from datetime import datetime

from sqlalchemy import Integer, Text, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

from database.base import Base


class JobMatch(Base):
    """Weighted 0-100 match score for (job_posting, profile) — see
    analysis/job_matcher.py for the scoring rubric."""

    __tablename__ = "job_match"
    __table_args__ = (UniqueConstraint("job_posting_id", "profile_id", name="uq_match_job_profile"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_posting.id"))
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id"))

    overall_score: Mapped[int] = mapped_column(Integer)
    sub_scores: Mapped[dict] = mapped_column(JSONB)  # {"required_skills": 22, "experience": 18, ...}
    band: Mapped[str] = mapped_column(String(30))  # apply_immediately|strong|worth_considering|stretch|low_priority

    matched_skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    missing_skills: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
