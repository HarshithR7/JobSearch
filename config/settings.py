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


def _streamlit_secrets() -> dict:
    """Streamlit Community Cloud secrets go into st.secrets — whether
    they're also reliably injected into os.environ (which BaseSettings
    reads by default, same as the local .env file) shouldn't be assumed
    without verifying for the exact deployment context, and a
    misconfigured/unsaved secret there silently falls back to this
    class's defaults (DB_HOST="localhost") rather than erroring — that's
    exactly what caused a real deploy failure: psycopg2 trying to connect
    to localhost instead of the real Neon DATABASE_URL. Reading st.secrets
    directly removes the dependency on that assumption entirely. Safe to
    call outside Streamlit too (CLI/scripts/main.py): importing streamlit
    doesn't require a running app, and accessing .secrets without a
    secrets.toml present raises, which the broad except below absorbs."""
    try:
        import streamlit as st
        return dict(st.secrets)
    except Exception:
        return {}


settings = Settings(**_streamlit_secrets())
