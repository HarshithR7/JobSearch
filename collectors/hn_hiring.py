"""Hacker News monthly 'Who is Hiring?' thread, via the public Algolia HN
Search API (no auth, documented at hn.algolia.com/api). Each top-level
comment is one job post in free text — extraction is heuristic (first
line is conventionally 'Company Name | Role | Location | Remote') so
these land as needs_review candidates, not confirmed postings."""

import re

from collectors.base import RawJob
from collectors.http_utils import get_json

SOURCE = "hn_hiring"

HARDWARE_KEYWORDS = (
    "risc-v", "riscv", "fpga", "asic", "verilog", "vhdl", "semiconductor",
    "chip", "silicon", "vlsi", "soc", "rtl", "hardware",
)


class DiscoveredJob(RawJob):
    company_name: str


def _latest_thread_id() -> int | None:
    data = get_json(
        'https://hn.algolia.com/api/v1/search_by_date'
        '?query=Who%20is%20Hiring&tags=story,author_whoishiring&hitsPerPage=1'
    )
    hits = (data or {}).get("hits") or []
    return int(hits[0]["objectID"]) if hits else None


def fetch(tag_filter: tuple[str, ...] = HARDWARE_KEYWORDS) -> list[DiscoveredJob]:
    thread_id = _latest_thread_id()
    if thread_id is None:
        return []

    thread = get_json(f"https://hn.algolia.com/api/v1/items/{thread_id}")
    if not thread:
        return []

    jobs: list[DiscoveredJob] = []
    for comment in thread.get("children", []):
        text = comment.get("text") or ""
        if not text or comment.get("dead") or comment.get("deleted"):
            continue
        plain = re.sub("<[^<]+?>", " ", text)
        if tag_filter and not any(keyword in plain.lower() for keyword in tag_filter):
            continue

        first_line = plain.strip().split("\n")[0]
        company_name = re.split(r"[|–—-]", first_line)[0].strip()[:120] or "Unknown"

        jobs.append(
            DiscoveredJob(
                external_id=str(comment["id"]),
                title=first_line[:200],
                url=f"https://news.ycombinator.com/item?id={comment['id']}",
                location=None,
                remote_flag="remote" in plain.lower(),
                department=None,
                posted_at=None,
                raw_description=plain[:5000],
                company_name=company_name,
            )
        )
    return jobs
