import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import JobPosting, JobSnapshot


def upsert_posting(db: Session, company_id: int, external_id: str, source: str, **fields) -> tuple[JobPosting, bool]:
    """Insert a new posting or refresh an existing one (matched by
    company_id + external_id). Returns (posting, is_new). Also records a
    JobSnapshot whenever the description text actually changed."""
    existing = db.scalar(
        select(JobPosting).where(
            JobPosting.company_id == company_id,
            JobPosting.external_id == external_id,
        )
    )
    now = datetime.now(timezone.utc)
    description = fields.get("raw_description") or ""
    description_hash = hashlib.sha256(description.encode("utf-8")).hexdigest()

    if existing is None:
        posting = JobPosting(
            company_id=company_id,
            external_id=external_id,
            source=source,
            first_seen_at=now,
            last_seen_at=now,
            status="live",
            **fields,
        )
        db.add(posting)
        db.flush()
        db.add(JobSnapshot(job_posting_id=posting.id, description_hash=description_hash, description_text=description))
        return posting, True

    existing.last_seen_at = now
    existing.status = "live"
    changed = False
    for key, value in fields.items():
        if value not in (None, "") and getattr(existing, key, None) != value:
            setattr(existing, key, value)
            changed = True

    last_snapshot = db.scalar(
        select(JobSnapshot)
        .where(JobSnapshot.job_posting_id == existing.id)
        .order_by(JobSnapshot.seen_at.desc())
    )
    if last_snapshot is None or last_snapshot.description_hash != description_hash:
        db.add(JobSnapshot(job_posting_id=existing.id, description_hash=description_hash, description_text=description))

    return existing, False


def mark_stale_not_seen_since(db: Session, company_id: int, cutoff: datetime) -> int:
    """Closes postings for a company that weren't refreshed in this scan
    (i.e. no longer returned by the source) — best-effort 'closed' detection."""
    postings = db.scalars(
        select(JobPosting).where(
            JobPosting.company_id == company_id,
            JobPosting.status == "live",
            JobPosting.last_seen_at < cutoff,
        )
    ).all()
    for posting in postings:
        posting.status = "closed"
    return len(postings)


def list_live(db: Session, limit: int = 500) -> list[JobPosting]:
    return list(
        db.scalars(
            select(JobPosting).where(JobPosting.status == "live").order_by(JobPosting.first_seen_at.desc()).limit(limit)
        )
    )
