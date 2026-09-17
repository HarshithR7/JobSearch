from sqlalchemy import select, func
from sqlalchemy.orm import Session

from database.models import Company


def get_by_name(db: Session, name: str) -> Company | None:
    return db.scalar(select(Company).where(func.lower(Company.name) == name.strip().lower()))


def upsert(db: Session, **fields) -> Company:
    """Insert a company or merge non-empty fields into an existing one,
    matched by name. Used by seed_companies.py and discovery collectors."""
    existing = get_by_name(db, fields["name"])
    if existing is None:
        company = Company(**fields)
        db.add(company)
        db.flush()
        return company

    for key, value in fields.items():
        if value not in (None, ""):
            setattr(existing, key, value)
    db.flush()
    return existing


def list_with_known_ats(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).where(Company.ats_type.in_(["greenhouse", "lever", "ashby", "smartrecruiters", "workday"]))))


def list_all(db: Session) -> list[Company]:
    return list(db.scalars(select(Company).order_by(Company.name)))
