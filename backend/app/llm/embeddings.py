"""Embedding clients for RAG / case matching.

D25: the default is OpenAI ``text-embedding-3-small`` (1536 dims —
``file_chunks.embedding`` is VECTOR(1536) since migration 0066). The original
BGE-M3-via-Ollama client is kept behind ``LLM_EMBED_PROVIDER=local`` but its
1024-dim vectors need the column re-migrated before they can be stored.

Usage::

    from app.llm.embeddings import get_embedder

    vecs = await get_embedder().embed(["hello", "world"])
    # vecs: list[list[float]], each len EMBEDDING_DIMS
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Protocol

import httpx

EMBEDDING_DIMS = 1536

_RETRY_BACKOFF = [0.5 * (i + 1) for i in range(10)]


class EmbeddingError(Exception):
    """Raised when the embedding server returns an error or is unreachable."""


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_one(self, text: str) -> list[float]: ...
    async def ping(self) -> bool: ...


class OpenAIEmbeddingClient:
    """OpenAI /v1/embeddings client (default since D25).

    Args:
        api_key: OpenAI API key.
        model: Embedding model id (``text-embedding-3-small`` -> 1536 dims).
        read_timeout: Seconds to wait for the full response.
        connect_retries: Connect-phase retries before giving up.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        read_timeout: float = 60.0,
        connect_retries: int = 3,
    ) -> None:
        import openai

        self._model = model
        self._connect_retries = max(connect_retries, 1)
        self._client = openai.AsyncOpenAI(api_key=api_key, timeout=read_timeout)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import openai

        last_exc: Exception | None = None
        for attempt in range(self._connect_retries):
            try:
                response = await self._client.embeddings.create(model=self._model, input=texts)
                # OpenAI returns items with an `index`; order defensively.
                ordered = sorted(response.data, key=lambda d: d.index)
                return [d.embedding for d in ordered]
            except openai.APITimeoutError as exc:
                raise EmbeddingError("Embedding server timed out.") from exc
            except openai.APIConnectionError as exc:
                last_exc = exc
                if attempt < self._connect_retries - 1:
                    await asyncio.sleep(_RETRY_BACKOFF[attempt])
            except openai.APIStatusError as exc:
                raise EmbeddingError(
                    f"Embedding server returned {exc.status_code}: {exc.message}"
                ) from exc

        raise EmbeddingError(
            f"Embedding server (openai) not reachable after {self._connect_retries} attempts."
        ) from last_exc

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

    async def ping(self) -> bool:
        try:
            await self._client.with_options(timeout=5.0).models.retrieve(self._model)
            return True
        except Exception:
            return False


class EmbeddingClient:
    """Calls the Ollama /api/embed endpoint (native Ollama API) — BGE-M3 path.

    Uses the native endpoint instead of the OpenAI-compatible /v1/embeddings so
    that keep_alive is honoured reliably — the /v1/ shim does not forward it.

    Args:
        base_url: Base URL of the Ollama server (e.g. ``http://host:11434``).
        model: Model name as shown by ``ollama list`` (e.g. ``bge-m3:latest``).
        connect_timeout: Seconds to wait for TCP connection.
        read_timeout: Seconds to wait for the full response.
        connect_retries: How many connect-phase retries before giving up.
        keep_alive: Ollama keep_alive value — ``"0"`` unloads immediately after
            each request, ``"-1"`` keeps forever, ``"5m"`` keeps 5 minutes.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "bge-m3:latest",
        connect_timeout: float = 10.0,
        read_timeout: float = 60.0,
        connect_retries: int = 3,
        keep_alive: str = "0",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._connect_retries = max(connect_retries, 1)
        self._keep_alive = keep_alive

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return an embedding vector for each input text.

        Raises:
            EmbeddingError: On server error or connection failure.
        """
        if not texts:
            return []

        payload = {"model": self._model, "input": texts, "keep_alive": self._keep_alive}
        timeout = httpx.Timeout(
            connect=self._connect_timeout,
            read=self._read_timeout,
            write=self._connect_timeout,
            pool=5.0,
        )
        last_exc: Exception | None = None

        for attempt in range(self._connect_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/api/embed",
                        json=payload,
                    )
                    if response.status_code != 200:
                        body = response.text[:400]
                        raise EmbeddingError(
                            f"Embedding server returned {response.status_code}: {body}"
                        )
                    data = response.json()
                    # Native Ollama shape: {"embeddings": [[...], [...]]}
                    return data["embeddings"]

            except EmbeddingError:
                raise

            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                last_exc = exc
                if attempt < self._connect_retries - 1:
                    await asyncio.sleep(_RETRY_BACKOFF[attempt])

            except httpx.ReadTimeout as exc:
                raise EmbeddingError("Embedding server timed out.") from exc

            except httpx.HTTPError as exc:
                raise EmbeddingError(f"Embedding server unreachable: {exc}") from exc

        raise EmbeddingError(
            f"Embedding server not reachable at {self._base_url} after "
            f"{self._connect_retries} attempts."
        ) from last_exc

    async def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper: embed a single string and return its vector."""
        results = await self.embed([text])
        return results[0]

    async def ping(self) -> bool:
        """Return True if the embedding server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                r = await client.get(f"{self._base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False


@lru_cache
def get_embedder() -> Embedder:
    """Return the process-singleton embedding client (built from settings)."""
    from app.config import get_settings

    cfg = get_settings()
    if cfg.llm_embed_provider == "openai":
        if not cfg.openai_api_key:
            raise EmbeddingError("LLM_EMBED_PROVIDER=openai requires OPENAI_API_KEY to be set")
        return OpenAIEmbeddingClient(
            api_key=cfg.openai_api_key,
            model=cfg.llm_embed_model,
            read_timeout=cfg.llm_read_timeout,
            connect_retries=cfg.llm_connect_retries,
        )
    return EmbeddingClient(
        base_url=cfg.llm_embed_url,
        model=cfg.llm_embed_model,
        connect_timeout=cfg.llm_connect_timeout,
        read_timeout=cfg.llm_read_timeout,
        connect_retries=cfg.llm_connect_retries,
        keep_alive=cfg.llm_keep_alive,
    )
