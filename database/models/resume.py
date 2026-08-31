from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class ResumeVersion(Base):
    """A tailored resume generated for one job (or None job_posting_id for
    a general refresh). Never overwritten — every generation is a new row,
    giving an audit trail of what was actually sent for which job."""

    __tablename__ = "resume_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))
    job_posting_id: Mapped[int | None] = mapped_column(ForeignKey("job_posting.id"), nullable=True)

    generated_text: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ats_missing_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
