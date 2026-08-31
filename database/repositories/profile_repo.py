from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Profile


def list_all(db: Session) -> list[Profile]:
    return list(db.scalars(select(Profile).order_by(Profile.name)))


def get_by_name(db: Session, name: str) -> Profile | None:
    return db.scalar(select(Profile).where(Profile.name == name))


def get(db: Session, profile_id: int) -> Profile | None:
    return db.get(Profile, profile_id)
