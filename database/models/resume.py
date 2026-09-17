from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
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
    # {summary, experience, projects, skills} — lets a past version be
    # re-rendered as a properly-formatted .docx later (resume_tailor.
    # render_docx) instead of only the flat-text fallback. Nullable: rows
    # from before this column existed only have generated_text.
    tailored_structured: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ats_missing_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
