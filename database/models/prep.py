from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class RoleArchetype(Base):
    """Normalized role cluster (e.g. 'RISC-V Verification Engineer',
    'Analog IC Design Engineer') so prep content is generated once per
    archetype, not once per job posting."""

    __tablename__ = "role_archetype"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    tech_tag: Mapped[str | None] = mapped_column(String(120), nullable=True)


class PrepContent(Base):
    __tablename__ = "prep_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_archetype_id: Mapped[int] = mapped_column(ForeignKey("role_archetype.id"), unique=True)

    books: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    topics: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    courses: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    sample_qna: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)  # [{"q": ..., "a": ...}]

    model_used: Mapped[str | None] = mapped_column(String(80), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
