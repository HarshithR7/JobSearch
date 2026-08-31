from datetime import datetime

from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class SourceRunLog(Base):
    """One row per daily_job_scan.py run per source, for debugging why a
    company stopped showing new postings."""

    __tablename__ = "source_run_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(40))
    companies_checked: Mapped[int] = mapped_column(Integer, default=0)
    new_postings_found: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
