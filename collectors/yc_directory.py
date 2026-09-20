"""Y Combinator's own company directory, via the community-maintained JSON
mirror at yc-oss.github.io/api (rebuilt regularly from YC's public
Algolia-backed directory — no scraping/auth, plain JSON, ~6,200 companies
with website/industry/tags/isHiring). This is company *discovery* only:
YC doesn't publish individual job postings, so matches land as
needs_review candidates the same way RemoteOK/HN discoveries do — their
website then gets run through ats_detect / careers_generic like any other
newly discovered company to actually pull postings.

Filtered to status == "Active" and isHiring == True by default: YC marks
this themselves, and scanning every inactive/acquired/not-hiring company
in a 6,000+ row directory daily would mostly add dead weight.
"""

from collectors.http_utils import get_json

SOURCE = "yc"
DIRECTORY_URL = "https://yc-oss.github.io/api/companies/all.json"

# Reused as the default hardware-side keyword set the same way remoteok.py /
# hn_hiring.py define their own — daily_job_scan.py extends this with each
# profile's own target_tech_tags before calling fetch_companies(), same
# pattern as the other discovery collectors.
HARDWARE_KEYWORDS = (
    "semiconductor", "chip", "asic", "fpga", "risc-v", "riscv", "silicon",
    "hardware", "vlsi", "soc", "photonics", "quantum",
)


class DiscoveredCompany(dict):
    """name, website, one_liner, industry, tags — enough to seed
    Company + let the ATS-detection pipeline take it from there."""


def _blob(company: dict) -> str:
    return " ".join(filter(None, [
        company.get("industry") or "",
        company.get("subindustry") or "",
        " ".join(company.get("tags") or []),
        company.get("one_liner") or "",
    ])).lower()


def fetch_companies(
    tag_filter: tuple[str, ...] = HARDWARE_KEYWORDS,
    only_hiring: bool = True,
) -> list[DiscoveredCompany]:
    data = get_json(DIRECTORY_URL)
    if not data:
        return []

    results = []
    for company in data:
        if company.get("status") != "Active":
            continue
        if only_hiring and not company.get("isHiring"):
            continue
        if not company.get("website"):
            continue
        if tag_filter and not any(keyword in _blob(company) for keyword in tag_filter):
            continue
        results.append(DiscoveredCompany(
            name=company["name"],
            website=company["website"],
            one_liner=company.get("one_liner"),
            industry=company.get("industry"),
            tags=company.get("tags") or [],
        ))
    return results
