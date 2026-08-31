from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import JobMatch


def upsert(db: Session, job_posting_id: int, profile_id: int, **fields) -> JobMatch:
    existing = db.scalar(
        select(JobMatch).where(JobMatch.job_posting_id == job_posting_id, JobMatch.profile_id == profile_id)
    )
    if existing is None:
        match = JobMatch(job_posting_id=job_posting_id, profile_id=profile_id, **fields)
        db.add(match)
        db.flush()
        return match

    for key, value in fields.items():
        setattr(existing, key, value)
    db.flush()
    return existing


def top_for_profile(db: Session, profile_id: int, limit: int = 50) -> list[JobMatch]:
    return list(
        db.scalars(
            select(JobMatch)
            .where(JobMatch.profile_id == profile_id)
            .order_by(JobMatch.overall_score.desc())
            .limit(limit)
        )
    )
