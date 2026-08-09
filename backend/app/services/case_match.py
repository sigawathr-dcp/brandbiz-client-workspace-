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

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import FileChunk
from app.models.user import User
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
    score: float  # max(0, min(1, 1 - distance)) — the number shown to the client
    rank: int  # 0-based, after sorting by (distance, filename)
    best_chunk_index: int
    rationale: str  # best chunk content[:280]
    card: CaseCard | None  # None when include_cards=False


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
    """
    ordered_keys = [step["field"] for step in intake_svc.INTAKE_SCRIPT]
    return "; ".join(
        f"{intake_svc.FIELD_LABELS.get(k, k)}: {fields[k]}"
        for k in ordered_keys
        if k in fields
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
    """
    q = query if query is not None else build_context_query(fields)
    chunks = await rag_search.retrieve(
        session,
        user,
        q,
        top_k=top_k,
        file_ids=agent_file_ids,
        effective_workspace_id=effective_workspace_id,
        max_distance=max_distance,
        strict=strict,
    )

    best_chunks = collapse_best_per_file(chunks)

    # Full document text per matched file — the best-scoring chunk may be a
    # middle chunk without the "# Case Study:" header, and parse_case_card
    # needs the whole template (title/client/category/source/narrative) to
    # build a presentable card instead of echoing raw markdown at the client.
    full_texts: dict[uuid.UUID, str] = {}
    if include_cards and best_chunks:
        matched_file_ids = [uuid.UUID(c.file_id) for c in best_chunks]
        chunk_rows = (
            await session.execute(
                select(FileChunk.file_id, FileChunk.content)
                .where(FileChunk.file_id.in_(matched_file_ids))
                .order_by(FileChunk.file_id, FileChunk.chunk_index)
            )
        ).all()
        for fid, content in chunk_rows:
            full_texts[fid] = full_texts.get(fid, "") + content

    results: list[CaseMatchResult] = []
    for c in best_chunks:
        file_id = uuid.UUID(c.file_id)
        card = parse_case_card(full_texts.get(file_id, c.content)) if include_cards else None
        results.append(
            CaseMatchResult(
                file_id=file_id,
                filename=c.filename,
                distance=c.score,
                score=to_match_score(c.score),
                rank=0,  # filled in after the deterministic sort below
                best_chunk_index=c.chunk_index,
                rationale=c.content[:280],
                card=card,
            )
        )

    results.sort(key=lambda r: (r.distance, r.filename))
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
        )
        for i, r in enumerate(results)
    ]

    return CaseMatchRun(query=q, chunks_retrieved=len(chunks), results=results)
