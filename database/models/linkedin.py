from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class LinkedInAlertEmail(Base):
    """Dedupe table for linkedin_email_parser.py — one row per email
    message-id already ingested, so re-running the parser is a no-op."""

    __tablename__ = "linkedin_alert_email"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    message_id: Mapped[str] = mapped_column(String(500), unique=True)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
