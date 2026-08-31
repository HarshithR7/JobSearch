from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class JobPosting(Base):
    __tablename__ = "job_posting"
    __table_args__ = (UniqueConstraint("company_id", "external_id", name="uq_job_company_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("company.id"))

    # id/slug the source system uses (Greenhouse job id, Lever posting id, URL hash for generic scrapes, ...)
    external_id: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(40))  # greenhouse|lever|ashby|smartrecruiters|generic|remoteok|hn|linkedin_alert
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remote_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tech_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    status: Mapped[str] = mapped_column(String(20), default="live")  # live|stale|closed
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobSnapshot(Base):
    """One row per time we observed a posting's description — lets the UI
    flag 'this job description changed since you last saw it'."""

    __tablename__ = "job_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.id"))
    description_hash: Mapped[str] = mapped_column(String(64))
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
