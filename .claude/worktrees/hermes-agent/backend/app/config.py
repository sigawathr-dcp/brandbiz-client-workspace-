from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "brandbiz"
    postgres_user: str = "brandbiz"
    postgres_password: str

    # Crypto
    encryption_key: str
    encryption_key_version: int = 1

    # Auth
    jwt_secret: str

    # Google OAuth (required from Task 1.5; blank disables OAuth routes)
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_workspace_domain: str = ""

    # LLM endpoints
    llm_primary_url: str = "http://llamacpp-primary:8080"
    llm_primary_model: str = "qwen2.5-14b-local"
    llm_embed_url: str = "http://llamacpp-embed:8081"
    # Embedding model name (must match `ollama list` output on the embed server)
    llm_embed_model: str = "bge-m3:latest"

    # How long Ollama keeps a model loaded in VRAM after a request (Ollama keep_alive param).
    # "0" = unload immediately (share VRAM across models on demand).
    # "-1" = keep forever. "5m" = keep 5 minutes. Passed verbatim to Ollama.
    llm_keep_alive: str = "0"

    # Local LLM reliability knobs (override via env; defaults match previous hardcoded values)
    llm_connect_timeout: float = 10.0   # seconds to establish TCP + TLS
    llm_read_timeout: float = 120.0     # seconds waiting for streaming tokens
    llm_connect_retries: int = 3        # connect-phase retries before giving up

    # RAG / Knowledge base
    rag_top_k: int = 5                         # number of chunks to retrieve per query
    rag_chunk_tokens: int = 500                # target chunk size in tokens (~4 chars/token)
    rag_chunk_overlap: int = 50                # overlap between adjacent chunks (in tokens)
    rag_max_distance: float = 0.6              # cosine distance ceiling; chunks above this are dropped as irrelevant
    file_storage_dir: str = "./data/files"     # local blob storage root (volume-mounted)
    max_upload_bytes: int = 50 * 1024 * 1024   # 50 MB per file

    # External APIs (Phase 2+)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    perplexity_api_key: str = ""

    # Hermes Agent — self-hosted, OpenAI-compatible API server (blank disables registration)
    hermes_api_key: str = ""
    hermes_api_url: str = "http://localhost:8642/v1"
    # Background agent tasks (Task 3.12) run Hermes's full tool loop unattended and can take
    # much longer than an interactive chat turn; keep this well above llm_read_timeout.
    hermes_api_timeout: float = 600.0

    # n8n outbound webhook — leave blank to disable all Gateway→n8n triggers.
    # Both the admin LINE alert (server-down keywords) and the label-inbox trigger
    # post to this single URL with distinct "action" fields so n8n can branch.
    n8n_webhook_url: str = ""

    # Obsidian vault sync (read-only RAG ingestion) — leave vault_git_url blank
    # to disable. URL should embed an access token: https://<token>@host/org/repo.git
    vault_git_url: str = ""
    vault_dir: str = "/data/vault"          # local clone dir (volume-mounted)
    vault_branch: str = "main"
    vault_bot_email: str = "obsidian-bot@service.local"
    vault_templates_dirname: str = "templates"  # excluded dir name (case-insensitive)

    # Cookie settings
    cookie_domain: str = ""
    cookie_secure: bool = False

    # CORS — frontend origins allowed to send credentialed requests
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
