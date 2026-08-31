"""Lever public Postings API. No auth needed:
https://api.lever.co/v0/postings/{slug}?mode=json
"""

from datetime import datetime, timezone

from collectors.base import RawJob, looks_remote
from collectors.http_utils import get_json

SOURCE = "lever"


def probe(slug: str) -> bool:
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=6)
    return isinstance(data, list)


def fetch(slug: str) -> list[RawJob] | None:
    """None on request/API failure; a list (possibly empty) on success."""
    data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(data, list):
        return None

    jobs: list[RawJob] = []
    for item in data:
        categories = item.get("categories") or {}
        location = categories.get("location")
        posted_ms = item.get("createdAt")
        posted_at = datetime.fromtimestamp(posted_ms / 1000, tz=timezone.utc) if posted_ms else None
        jobs.append(
            RawJob(
                external_id=str(item["id"]),
                title=item.get("text", ""),
                url=item.get("hostedUrl", ""),
                location=location,
                remote_flag=looks_remote(location) or (categories.get("commitment") == "Remote"),
                department=categories.get("team"),
                posted_at=posted_at,
                raw_description=item.get("descriptionPlain") or item.get("description"),
            )
        )
    return jobs
