"""
app/services/case_match.py

The case-study retrieval pipeline behind POST /client/cases — extracted out
of app/routers/client.py so production and the offline eval harness
(backend/scripts/eval_case_match_*.py) share exactly one implementation.
An eval that reimplemented this logic would measure a fork, not the
product.

What stays in the router: ClientContext resolution, profile decrypt,
CaseMatch persistence, and audit logging — this module is read-only and
writes nothing to the database.
"""
from __future__ import annotations

import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.client_intake import CaseStudy, CaseStudyTag
from app.models.file import FileChunk
from app.models.user import User
from app.services import case_score as score_svc
from app.services import client_intake as intake_svc
from app.services.case_card import CaseCard, parse_case_card
from app.tools import rag_search


@dataclass(frozen=True)
class CaseMatchResult:
    """One case file scored against a client profile — the best-scoring
    chunk of that file, collapsed to one row per file (a case study may
    retrieve several chunks; the Cases tab wants one card per case)."""

    file_id: uuid.UUID
    filename: str
    distance: float  # raw cosine distance of the best chunk (lower = closer)
    score: float  # 0..1 shown to the client — blended, see match_cases()
    rank: int  # 0-based, after sorting by (-score, filename)
    best_chunk_index: int
    rationale: str  # best chunk content[:280]
    card: CaseCard | None  # None when include_cards=False
    # Per-dimension contributions behind `score` (app/services/case_score.py).
    # None when the case library carries no tags yet, or when the tag model is
    # switched off with case_match_tag_weight = 0 — in both cases `score` is
    # the plain cosine similarity it has always been.
    breakdown: score_svc.CaseScore | None = None
    # Dimensions that matched outright, for the card's "ตรงกับ: …" line.
    matched_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseMatchRun:
    query: str
    chunks_retrieved: int
    results: list[CaseMatchResult]  # sorted by (distance, filename) — deterministic ties


def build_context_query(fields: Mapping[str, str]) -> str:
    """Flatten intake fields into one embeddable query string, in the fixed
    INTAKE_SCRIPT question order rather than dict-insertion order. In
    production these always agree (intake is answered strictly
    sequentially), so this is a no-op there; fixing the order removes a
    nondeterminism source for callers (e.g. the eval harness) that may
    build a `fields` dict by other means.

    Which fields are eligible — including how answers from an older script
    version are carried, and why solution-trigger answers are excluded — is
    decided by client_intake.match_query_fields(), so this builder and every
    eval variant it is benchmarked against cannot disagree about it.
    """
    return "; ".join(
        f"{intake_svc.FIELD_LABELS.get(k, k)}: {fields[k]}"
        for k in intake_svc.match_query_fields(fields)
    )


def collapse_best_per_file(
    chunks: Sequence[rag_search.RetrievedChunk],
) -> list[rag_search.RetrievedChunk]:
    """One lowest-distance chunk per file_id. Pure — no DB, no I/O."""
    best_by_file: dict[str, rag_search.RetrievedChunk] = {}
    for c in chunks:
        prev = best_by_file.get(c.file_id)
        if prev is None or c.score < prev.score:  # lower cosine distance = closer
            best_by_file[c.file_id] = c
    return list(best_by_file.values())


def to_match_score(distance: float) -> float:
    """cosine distance -> similarity, clamped to [0, 1]."""
    return max(0.0, min(1.0, 1.0 - distance))


async def cards_for_file_ids(
    session: AsyncSession, file_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, CaseCard]:
    """Rebuild CaseCards for a known set of file_ids, without re-running
    retrieval — lifted out of match_cases() so GET /client/bootstrap can
    replay a previously-persisted CaseMatch row's card the same way a fresh
    /client/cases call would build it, instead of re-implementing the
    full-text concatenation + parse_case_card() call a second time."""
    if not file_ids:
        return {}
    chunk_rows = (
        await session.execute(
            select(FileChunk.file_id, FileChunk.content)
            .where(FileChunk.file_id.in_(file_ids))
            .order_by(FileChunk.file_id, FileChunk.chunk_index)
        )
    ).all()
    full_texts: dict[uuid.UUID, str] = {}
    for fid, content in chunk_rows:
        full_texts[fid] = full_texts.get(fid, "") + content
    return {fid: parse_case_card(text) for fid, text in full_texts.items()}


async def tags_for_file_ids(
    session: AsyncSession, file_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[str, set[str]]]:
    """{file_id: {dimension: {token, ...}}} for the candidate cases.

    Keyed by file_id, not case_study_id, because retrieval works in files
    (chunks belong to files) while tags hang off the case_studies catalog
    row — this join is the one place that gap is bridged. A case with no
    tags is simply absent from the result; case_score treats that as
    "unknown", not "unsuitable".
    """
    if not file_ids:
        return {}
    rows = (
        await session.execute(
            select(CaseStudy.file_id, CaseStudyTag.tag_type, CaseStudyTag.tag_value)
            .join(CaseStudyTag, CaseStudyTag.case_study_id == CaseStudy.id)
            .where(CaseStudy.file_id.in_(file_ids))
        )
    ).all()
    out: dict[uuid.UUID, dict[str, set[str]]] = {}
    for file_id, tag_type, tag_value in rows:
        out.setdefault(file_id, {}).setdefault(tag_type, set()).add(tag_value)
    return out


async def match_cases(
    session: AsyncSession,
    user: User,
    fields: Mapping[str, str],
    *,
    agent_file_ids: Sequence[uuid.UUID] | None,
    effective_workspace_id: uuid.UUID | None = None,
    top_k: int | None = None,
    max_distance: float | None = None,
    query: str | None = None,
    include_cards: bool = True,
    strict: bool = False,
    alpha: float | None = None,
) -> CaseMatchRun:
    """Score a client's intake profile against the case library reachable
    by `user` (narrowed to `agent_file_ids` when given).

    `query` lets a caller override the embedded query string (e.g. the eval
    harness's query_variants) without re-deriving it from `fields`; the
    default is `build_context_query(fields)`, the exact production query.
    `effective_workspace_id` / `top_k` / `max_distance` / `strict` pass
    straight through to rag_search.retrieve() — see its docstring. `strict`
    defaults to False (production behaviour: degrade gracefully); the eval
    harness passes True so an embed-server outage aborts loudly instead of
    silently reporting "0.0 accuracy" for every profile.

    Ranking is the alpha blend described in app/services/case_score.py:
    retrieval widens to a candidate POOL (settings.case_match_pool_chunks,
    relevance cutoff disabled) and the weighted tag score decides what
    surfaces from it. Leaving retrieval at `rag_top_k` would let cosine
    pre-select the shortlist and make the interview's weights decorative —
    the weights could only reorder five cases cosine had already chosen.

    `alpha` overrides settings.case_match_tag_weight for one call (the eval
    harness sweeps it). alpha = 0 is the pre-tagging behaviour exactly, and
    is also what an untagged corpus degrades to on its own.

    Callers that pass an explicit `top_k` / `max_distance` (the eval
    harness's deep-pool mode) keep them: an explicit request always beats
    the pool default.
    """
    q = query if query is not None else build_context_query(fields)
    a = settings.case_match_tag_weight if alpha is None else alpha
    a = max(0.0, min(1.0, a))

    # Widen the pool only when the tag model is actually doing something. At
    # alpha = 0 the ranking is pure cosine, so pulling 200 chunks instead of
    # 5 would cost latency for an identical top-5.
    pool_k = top_k
    pool_max_distance = max_distance
    if a > 0.0:
        if pool_k is None:
            pool_k = settings.case_match_pool_chunks
        if pool_max_distance is None:
            pool_max_distance = math.inf

    chunks = await rag_search.retrieve(
        session,
        user,
        q,
        top_k=pool_k,
        file_ids=agent_file_ids,
        effective_workspace_id=effective_workspace_id,
        max_distance=pool_max_distance,
        strict=strict,
    )

    best_chunks = collapse_best_per_file(chunks)

    # Full document text per matched file — the best-scoring chunk may be a
    # middle chunk without the "# Case Study:" header, and parse_case_card
    # needs the whole template (title/client/category/source/narrative) to
    # build a presentable card instead of echoing raw markdown at the client.
    cards: dict[uuid.UUID, CaseCard] = {}
    if include_cards and best_chunks:
        matched_file_ids = [uuid.UUID(c.file_id) for c in best_chunks]
        cards = await cards_for_file_ids(session, matched_file_ids)

    # Corpus tags for the candidates. Empty dict when nothing is tagged yet,
    # which case_score turns into a damped-dense score per dimension rather
    # than a zero — a half-tagged corpus stays usable while tagging catches up.
    tags_by_file: dict[uuid.UUID, dict[str, set[str]]] = {}
    if a > 0.0 and best_chunks:
        tags_by_file = await tags_for_file_ids(
            session, [uuid.UUID(c.file_id) for c in best_chunks]
        )
    client_tags = score_svc.client_tags_from_fields(fields) if a > 0.0 else {}

    results: list[CaseMatchResult] = []
    for c in best_chunks:
        file_id = uuid.UUID(c.file_id)
        card = cards[file_id] if file_id in cards else (parse_case_card(c.content) if include_cards else None)
        dense = to_match_score(c.score)

        breakdown: score_svc.CaseScore | None = None
        if a > 0.0:
            breakdown = score_svc.score_case(
                client_tags,
                tags_by_file.get(file_id, {}),
                intake_svc.SCORING_WEIGHTS,
                dense,
                alpha=a,
            )
            final = breakdown.final
            matched_on = breakdown.matched_dimensions
        else:
            final = dense
            matched_on = ()

        results.append(
            CaseMatchResult(
                file_id=file_id,
                filename=c.filename,
                distance=c.score,
                score=final,
                rank=0,  # filled in after the deterministic sort below
                best_chunk_index=c.chunk_index,
                rationale=c.content[:280],
                card=card,
                breakdown=breakdown,
                matched_on=matched_on,
            )
        )

    # Below the floor a case is not worth showing at all. Applied only when
    # the tag model is on: at alpha = 0 the caller's max_distance is still the
    # only cutoff, exactly as before.
    if a > 0.0:
        results = [r for r in results if r.score >= settings.case_match_min_score]

    # Descending score. Filename remains the tiebreak so equal scores order
    # deterministically — several cases legitimately tie once scoring is
    # discrete tag overlap rather than a continuous cosine.
    results.sort(key=lambda r: (-r.score, r.filename))
    if a > 0.0:
        results = results[: settings.case_match_top_n]

    results = [
        CaseMatchResult(
            file_id=r.file_id,
            filename=r.filename,
            distance=r.distance,
            score=r.score,
            rank=i,
            best_chunk_index=r.best_chunk_index,
            rationale=r.rationale,
            card=r.card,
            breakdown=r.breakdown,
            matched_on=r.matched_on,
        )
        for i, r in enumerate(results)
    ]

    return CaseMatchRun(query=q, chunks_retrieved=len(chunks), results=results)
