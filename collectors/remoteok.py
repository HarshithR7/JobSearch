"""RemoteOK public JSON feed — free, no auth, documented for this exact use
(https://remoteok.com/api). Used as a discovery source: companies posting
here that aren't already in the `company` table get added with
source='discovered'."""

from datetime import datetime

from collectors.base import RawJob, parse_iso
from collectors.http_utils import get_json

SOURCE = "remoteok"

HARDWARE_KEYWORDS = (
    "risc-v", "riscv", "fpga", "asic", "verilog", "vhdl", "semiconductor",
    "chip", "silicon", "vlsi", "soc", "rtl", "eda", "photonic", "quantum",
)


class DiscoveredJob(RawJob):
    company_name: str
    company_website: str | None


def fetch(tag_filter: tuple[str, ...] = HARDWARE_KEYWORDS) -> list[DiscoveredJob]:
    data = get_json("https://remoteok.com/api")
    if not isinstance(data, list):
        return []

    jobs: list[DiscoveredJob] = []
    for item in data[1:]:  # first element is a legal/metadata blob, not a job
        if not isinstance(item, dict) or "id" not in item:
            continue

        tags = [t.lower() for t in (item.get("tags") or [])]
        description = (item.get("description") or "").lower()
        position = (item.get("position") or "").lower()
        haystack = " ".join(tags) + " " + description[:500] + " " + position
        if tag_filter and not any(keyword in haystack for keyword in tag_filter):
            continue

        posted_at: datetime | None = parse_iso(item.get("date"))
        jobs.append(
            DiscoveredJob(
                external_id=str(item["id"]),
                title=item.get("position", ""),
                url=item.get("url", ""),
                location=item.get("location") or None,
                remote_flag=True,
                department=None,
                posted_at=posted_at,
                raw_description=item.get("description"),
                company_name=item.get("company", "").strip(),
                company_website=None,  # RemoteOK doesn't expose a company site field; leave for a human/ATS-detect pass
            )
        )
    return jobs
