from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str | None = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "job_search"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = ""

    # AI
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    # Cheaper/faster tier for high-volume, bounded-output calls (job-match
    # scoring against a fixed JSON schema) where Sonnet-level reasoning
    # isn't needed. Resume parsing/tailoring/prep generation stay on
    # ANTHROPIC_MODEL — those are low-volume and higher-stakes (a tailored
    # resume is what actually goes out to an employer).
    ANTHROPIC_MODEL_FAST: str = "claude-haiku-4-5-20251001"

    # Optional collectors
    GOOGLE_CSE_KEY: str | None = None
    GOOGLE_CSE_CX: str | None = None

    # IMAP credentials for collectors/linkedin_email_parser.py are per-
    # profile (Profile.imap_host/imap_user/imap_app_password/imap_label,
    # set on the Profiles page), not global — removed from here when that
    # became a real per-profile feature instead of dead code hardcoded to
    # one mailbox.

    # Application
    ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    GITHUB_USERNAME: str = "HarshithR7"


settings = Settings()
