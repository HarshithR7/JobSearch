from datetime import datetime

from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Profile(Base):
    """One row per person using the portal (Harshith, a friend, ...)."""

    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Immutable master resume — the single source of truth resume_tailor.py
    # is constrained to. Never overwritten; re-uploading creates a new
    # profile-level version instead (kept simple as a single latest field
    # for Phase 1 — full history isn't needed until Phase 5 A/B testing).
    resume_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_structured: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resume_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    target_roles: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    target_tech_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    visa_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_preference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_username: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
