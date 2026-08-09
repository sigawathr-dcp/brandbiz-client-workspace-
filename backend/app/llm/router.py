from functools import lru_cache

from app.llm.base import LLMClient

LOCAL_MODEL_CODE = "gemma4:26b"
PERPLEXITY_MODEL_CODE = "perplexity-sonar"
HERMES_MODEL_CODE = "hermes-agent"


class LLMRouter:
    def __init__(
        self,
        primary_url: str,
        primary_model: str = LOCAL_MODEL_CODE,
        connect_timeout: float = 10.0,
        read_timeout: float = 120.0,
        connect_retries: int = 3,
        keep_alive: str = "0",
    ) -> None:
        from app.llm.llamacpp import LlamaCppClient

        self._clients: dict[str, LLMClient] = {
            LOCAL_MODEL_CODE: LlamaCppClient(
                base_url=primary_url,
                model=primary_model,
                connect_timeout=connect_timeout,
                read_timeout=read_timeout,
                connect_retries=connect_retries,
                keep_alive=keep_alive,
            ),
        }

    def get(self, model_code: str) -> LLMClient:
        client = self._clients.get(model_code)
        if client is None:
            raise KeyError(f"No LLM client registered for model code '{model_code}'")
        return client

    def register(self, model_code: str, client: LLMClient) -> None:
        self._clients[model_code] = client


@lru_cache
def get_router() -> LLMRouter:
    from app.config import get_settings

    cfg = get_settings()
    router = LLMRouter(
        primary_url=cfg.llm_primary_url,
        primary_model=cfg.llm_primary_model,
        connect_timeout=cfg.llm_connect_timeout,
        read_timeout=cfg.llm_read_timeout,
        connect_retries=cfg.llm_connect_retries,
        keep_alive=cfg.llm_keep_alive,
    )

    if cfg.anthropic_api_key:
        from app.llm.anthropic import AnthropicClient

        router.register("claude-sonnet-4", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-sonnet-4-6"))
        router.register("claude-opus-4", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-opus-4-8"))
        # True AI Hub verbatim codes → same underlying client
        router.register("Claude Sonnet 4.5", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-sonnet-4-6"))
        router.register("Claude Sonnet 4.6", AnthropicClient(api_key=cfg.anthropic_api_key, model="claude-sonnet-4-6"))

    if cfg.openai_api_key:
        from app.llm.openai import OpenAIClient

        router.register("gpt-4o-mini", OpenAIClient(api_key=cfg.openai_api_key, model="gpt-4o-mini"))
        router.register("gpt-4o", OpenAIClient(api_key=cfg.openai_api_key, model="gpt-4o"))
        # True AI Hub verbatim codes → nearest available OpenAI model
        router.register("gpt-5-nano", OpenAIClient(api_key=cfg.openai_api_key, model="gpt-4o-mini"))
        router.register("GPT 5.1", OpenAIClient(api_key=cfg.openai_api_key, model="gpt-4o"))
        router.register("@b2c-production-openai/gpt-5", OpenAIClient(api_key=cfg.openai_api_key, model="gpt-4o"))

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
