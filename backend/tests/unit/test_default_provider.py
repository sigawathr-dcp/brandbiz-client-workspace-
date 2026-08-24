"""D25 — OpenAI as the default chat + embedding provider.

Covers the seams the switch touched: router default-client selection,
Ollama-kwarg translation in OpenAIClient, the OpenAI embedding client, and
the billing predicate.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm import router as router_mod
from app.llm.embeddings import EmbeddingError, OpenAIEmbeddingClient
from app.llm.openai import OpenAIClient, _translate_opts

pytest.importorskip("openai")


# ---------------------------------------------------------------------------
# _translate_opts
# ---------------------------------------------------------------------------

def test_translate_opts_maps_num_predict_and_drops_keep_alive():
    out = _translate_opts({"options": {"num_predict": 10}, "keep_alive": "5m"})
    assert out == {"max_completion_tokens": 10}


def test_translate_opts_drops_options_without_num_predict():
    assert _translate_opts({"options": {"num_ctx": 4096}}) == {}


def test_translate_opts_max_tokens_alias_and_passthrough():
    out = _translate_opts({"max_tokens": 50, "top_p": 0.9})
    assert out == {"max_completion_tokens": 50, "top_p": 0.9}


# ---------------------------------------------------------------------------
# OpenAIClient.stream_chat — helper-call kwargs reach the SDK translated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_chat_translates_helper_kwargs():
    client = OpenAIClient(api_key="k", model="gpt-5.4-mini-2026-03-17", supports_reasoning=True)

    async def fake_stream():
        yield SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason=None, delta=SimpleNamespace(content="ok"))])
        yield SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1),
            choices=[SimpleNamespace(finish_reason="stop", delta=SimpleNamespace(content=None))],
        )

    create = AsyncMock(return_value=fake_stream())
    client._client = MagicMock()
    client._client.chat.completions.create = create

    from app.llm.base import ChatMessage
    chunks = [c async for c in client.stream_chat(
        [ChatMessage(role="user", content="hi")],
        options={"num_predict": 10},
        keep_alive="5m",
    )]

    kwargs = create.call_args.kwargs
    assert kwargs["max_completion_tokens"] == 10
    assert "keep_alive" not in kwargs and "options" not in kwargs
    assert "temperature" not in kwargs  # reasoning-class model: never sent
    assert chunks[-1].prompt_tokens == 3 and chunks[-1].completion_tokens == 1


@pytest.mark.asyncio
async def test_ping_false_on_error():
    client = OpenAIClient(api_key="k", model="gpt-5.4-mini-2026-03-17")
    client._client = MagicMock()
    client._client.with_options.return_value.models.retrieve = AsyncMock(side_effect=RuntimeError("boom"))
    assert await client.ping() is False


# ---------------------------------------------------------------------------
# OpenAIEmbeddingClient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openai_embed_returns_vectors_in_input_order():
    emb = OpenAIEmbeddingClient(api_key="k")
    response = SimpleNamespace(data=[
        SimpleNamespace(index=1, embedding=[0.2] * 3),
        SimpleNamespace(index=0, embedding=[0.1] * 3),
    ])
    emb._client = MagicMock()
    emb._client.embeddings.create = AsyncMock(return_value=response)

    vecs = await emb.embed(["a", "b"])
    assert vecs == [[0.1] * 3, [0.2] * 3]
    emb._client.embeddings.create.assert_awaited_once_with(model="text-embedding-3-small", input=["a", "b"])


@pytest.mark.asyncio
async def test_openai_embed_empty_input_short_circuits():
    emb = OpenAIEmbeddingClient(api_key="k")
    emb._client = MagicMock()
    assert await emb.embed([]) == []


@pytest.mark.asyncio
async def test_openai_embed_status_error_becomes_embedding_error():
    import openai

    emb = OpenAIEmbeddingClient(api_key="k", connect_retries=1)
    emb._client = MagicMock()
    exc = openai.APIStatusError("bad", response=MagicMock(status_code=401), body=None)
    emb._client.embeddings.create = AsyncMock(side_effect=exc)
    with pytest.raises(EmbeddingError, match="401"):
        await emb.embed(["x"])


# ---------------------------------------------------------------------------
# Router default-client selection + billing predicate
# ---------------------------------------------------------------------------

def _settings(**over):
    base = dict(
        llm_default_provider="openai",
        llm_default_model="gpt-5.4-mini-2026-03-17",
        llm_default_supports_reasoning=True,
        openai_api_key="k",
        llm_primary_url="http://localhost:8080",
        llm_primary_model="gemma4:26b",
        llm_connect_timeout=1.0,
        llm_read_timeout=1.0,
        llm_connect_retries=1,
        llm_keep_alive="0",
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_build_default_client_openai():
    with patch("app.config.get_settings", return_value=_settings()):
        client = router_mod._build_default_client()
    assert isinstance(client, OpenAIClient)
    assert client.supports_reasoning is True


def test_build_default_client_openai_requires_key():
    with patch("app.config.get_settings", return_value=_settings(openai_api_key="")):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            router_mod._build_default_client()


def test_build_default_client_local():
    from app.llm.llamacpp import LlamaCppClient

    with patch("app.config.get_settings", return_value=_settings(llm_default_provider="local")):
        client = router_mod._build_default_client()
    assert isinstance(client, LlamaCppClient)


def test_default_model_is_free_only_for_local():
    with patch("app.config.get_settings", return_value=_settings()):
        assert router_mod.default_model_is_free() is False
    with patch("app.config.get_settings", return_value=_settings(llm_default_provider="local")):
        assert router_mod.default_model_is_free() is True
