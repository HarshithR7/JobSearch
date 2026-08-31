"""Ashby public Job Board API. No auth needed:
https://api.ashbyhq.com/posting-api/job-board/{slug}
"""

from collectors.base import RawJob, looks_remote
from collectors.http_utils import get_json

SOURCE = "ashby"


def probe(slug: str) -> bool:
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=6)
    return isinstance(data, dict) and "jobs" in data


def fetch(slug: str) -> list[RawJob] | None:
    """None on request/API failure; a list (possibly empty) on success."""
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if data is None or "jobs" not in data:
        return None

    jobs: list[RawJob] = []
    for item in data["jobs"]:
        location = item.get("location")
        jobs.append(
            RawJob(
                external_id=item.get("id", ""),
                title=item.get("title", ""),
                url=item.get("jobUrl", ""),
                location=location,
                remote_flag=item.get("isRemote", looks_remote(location)),
                department=item.get("department"),
                posted_at=None,
                raw_description=item.get("descriptionPlain") or item.get("descriptionHtml"),
            )
        )
    return jobs
