"""Given a company name (and optional known careers_url), guess which ATS
it's on by probing standard slug patterns. Cheap and safe: each probe is a
single GET against a public API, no scraping involved."""

import re
import time

import requests

from collectors import ats_ashby, ats_greenhouse, ats_lever, ats_smartrecruiters, ats_workday
from collectors.http_utils import USER_AGENT, slugify

# Be a polite client: these are free, unauthenticated public APIs meant for
# embedding job boards, not built for a script probing hundreds of slug
# guesses back to back. A small delay between probes keeps a one-time
# backfill over the whole company list from looking like a burst attack.
PROBE_DELAY_SECONDS = 0.3

PROBERS = {
    "greenhouse": ats_greenhouse.probe,
    "lever": ats_lever.probe,
    "ashby": ats_ashby.probe,
    "smartrecruiters": ats_smartrecruiters.probe,
}

FETCHERS = {
    "greenhouse": ats_greenhouse.fetch,
    "lever": ats_lever.fetch,
    "ashby": ats_ashby.fetch,
    "smartrecruiters": ats_smartrecruiters.fetch,
    "workday": ats_workday.fetch,
}

WORKDAY_URL_RE = re.compile(r"([\w-]+)\.wd\d+\.myworkdayjobs\.com/([\w-]+)")

# If a careers_url already points at a known ATS-hosted board, the slug is
# usually right there in the path — try that exact slug first.
ATS_URL_PATTERNS = {
    "greenhouse": re.compile(r"(?:boards\.greenhouse\.io|greenhouse\.io/[\w-]+/jobs)/([\w-]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([\w-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([\w-]+)"),
    "smartrecruiters": re.compile(r"careers\.smartrecruiters\.com/([\w-]+)"),
}


def candidate_slugs(name: str, careers_url: str | None) -> list[str]:
    slugs = []
    if careers_url:
        for pattern in ATS_URL_PATTERNS.values():
            match = pattern.search(careers_url)
            if match:
                slugs.append(match.group(1))
    base = slugify(name)
    if base and base not in slugs:
        slugs.append(base)
    compact = base.replace("-", "")
    if compact and compact not in slugs:
        slugs.append(compact)
    return slugs


def detect(name: str, careers_url: str | None = None) -> tuple[str | None, str | None]:
    """Returns (ats_type, ats_slug), or (None, None) if nothing matched."""
    for slug in candidate_slugs(name, careers_url):
        for ats_type, probe in PROBERS.items():
            if probe(slug):
                return ats_type, slug
            time.sleep(PROBE_DELAY_SECONDS)
    return None, None


def detect_workday(website: str | None) -> str | None:
    """Workday's ats_slug is "tenant/site", not a single-word slug like the
    other ATS platforms — candidate_slugs()/PROBERS above can't find it by
    guessing. Companies host it off a separate subdomain (jobs.<company>.com
    or careers.<company>.com), not a path under the main site, so
    careers_generic's /careers-path guessing misses it too — verified
    directly: Intel's is at jobs.intel.com, redirecting to
    intel.wd1.myworkdayjobs.com. Follows the redirect and pulls tenant/site
    straight out of the final URL."""
    if not website:
        return None
    domain = website.replace("https://", "").replace("http://", "").split("/")[0]
    for subdomain in (f"jobs.{domain}", f"careers.{domain}"):
        try:
            resp = requests.get(f"https://{subdomain}", headers={"User-Agent": USER_AGENT}, timeout=8, allow_redirects=True)
        except requests.RequestException:
            continue
        match = WORKDAY_URL_RE.search(resp.url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"
    return None
