"""Greenhouse public job-board API. No auth needed:
https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
"""

from collectors.base import RawJob, parse_iso, looks_remote
from collectors.http_utils import get_json

SOURCE = "greenhouse"


def probe(slug: str) -> bool:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=6)
    return isinstance(data, dict) and "jobs" in data


def fetch(slug: str) -> list[RawJob] | None:
    """Returns None on request/API failure (so the caller doesn't wrongly
    treat a transient outage as 'all postings closed'), or a list (possibly
    empty, meaning confirmed zero open jobs) on success."""
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if data is None or "jobs" not in data:
        return None

    jobs: list[RawJob] = []
    for item in data["jobs"]:
        location = (item.get("location") or {}).get("name")
        jobs.append(
            RawJob(
                external_id=str(item["id"]),
                title=item.get("title", ""),
                url=item.get("absolute_url", ""),
                location=location,
                remote_flag=looks_remote(location),
                department=(item.get("departments") or [{}])[0].get("name"),
                posted_at=parse_iso(item.get("updated_at")),
                raw_description=item.get("content"),
            )
        )
    return jobs
