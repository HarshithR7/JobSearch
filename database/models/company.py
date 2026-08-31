from datetime import datetime

from sqlalchemy import String, Text, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base


class Company(Base):
    """Seeded from startups2(AutoRecovered).xlsx + companies_important.txt,
    then grown by discovery collectors (RemoteOK/HN/YC-style signals)."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    careers_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # greenhouse | lever | ashby | smartrecruiters | generic | none | unknown
    ats_type: Mapped[str] = mapped_column(String(32), default="unknown")
    ats_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # Widened beyond a typical short tag/country: the source spreadsheet has
    # inconsistent column alignment on some sheets, occasionally landing a
    # full free-text description in these positions.
    technology_tag: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country: Mapped[str | None] = mapped_column(String(500), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tier 1 Primary | Tier 2 High-Potential | Tier 3 Startup | Tier 4 Research
    priority_tier: Mapped[str | None] = mapped_column(String(40), nullable=True)
    visa_sponsor_known: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # startups2/importlist/discovered/manual
    source: Mapped[str] = mapped_column(String(40), default="manual")
    # free-text notes carried over from the spreadsheet ("no careers page", "mailed", ...)
    legacy_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
