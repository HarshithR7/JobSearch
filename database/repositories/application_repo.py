from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Application, ApplicationEvent


def get_or_create(db: Session, profile_id: int, job_posting_id: int) -> Application:
    existing = db.scalar(
        select(Application).where(Application.profile_id == profile_id, Application.job_posting_id == job_posting_id)
    )
    if existing:
        return existing
    application = Application(profile_id=profile_id, job_posting_id=job_posting_id, status="discovered")
    db.add(application)
    db.flush()
    db.add(ApplicationEvent(application_id=application.id, status="discovered"))
    return application


def set_status(db: Session, application: Application, status: str, note: str | None = None) -> Application:
    application.status = status
    if status == "applied" and application.applied_at is None:
        application.applied_at = datetime.now(timezone.utc)
    db.add(ApplicationEvent(application_id=application.id, status=status, note=note))
    db.flush()
    return application


def list_for_profile(db: Session, profile_id: int) -> list[Application]:
    return list(
        db.scalars(select(Application).where(Application.profile_id == profile_id).order_by(Application.updated_at.desc()))
    )
