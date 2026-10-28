from pathlib import Path
from urllib.parse import urlsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND = Path(__file__).resolve().parents[1]
# Later files override earlier ones; real environment variables override both. Missing files are ignored.
_ENV_FILES = (_BACKEND.parent / ".env", _BACKEND / ".env")

VALID_ENVIRONMENTS = {"development", "test", "staging", "production"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
WEAK_SECRETS = {
    "",
    "change-me",
    "change-me-in-production",
    "secret",
    "jwt-secret",
    "test-secret",
    "dev-secret",
    "placeholder",
    "replace-with-strong-random-secret",
}
WEAK_DB_PASSWORDS = {"", "change-me", "password", "postgres", "webforge", "admin", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    # Deployment & observability
    environment: str = "development"  # development | test | staging | production
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR | CRITICAL
    log_json: bool = False  # emit structured JSON log lines when True (recommended in staging/production)
    enable_metrics: bool = True  # bounded in-memory request/error counters

    # Database connection & pool settings
    database_url: str  # required, e.g. postgresql+psycopg://user:pass@host:5432/dbname
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_connect_retries: int = 5
    db_connect_retry_delay_seconds: float = 1.0

    # Authentication & CORS
    jwt_secret: str = ""
    cors_origins: str = "http://localhost:5173"
    cookie_secure: bool = False

    # AI provider configuration
    ai_provider: str = "google"
    google_ai_api_key: str = ""
    # Google's changelog (2026-09-18) limits the 2.5 models to existing users and points new projects at 3.5 Flash-Lite / 3.8 Flash.
    # Alternatives: gemini-3.5-flash-lite (cheaper), gemini-3.6-flash. Verify with `python -m app.provider_check --live`.
    google_model: str = "gemini-3.8-flash"
    google_timeout_seconds: int = 60

    # Discovery & lifecycle generation timeouts
    discovery_max_rounds: int = 3
    discovery_questions_per_round: int = 5
    discovery_generation_timeout_seconds: int = 120
    research_generation_timeout_seconds: int = 180
    strategy_generation_timeout_seconds: int = 180
    prd_generation_timeout_seconds: int = 180
    ux_generation_timeout_seconds: int = 180
    design_generation_timeout_seconds: int = 180
    architecture_generation_timeout_seconds: int = 180
    optimization_generation_timeout_seconds: int = 180
    slow_request_threshold_ms: float = 500.0


def validate_runtime_settings(cfg: Settings | None = None) -> list[str]:
    """Validate runtime settings and return a list of human-readable configuration errors (never containing secret values)."""
    s = cfg or settings
    errors: list[str] = []

    env = (s.environment or "").strip().lower()
    if env not in VALID_ENVIRONMENTS:
        errors.append(f"ENVIRONMENT must be one of {sorted(VALID_ENVIRONMENTS)} (got {s.environment!r}).")

    lvl = (s.log_level or "").strip().upper()
    if lvl not in VALID_LOG_LEVELS:
        errors.append(f"LOG_LEVEL must be one of {sorted(VALID_LOG_LEVELS)} (got {s.log_level!r}).")

    db_url = (s.database_url or "").strip()
    if not db_url:
        errors.append("DATABASE_URL is required and cannot be empty.")

    if s.db_pool_size < 1 or s.db_max_overflow < 0 or s.db_pool_timeout < 1:
        errors.append("Database pool parameters (DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT) must be positive.")

    if s.db_connect_retries < 0 or s.db_connect_retry_delay_seconds < 0:
        errors.append("DB_CONNECT_RETRIES and DB_CONNECT_RETRY_DELAY_SECONDS must be non-negative.")

    # Strict production / staging fail-fast validation
    if env in ("production", "staging"):
        sec = (s.jwt_secret or "").strip()
        if sec.lower() in WEAK_SECRETS or len(sec) < 32:
            errors.append(
                "JWT_SECRET must be set to a strong random secret of at least 32 characters in staging/production."
            )

        if not (db_url.startswith("postgresql://") or db_url.startswith("postgresql+psycopg://")):
            errors.append("DATABASE_URL must use PostgreSQL (postgresql+psycopg://) in staging/production.")
        else:
            parsed_db = urlsplit(db_url)
            db_pwd = (parsed_db.password or "").strip().lower()
            if db_pwd in WEAK_DB_PASSWORDS:
                errors.append("DATABASE_URL password uses a weak/default placeholder in staging/production.")

        origins = [o.strip() for o in (s.cors_origins or "").split(",") if o.strip()]
        if not origins:
            errors.append("CORS_ORIGINS must specify at least one explicit origin in staging/production.")
        for origin in origins:
            if origin == "*":
                errors.append("CORS_ORIGINS cannot contain wildcard '*' when credentials are enabled.")
            elif env == "production":
                p = urlsplit(origin)
                if p.scheme.lower() != "https" or p.hostname in ("localhost", "127.0.0.1"):
                    errors.append(
                        f"CORS_ORIGINS entry {origin!r} must use https:// and a non-localhost domain in production."
                    )

        if env == "production" and not s.cookie_secure:
            errors.append("COOKIE_SECURE must be true in production so session cookies require HTTPS.")

        api_key = (s.google_ai_api_key or "").strip().lower()
        if api_key in {"change-me", "your-api-key", "placeholder", "todo"}:
            errors.append("GOOGLE_AI_API_KEY contains a placeholder value; set a valid key or leave empty.")

    return errors


def enforce_startup_settings(cfg: Settings | None = None) -> None:
    """Fail fast on startup if configuration is invalid."""
    errors = validate_runtime_settings(cfg)
    if errors:
        raise RuntimeError("Invalid runtime configuration: " + "; ".join(errors))


settings = Settings()
