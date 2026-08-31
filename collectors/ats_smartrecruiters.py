"""SmartRecruiters public Postings API. No auth needed:
https://api.smartrecruiters.com/v1/companies/{slug}/postings
"""

from collectors.base import RawJob, parse_iso, looks_remote
from collectors.http_utils import get_json

SOURCE = "smartrecruiters"


def probe(slug: str) -> bool:
    data = get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", timeout=6)
    return isinstance(data, dict) and "content" in data


def fetch(slug: str) -> list[RawJob] | None:
    """None on request/API failure; a list (possibly empty) on success."""
    data = get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings")
    if data is None or "content" not in data:
        return None

    jobs: list[RawJob] = []
    for item in data["content"]:
        location_obj = item.get("location") or {}
        location = ", ".join(filter(None, [location_obj.get("city"), location_obj.get("country")])) or None
        jobs.append(
            RawJob(
                external_id=item.get("id", ""),
                title=item.get("name", ""),
                url=(item.get("ref") or {}).get("jobAd", item.get("jobAdUrl", "")),
                location=location,
                remote_flag=location_obj.get("remote") or looks_remote(location),
                department=(item.get("department") or {}).get("label"),
                posted_at=parse_iso(item.get("releasedDate")),
                raw_description=None,  # requires a second call to the postings/{id} detail endpoint
            )
        )
    return jobs
