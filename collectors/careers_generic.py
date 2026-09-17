"""Best-effort fallback for companies with no recognized ATS: fetch their
careers page and heuristically pick out links that look like job postings.
Deliberately conservative — anything it finds gets Company.needs_review=True
so a human glances at it once rather than trusting a guess."""

import hashlib
import re
import warnings
from urllib.parse import urljoin

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from collectors.base import RawJob
from collectors.http_utils import get_html

# A handful of "careers" URL guesses land on a sitemap.xml or RSS feed
# instead of an actual page — harmless (BeautifulSoup still parses it,
# just finds no job-like links), but noisy without this filter.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

SOURCE = "generic"

JOB_LINK_HINT = re.compile(r"job|career|position|opening|role", re.IGNORECASE)
NAV_TEXT = re.compile(r"^(home|about|contact|careers?|jobs?|apply|open positions?)$", re.IGNORECASE)
CAREERS_LINK_TEXT = re.compile(r"career|jobs|join us|we're hiring|open positions|work with us", re.IGNORECASE)
# Real problem this heuristic can't solve without these: on a page whose
# entire URL namespace lives under /careers/..., JOB_LINK_HINT matches
# almost every internal link's href regardless of what it actually points
# to. Caught on real data: Silicon Labs' "Click Here", "View FAQs",
# "Candidate Resource Hub", "Browse Job Openings" all got ingested as if
# each were a distinct job posting.
NON_JOB_LINK_TEXT = re.compile(
    r"^(click here|view faqs?|browse .*(jobs?|positions?|openings?)|"
    r"(candidate|hiring|recruit\w*) (resource|resources?)( hub)?|"
    r"recruitment fraud disclaimer|privacy policy|terms of (use|service)|"
    r"search (jobs?|openings?|positions?)|sign ?in|log ?in|create account|"
    r"apply now|(see|view|browse) open(ing)?s?( roles?| positions?)?|open roles?|"
    r"join( us)?( now)?|join our (talent )?(community|network)|"
    r"(feel the difference|ai at work|explore (options|benefits)|why work here|"
    r"career growth and learning|benefits and perks)|initiativbewerbung.*)$",
    re.IGNORECASE,
)
# Workday, and other JS-rendered SPA job boards, don't put job listings in
# the initial HTML at all — the list loads via a JS API call after the
# page loads. A static fetch()+BeautifulSoup can only ever see the shell
# page's nav links for these, which is exactly the false-positive pattern
# above, no matter how the text/href heuristic is tuned. Skip ingesting
# from these domains entirely rather than ingest nav-link garbage.
JS_RENDERED_ATS_DOMAINS = ("myworkdayjobs.com", "successfactors.com", "icims.com", "taleo.net")
# Some sites' location-filter links get caught by JOB_LINK_HINT (href
# under /careers/) with nothing job-title-like about the anchor text
# itself — e.g. "Southampton, UK", "West Coast, United States".
LOCATION_LIKE_TITLE = re.compile(r"^[A-Za-z .'-]+,\s*(UK|USA|US|United States|United Kingdom|[A-Z]{2})$")
MIN_TITLE_WORDS = 2
MAX_TITLE_WORDS = 12
COMMON_CAREERS_PATHS = ("/careers", "/jobs", "/careers/", "/join-us", "/company/careers", "/about/careers", "/about-us/careers")


def _normalize(website: str) -> str:
    return website if website.startswith(("http://", "https://")) else f"https://{website}"


def discover_careers_url(website: str) -> str | None:
    """Given just a company's homepage domain (all we have from the seed
    spreadsheet — it never included direct careers-page URLs), find a
    plausible careers page: try common path guesses first, then fall back
    to following a 'Careers'/'Jobs' nav link found on the homepage itself.
    Returns None rather than guessing wrong if nothing looks right."""
    base = _normalize(website)

    for path in COMMON_CAREERS_PATHS:
        html = get_html(base.rstrip("/") + path, timeout=8)
        if html and JOB_LINK_HINT.search(html):
            return base.rstrip("/") + path

    home_html = get_html(base, timeout=8)
    if not home_html:
        return None

    soup = BeautifulSoup(home_html, "lxml")
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(strip=True)
        if CAREERS_LINK_TEXT.search(text) or CAREERS_LINK_TEXT.search(anchor["href"]):
            return urljoin(base, anchor["href"])

    return None


def fetch(careers_url: str) -> list[RawJob]:
    if any(domain in careers_url for domain in JS_RENDERED_ATS_DOMAINS):
        return []

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
        if NAV_TEXT.match(text) or NON_JOB_LINK_TEXT.match(text) or LOCATION_LIKE_TITLE.match(text):
            continue

        href = anchor["href"]
        if any(domain in href for domain in JS_RENDERED_ATS_DOMAINS):
            continue
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
