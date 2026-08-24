"""RAG retrieval tool — embeds a query, runs pgvector cosine search, returns
the top-k chunks the user is allowed to see (personal + org scope).

Usage from the orchestrator / chat_policy::

    from app.tools.rag_search import retrieve, build_context_block, citations

    chunks = await retrieve(session, user, query="What is the refund policy?", top_k=5)
    context = build_context_block(chunks)
    srcs = citations(chunks)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.embeddings import EmbeddingError, get_embedder
from app.models.file import LIBRARY_SCOPE, File, FileChunk
from app.models.user import User
from app.services.workspace import (
    workspace_visibility_filter,
    workspace_visibility_filter_by_workspace_id,
)

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class RetrievedChunk:
    """One chunk returned by a vector similarity search."""
    chunk_id: str
    file_id: str
    filename: str
    chunk_index: int
    content: str
    score: float        # cosine distance (lower = more similar)
    scope: str


# ---------------------------------------------------------------------------
# Core retrieval
# ---------------------------------------------------------------------------

def _scope_filter(user: User, file_ids: list | None, effective_workspace_id=None):
    """Build the WHERE clause enforcing access rule R4:
      • personal files: must belong to this user
      • org files: any user in the same tenant may read (D21/D22 — internal
        users only see internal-shared org files; a client seat only sees
        org files scoped to its own workspace, never another workspace's
        and never the internal org corpus)
      • library files: the shared case-study corpus, readable by every
        tenant regardless of CLIENT_INTERNAL_ACCESS_ENABLED (ADR 0002 —
        every LINE-minted workspace is its own tenant, so an org-scoped
        corpus stamped to one workspace was invisible to all of them and
        POST /client/cases returned zero chunks for every real client)

    When ``file_ids`` is given (e.g. an AI Agent's attached knowledge
    files), the corpus is narrowed to just those files — but R4 still
    applies on top: an agent's attached files never bypass ownership/scope.

    ``effective_workspace_id``, when given, replaces ``user.workspace_id``
    as the tenant key for the org branch only — see
    app/services/workspace.py::workspace_visibility_filter_by_workspace_id
    for why (/client/* preview reads). ``None`` (the default, every
    existing caller) is unchanged behaviour: the org branch keys off the
    user's own workspace_id.
    """
    org_filter = (
        workspace_visibility_filter_by_workspace_id(effective_workspace_id, File)
        if effective_workspace_id is not None
        else workspace_visibility_filter(user, File)
    )
    access_filter = or_(
        and_(File.scope == "personal", File.user_id == user.id),
        and_(File.scope == "org", org_filter),
        File.scope == LIBRARY_SCOPE,
    )
    if file_ids:
        return and_(File.id.in_(file_ids), access_filter)
    return access_filter


async def retrieve(
    session: AsyncSession,
    user: User,
    query: str,
    top_k: int | None = None,
    file_ids: list | None = None,
    effective_workspace_id=None,
    max_distance: float | None = None,
    strict: bool = False,
) -> list[RetrievedChunk]:
    """Embed ``query`` and return the top-k most similar processed chunks
    that the user is permitted to read (personal scope or org scope).

    When ``file_ids`` is provided (from an AI Agent's knowledge set), results
    are restricted to only those files instead of the full user-accessible corpus.

    ``effective_workspace_id`` overrides the org-scope tenant key — see
    _scope_filter(). ``max_distance`` overrides the relevance cutoff (pass
    ``math.inf`` to disable it entirely, e.g. for an eval deep-pool run);
    ``None`` (the default) uses ``settings.rag_max_distance``.

    Returns an empty list (gracefully) when the embed server is unavailable
    so chat can degrade to non-RAG rather than failing the entire request —
    unless ``strict=True``, in which case the EmbeddingError is re-raised.
    Production callers never set ``strict``; it exists so an offline eval
    harness aborts loudly instead of silently reporting "0.0 accuracy" for
    every profile when the embed server happens to be down.
    """
    if not query.strip():
        return []

    from app.config import get_settings
    k = top_k or get_settings().rag_top_k

    # 1. Embed the query
    try:
        query_vec = await get_embedder().embed_one(query)
    except EmbeddingError as exc:
        if strict:
            raise
        _log.warning("RAG: embed failed, skipping retrieval: %s", exc)
        return []

    # 2. pgvector cosine distance search — only processed files in scope
    scope_filter = _scope_filter(user, file_ids, effective_workspace_id)

    stmt = (
        select(
            FileChunk.id,
            FileChunk.file_id,
            File.filename,
            FileChunk.chunk_index,
            FileChunk.content,
            FileChunk.embedding.cosine_distance(query_vec).label("distance"),
            File.scope,
        )
        .join(File, FileChunk.file_id == File.id)
        .where(
            and_(
                FileChunk.embedding.is_not(None),
                File.is_processed.is_(True),
                scope_filter,
            )
        )
        .order_by("distance")
        .limit(k)
    )

    rows = (await session.execute(stmt)).all()

    max_dist = max_distance if max_distance is not None else get_settings().rag_max_distance
    chunks = [
        RetrievedChunk(
            chunk_id=str(row.id),
            file_id=str(row.file_id),
            filename=row.filename,
            chunk_index=row.chunk_index,
            content=row.content,
            score=float(row.distance),
            scope=row.scope,
        )
        for row in rows
    ]
    # Drop chunks that are too distant (likely irrelevant). build_context_block()
    # already returns "" for an empty list, so the LLM answers without injected docs.
    relevant = [c for c in chunks if c.score <= max_dist]
    if len(relevant) < len(chunks):
        _log.debug(
            "RAG: dropped %d/%d chunks exceeding max_distance=%.3f",
            len(chunks) - len(relevant),
            len(chunks),
            max_dist,
        )
    return relevant


# ---------------------------------------------------------------------------
# Context formatting helpers
# ---------------------------------------------------------------------------

def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a system-message context block.

    The LLM is instructed to answer from the provided sources and cite them
    by filename. Returns an empty string when the list is empty.
    """
    if not chunks:
        return ""

    parts = [
        "You have access to the following document excerpts from the company "
        "knowledge base. Use them to answer the user's question. "
        "Cite the source filename when you reference content from it.\n"
    ]
    for i, chunk in enumerate(chunks, 1):
        parts.append(
            f"[{i}] {chunk.filename} (chunk {chunk.chunk_index}):\n{chunk.content}"
        )
    return "\n\n".join(parts)


def citations(chunks: list[RetrievedChunk]) -> list[dict]:
    """Return a serialisable list of citation objects for the SSE ``sources`` event."""
    seen: set[str] = set()
    result: list[dict] = []
    for chunk in chunks:
        key = f"{chunk.file_id}:{chunk.chunk_index}"
        if key not in seen:
            seen.add(key)
            result.append({
                "file_id": chunk.file_id,
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
                "score": round(chunk.score, 4),
            })
    return result
