from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database.models import Profile


def list_all(db: Session) -> list[Profile]:
    return list(db.scalars(select(Profile).order_by(Profile.name)))


def get_by_name(db: Session, name: str) -> Profile | None:
    return db.scalar(select(Profile).where(Profile.name == name))


def get(db: Session, profile_id: int) -> Profile | None:
    return db.get(Profile, profile_id)


def delete_profile(db: Session, profile_id: int) -> None:
    """Deletes a profile and everything scoped to it. No ON DELETE CASCADE
    at the DB level (see migrations/versions/0001), so dependents are
    removed by hand, in FK-safe order: application_event -> application ->
    resume_version -> job_match -> linkedin_alert_email -> profile."""
    from database.models import Application, ApplicationEvent, JobMatch, LinkedInAlertEmail, ResumeVersion

    application_ids = list(
        db.scalars(select(Application.id).where(Application.profile_id == profile_id))
    )
    if application_ids:
        db.execute(delete(ApplicationEvent).where(ApplicationEvent.application_id.in_(application_ids)))
    db.execute(delete(Application).where(Application.profile_id == profile_id))
    db.execute(delete(ResumeVersion).where(ResumeVersion.profile_id == profile_id))
    db.execute(delete(JobMatch).where(JobMatch.profile_id == profile_id))
    db.execute(delete(LinkedInAlertEmail).where(LinkedInAlertEmail.profile_id == profile_id))
    db.execute(delete(Profile).where(Profile.id == profile_id))
