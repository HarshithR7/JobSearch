"""Company discovery via Google's official Custom Search JSON API — not
scraping Google's search results page, which would violate its ToS and
get rate-limited/blocked the same way LinkedIn/Indeed scraping would.
The JSON API is a legitimate, documented product with a 100-free-
queries/day tier; requires GOOGLE_CSE_KEY (API key) and GOOGLE_CSE_CX
(a Custom Search Engine ID, configured at
programmablesearchengine.google.com to search the whole web) in .env.

Off by default: daily_job_scan.py only calls this when both are set, so
a fresh clone without these two free credentials still runs fine on the
ATS/discovery collectors alone.
"""

import re

from collectors.base import RawJob
from collectors.http_utils import get_json
from config import settings

SOURCE = "google_search"

# One query per technology tag already used in the company table (see
# database/models/company.py) — keeps this aligned with Harshith's actual
# target areas rather than a generic "startup jobs" search, and spreads
# the 100/day free quota across the space that matters to him.
TECH_TAGS = [
    "RISC-V", "ASIC", "FPGA", "AI accelerator", "EDA", "photonics",
    "quantum computing hardware", "RF chip", "chiplet", "analog IC design",
]

RESULT_URL_JUNK = re.compile(r"linkedin\.com|indeed\.com|glassdoor\.com|wikipedia\.org|youtube\.com", re.IGNORECASE)


def search(query: str, num: int = 10) -> list[dict]:
    if not (settings.GOOGLE_CSE_KEY and settings.GOOGLE_CSE_CX):
        return []
    data = get_json(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": settings.GOOGLE_CSE_KEY, "cx": settings.GOOGLE_CSE_CX, "q": query, "num": num},
    )
    return (data or {}).get("items", [])


def discover_companies(tech_tags: list[str] = TECH_TAGS) -> list[dict]:
    """Runs one 'X startup careers hiring' query per tag and returns
    candidate (company_name, website, careers_url, technology_tag) dicts,
    deduped by domain. Company name is a rough guess from the result title
    — always landed with needs_review=True by the caller, same as every
    other discovery source, since this is inherently noisier than an ATS
    API returning structured data."""
    if not (settings.GOOGLE_CSE_KEY and settings.GOOGLE_CSE_CX):
        return []

    seen_domains = set()
    candidates = []
    for tag in tech_tags:
        results = search(f'"{tag}" startup careers hiring -site:linkedin.com -site:indeed.com')
        for item in results:
            link = item.get("link", "")
            if not link or RESULT_URL_JUNK.search(link):
                continue
            domain = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
            if domain in seen_domains:
                continue
            seen_domains.add(domain)

            title = item.get("title", "").split("|")[0].split(" - ")[0].split(":")[0].strip()
            candidates.append(
                {
                    "company_name": title[:120] or domain,
                    "website": domain,
                    "careers_url": link,
                    "technology_tag": tag,
                }
            )
    return candidates
