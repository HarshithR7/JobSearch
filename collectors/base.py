from datetime import datetime
from typing import TypedDict


class RawJob(TypedDict, total=False):
    external_id: str
    title: str
    url: str
    location: str | None
    remote_flag: bool | None
    department: str | None
    posted_at: datetime | None
    raw_description: str | None


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def looks_remote(location: str | None) -> bool | None:
    if not location:
        return None
    return "remote" in location.lower()
