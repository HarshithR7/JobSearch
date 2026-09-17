"""Workday CXS API — many large enterprises (Intel, and others) host their
careers site on Workday, which is a JS-rendered SPA: the raw HTML never
contains job listings, only a shell page (see collectors/careers_generic.py's
JS_RENDERED_ATS_DOMAINS, which skips these rather than ingest nav-link
garbage). But Workday's frontend itself calls a documented-shape JSON API
to populate the list — this hits that same API directly, no browser/JS
needed. Verified against the real Intel tenant before building this:
POST .../wday/cxs/intel/External/jobs returned 604 real postings with
correct titles, locations, and URLs.

slug format: "tenant/site", e.g. "intel/External" — both are visible in
a Workday careers URL: https://<tenant>.wd1.myworkdayjobs.com/<site>/...
wd1/wd3/wd5 etc. vary by company; probe() tries the common ones.

Deliberately list-only (title/location/url/posted-relative-text), no
per-job description fetch: that would be a second API call per posting,
and a company can have 600+ open roles — not worth the request volume
for a first pass. raw_description stays None here, same tradeoff
careers_generic/hn_hiring already make."""

import re
from datetime import datetime, timedelta, timezone

from collectors.base import RawJob
from collectors.http_utils import post_json

SOURCE = "workday"

WD_HOST_CANDIDATES = ("wd1", "wd3", "wd5")
PAGE_SIZE = 20  # Workday's CXS API rejects (400) any limit above 20 — verified directly
MAX_JOBS = 500  # generous cap — a company with more than this is an edge case, not worth unbounded pagination

_DAYS_AGO_RE = re.compile(r"posted\s+(\d+)\+?\s+days?\s+ago", re.IGNORECASE)


def _jobs_url(tenant: str, site: str, wd_host: str) -> str:
    return f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"


def _resolve_host(tenant: str, site: str) -> str | None:
    for wd_host in WD_HOST_CANDIDATES:
        data = post_json(_jobs_url(tenant, site, wd_host), json_body={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}, timeout=8)
        if data and "jobPostings" in data:
            return wd_host
    return None


def probe(slug: str) -> bool:
    if "/" not in slug:
        return False
    tenant, site = slug.split("/", 1)
    return _resolve_host(tenant, site) is not None


def _parse_posted_at(posted_text: str | None) -> datetime | None:
    """Workday gives relative text ("Posted 3 Days Ago", "Posted Today",
    "Posted 30+ Days Ago") in the list endpoint, not an absolute date —
    approximate only, good enough for a freshness signal."""
    if not posted_text:
        return None
    text = posted_text.strip().lower()
    now = datetime.now(timezone.utc)
    if "today" in text:
        return now
    match = _DAYS_AGO_RE.search(text)
    if match:
        return now - timedelta(days=int(match.group(1)))
    return None


def fetch(slug: str) -> list[RawJob] | None:
    if "/" not in slug:
        return None
    tenant, site = slug.split("/", 1)
    wd_host = _resolve_host(tenant, site)
    if wd_host is None:
        return None

    jobs: list[RawJob] = []
    offset = 0
    total = None
    while offset < MAX_JOBS:
        data = post_json(
            _jobs_url(tenant, site, wd_host),
            json_body={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
        )
        if data is None:
            return jobs or None
        postings = data.get("jobPostings", [])
        if not postings:
            break
        # total in the response is only reliable on the first page — every
        # subsequent page came back with total=0 despite still returning
        # real postings (verified directly against the live Intel tenant),
        # which made offset >= total trigger a false-early break after just
        # 2 pages (40 of 604 real jobs). Pin it from page one instead of
        # re-reading it each time.
        if total is None:
            total = data.get("total", 0)
        for item in postings:
            path = item.get("externalPath", "")
            jobs.append(
                RawJob(
                    external_id=path.rsplit("_", 1)[-1] or path,  # trailing JRxxxxxx requisition id
                    title=item.get("title", ""),
                    url=f"https://{tenant}.{wd_host}.myworkdayjobs.com/{site}{path}",
                    location=item.get("locationsText"),
                    remote_flag=None,
                    department=None,
                    posted_at=_parse_posted_at(item.get("postedOn")),
                    raw_description=None,
                )
            )
        offset += PAGE_SIZE
        if offset >= total:
            break

    return jobs
