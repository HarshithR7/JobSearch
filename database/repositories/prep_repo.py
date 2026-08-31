from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import RoleArchetype, PrepContent

STALE_AFTER_DAYS = 30


def get_or_create_archetype(db: Session, name: str, tech_tag: str | None = None) -> RoleArchetype:
    existing = db.scalar(select(RoleArchetype).where(RoleArchetype.name == name))
    if existing:
        return existing
    archetype = RoleArchetype(name=name, tech_tag=tech_tag)
    db.add(archetype)
    db.flush()
    return archetype


def get_fresh_content(db: Session, role_archetype_id: int) -> PrepContent | None:
    content = db.scalar(select(PrepContent).where(PrepContent.role_archetype_id == role_archetype_id))
    if content is None:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)
    if content.generated_at.replace(tzinfo=timezone.utc) < cutoff:
        return None
    return content


def upsert_content(db: Session, role_archetype_id: int, **fields) -> PrepContent:
    existing = db.scalar(select(PrepContent).where(PrepContent.role_archetype_id == role_archetype_id))
    if existing is None:
        content = PrepContent(role_archetype_id=role_archetype_id, **fields)
        db.add(content)
        db.flush()
        return content
    for key, value in fields.items():
        setattr(existing, key, value)
    existing.generated_at = datetime.now(timezone.utc)
    db.flush()
    return existing
