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

    # Weighted case matching (app/services/case_score.py). The score a client
    # sees is alpha * weighted-tag-score + (1 - alpha) * cosine-similarity.
    # alpha = 0 reproduces the pre-tagging behaviour exactly — the rollback
    # path and the eval harness's A/B baseline.
    case_match_tag_weight: float = 0.7
    # Candidate pool for rescoring. rag_top_k is a CHUNK budget applied
    # before any weighting, so leaving it at 5 would let cosine pre-select
    # the shortlist and make the weights decorative. Retrieval widens to this
    # many chunks with the distance ceiling disabled, then the weighted score
    # decides what actually surfaces.
    case_match_pool_chunks: int = 200
    # Floor on the blended score; below this a case is not shown at all.
    case_match_min_score: float = 0.15
    # How many cases the client is shown after rescoring. 3 per
    # Matching_logic.xlsx ("Top 3 cases" / "Rank 2–3 Case") — the AE has to
    # be able to explain every card that surfaces, so the list is kept to
    # what a person will actually argue for.
    case_match_top_n: int = 3

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
    # Ollama endpoint Hermes itself reasons against — used only to render the
    # downloadable host-setup script (Task 3.13). A running Hermes reads its
    # own config.yaml; changing these does not reconfigure it.
    hermes_ollama_url: str = "http://192.168.20.18:12342/v1"
    hermes_ollama_model: str = "gemma4:26b"

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

    # Client Workspaces (Phase 5, D21/D22) — event kill switch. Set false to
    # hard-disable /client/*, /public/*, and /admin/clients/* without a
    # deploy. Client-seat routers check this explicitly (they are not gated
    # by require_internal, so they need their own off switch).
    client_surface_enabled: bool = True

    # D23 — let client-workspace seats use the full internal app (chat,
    # files, agents, skills, studio, tasks, conversations, image), not just
    # /client/*. Off by default in code; a single reversible switch — see
    # app/deps.py::require_internal. hermes and automations stay staff-only
    # regardless, via require_staff / require_staff_principal.
    client_internal_access_enabled: bool = False

    # D23 — non-NULL default caps for a client workspace when the caller
    # (POST /admin/clients, or a seed script) doesn't pass explicit ones.
    # create_workspace() used to default both to None (= uncapped); an
    # admin who genuinely wants uncapped can still pass a very large number
    # explicitly. Per-seat monthly ceiling, then pooled cap across every
    # seat the workspace ever mints (PolicyEngine.decide() Rule 5).
    client_default_monthly_token_limit: int = 200_000
    client_default_workspace_budget: int = 2_000_000

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
