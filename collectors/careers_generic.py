"""Best-effort fallback for companies with no recognized ATS: fetch their
careers page and heuristically pick out links that look like job postings.
Deliberately conservative — anything it finds gets Company.needs_review=True
so a human glances at it once rather than trusting a guess."""

import hashlib
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.base import RawJob
from collectors.http_utils import get_html

SOURCE = "generic"

JOB_LINK_HINT = re.compile(r"job|career|position|opening|role", re.IGNORECASE)
NAV_TEXT = re.compile(r"^(home|about|contact|careers?|jobs?|apply|open positions?)$", re.IGNORECASE)
MIN_TITLE_WORDS = 2
MAX_TITLE_WORDS = 12


def fetch(careers_url: str) -> list[RawJob]:
    html = get_html(careers_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    jobs: list[RawJob] = []
    seen_urls = set()

    for anchor in soup.find_all("a", href=True):
        text = " ".join(anchor.get_text(strip=True).split())
        word_count = len(text.split())
        if not (MIN_TITLE_WORDS <= word_count <= MAX_TITLE_WORDS):
            continue
        if NAV_TEXT.match(text):
            continue

        href = anchor["href"]
        looks_like_job = bool(JOB_LINK_HINT.search(href)) or bool(JOB_LINK_HINT.search(text))
        if not looks_like_job:
            continue

        url = urljoin(careers_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        jobs.append(
            RawJob(
                external_id=hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
                title=text,
                url=url,
                location=None,
                remote_flag=None,
                department=None,
                posted_at=None,
                raw_description=None,
            )
        )

    return jobs
