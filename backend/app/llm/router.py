from functools import lru_cache

from app.llm.base import LLMClient


def _default_model_code() -> str:
    from app.config import get_settings

    return get_settings().llm_default_model


# D25: the baseline model every "auto"/unspecified request, every helper call
# (intent classification, skill matching, prompt assistant) and every policy
# downgrade resolves to. Read from LLM_DEFAULT_MODEL at import time; the
# provider behind it is LLM_DEFAULT_PROVIDER ("openai" | "local").
DEFAULT_MODEL_CODE = _default_model_code()
# Backwards-compatible alias — "local" is historical: before D25 the baseline
# was always the on-prem Ollama/llama.cpp model. Prefer DEFAULT_MODEL_CODE.
LOCAL_MODEL_CODE = DEFAULT_MODEL_CODE

PERPLEXITY_MODEL_CODE = "perplexity-sonar"
HERMES_MODEL_CODE = "hermes-agent"


def default_model_is_free() -> bool:
    """True when the default model costs nothing at inference time.

    Only the on-prem path is free; a hosted default (D25: OpenAI) is charged
    against quota like any other external model (orchestrator.call_llm and the
    /v1 passthrough consult this before quota_svc.consume()).
    """
    from app.config import get_settings

    return get_settings().llm_default_provider == "local"


class LLMRouter:
    def __init__(self, default_code: str, default_client: LLMClient) -> None:
        self._default_code = default_code
        self._clients: dict[str, LLMClient] = {default_code: default_client}

    @property
    def default_code(self) -> str:
        return self._default_code

    def get(self, model_code: str) -> LLMClient:
        client = self._clients.get(model_code)
        if client is None:
            raise KeyError(f"No LLM client registered for model code '{model_code}'")
        return client

    def register(self, model_code: str, client: LLMClient) -> None:
        self._clients[model_code] = client


def _build_default_client() -> LLMClient:
    from app.config import get_settings

    cfg = get_settings()
    if cfg.llm_default_provider == "local":
        from app.llm.llamacpp import LlamaCppClient

        return LlamaCppClient(
            base_url=cfg.llm_primary_url,
            model=cfg.llm_primary_model,
            connect_timeout=cfg.llm_connect_timeout,
            read_timeout=cfg.llm_read_timeout,
            connect_retries=cfg.llm_connect_retries,
            keep_alive=cfg.llm_keep_alive,
        )
    if cfg.llm_default_provider == "openai":
        if not cfg.openai_api_key:
            raise RuntimeError(
                "LLM_DEFAULT_PROVIDER=openai requires OPENAI_API_KEY to be set"
            )
        from app.llm.openai import OpenAIClient

        return OpenAIClient(
            api_key=cfg.openai_api_key,
            model=cfg.llm_default_model,
            supports_reasoning=cfg.llm_default_supports_reasoning,
        )
    raise RuntimeError(
        f"Unsupported LLM_DEFAULT_PROVIDER={cfg.llm_default_provider!r} (expected 'openai' or 'local')"
    )


@lru_cache
def get_router() -> LLMRouter:
    from app.config import get_settings

    cfg = get_settings()
    router = LLMRouter(DEFAULT_MODEL_CODE, _build_default_client())

    if cfg.anthropic_api_key:
        from app.llm.anthropic import AnthropicClient

        router.register("claude-sonnet-4", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-sonnet-4-6"))
        router.register("claude-opus-4", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-opus-4-8"))
        # True AI Hub verbatim codes → same underlying client
        router.register("Claude Sonnet 4.5", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-sonnet-4-6"))
        router.register("Claude Sonnet 4.6", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-sonnet-4-6"))

    if cfg.openai_api_key:
        from app.llm.openai import OpenAIClient

        def _oa(model: str) -> OpenAIClient:
            return OpenAIClient(api_key=cfg.openai_api_key, model=model)

        # Legacy catalog codes kept for existing agents / permissions rows.
        router.register("gpt-4o-mini", _oa("gpt-4o-mini"))
        router.register("gpt-4o", _oa("gpt-4o"))
        # True AI Hub verbatim codes → nearest available OpenAI model
        router.register("gpt-5-nano", _oa("gpt-4o-mini"))
        router.register("GPT 5.1", _oa("gpt-4o"))
        router.register("@b2c-production-openai/gpt-5", _oa("gpt-4o"))

    if cfg.google_api_key:
        from app.llm.google import GoogleClient

        google_client = GoogleClient(api_key=cfg.google_api_key)
        router.register("gemini-2.5-flash", google_client)
        router.register("gemini-2.5-flash-image", google_client)
        # True AI Hub verbatim code
        router.register("Gemini 2.5 Pro", google_client)
        # Cheapest Google text tier — separate client instance so it actually
        # calls the flash-lite tier, not the flash default above. Pinned to
        # the rolling "-latest" alias: the dated gemini-2.5-flash-lite id is
        # already rejected for this API key ("no longer available to new
        # users"), so a fixed version string would just break again later.
        router.register(
            "gemini-2.5-flash-lite",
            GoogleClient(api_key=cfg.google_api_key, text_model="gemini-flash-lite-latest"),
        )

    if cfg.perplexity_api_key:
        from app.llm.perplexity import PerplexityClient

        router.register("perplexity-sonar", PerplexityClient(api_key=cfg.perplexity_api_key))

    if cfg.hermes_api_key:
        from app.llm.hermes import HermesClient

        router.register(
            HERMES_MODEL_CODE,
            HermesClient(
                api_key=cfg.hermes_api_key,
                base_url=cfg.hermes_api_url,
                timeout=cfg.hermes_api_timeout,
            ),
        )

    return router
