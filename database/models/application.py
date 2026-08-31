from datetime import datetime, date

from sqlalchemy import String, Text, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base

# Discovered -> Interested -> Resume Prepared -> Applied -> OA ->
# Recruiter Screen -> Interview -> Final -> Offer | Rejected
APPLICATION_STATUSES = [
    "discovered",
    "interested",
    "resume_prepared",
    "applied",
    "oa",
    "recruiter_screen",
    "interview",
    "final",
    "offer",
    "rejected",
]


class Application(Base):
    __tablename__ = "application"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.id"))

    status: Mapped[str] = mapped_column(String(30), default="discovered")
    resume_version_id: Mapped[int | None] = mapped_column(ForeignKey("resume_version.id"), nullable=True)
    cover_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recruiter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    referral: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ApplicationEvent(Base):
    """Timestamped history of status transitions for one application."""

    __tablename__ = "application_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
