"""The daily pipeline: for every seeded/discovered company, pull live
postings from its known ATS (or best-effort careers page), dedupe,
mark closed postings that disappeared, then run discovery collectors to
find companies not yet tracked. Meant to be invoked by
.github/workflows/daily-job-scan.yml, or manually via `python main.py scan-jobs`.
"""

from datetime import datetime, timezone

from config import logger
from database.session import get_session
from database.models import Company, SourceRunLog
from database.repositories import company_repo, job_repo, profile_repo
from collectors import ats_detect, careers_generic, google_search, hn_hiring, remoteok
from collectors.ats_detect import FETCHERS


def _profile_tech_tags() -> list[str]:
    """Aggregates target_tech_tags across every profile, not just one —
    the discovery collectors below default to a hardcoded semiconductor/
    hardware keyword list (Harshith's own domain), which means a second
    profile with a different background (e.g. web/software, finance,
    biotech) would never get relevant companies discovered at all. This
    extends discovery with whatever every profile actually says they're
    targeting, on top of (not instead of) the original defaults."""
    with get_session() as db:
        profiles = profile_repo.list_all(db)
    tags: list[str] = []
    seen = set()
    for p in profiles:
        for tag in (p.target_tech_tags or []):
            cleaned = tag.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                tags.append(cleaned)
    return tags


def _scan_known_ats_companies() -> tuple[int, int, dict]:
    checked = 0
    new_postings = 0
    errors: dict[str, str] = {}
    run_start = datetime.now(timezone.utc)

    with get_session() as db:
        companies = company_repo.list_with_known_ats(db)

    for company in companies:
        fetcher = FETCHERS.get(company.ats_type)
        if fetcher is None:
            continue
        checked += 1
        jobs = fetcher(company.ats_slug)
        if jobs is None:
            errors[company.name] = f"{company.ats_type} fetch failed"
            continue

        with get_session() as db:
            for job in jobs:
                _, is_new = job_repo.upsert_posting(
                    db,
                    company_id=company.id,
                    external_id=job["external_id"],
                    source=company.ats_type,
                    title=job.get("title", ""),
                    url=job.get("url", ""),
                    location=job.get("location"),
                    remote_flag=job.get("remote_flag"),
                    department=job.get("department"),
                    posted_at=job.get("posted_at"),
                    raw_description=job.get("raw_description"),
                )
                if is_new:
                    new_postings += 1
            closed = job_repo.mark_stale_not_seen_since(db, company.id, run_start)
            company.last_checked_at = run_start

        if closed:
            logger.info(f"{company.name}: closed {closed} postings no longer listed")

    return checked, new_postings, errors


def _detect_ats_for_unknown_companies(limit: int = 30) -> int:
    """Tries to identify the ATS for companies still marked 'unknown'.

    One session per company, committed immediately after each — this loop
    is network-bound (each company can take several seconds across probe
    attempts) and holding a single DB session/transaction open across the
    whole batch risks the DB closing an idle connection before anything
    gets committed, silently losing all progress. Committing per-company
    also means a mid-run crash keeps everything done so far.
    """
    with get_session() as db:
        unknown_ids = [c.id for c in company_repo.list_all(db) if c.ats_type == "unknown"][:limit]

    detected = 0
    for i, company_id in enumerate(unknown_ids, start=1):
        if i % 25 == 0:
            logger.info(f"ATS detection progress: {i}/{len(unknown_ids)} companies checked, {detected} detected so far")
        with get_session() as db:
            company = db.get(Company, company_id)
            name, careers_url = company.name, company.careers_url

        ats_type, slug = ats_detect.detect(name, careers_url)

        with get_session() as db:
            company = db.get(Company, company_id)
            if ats_type:
                company.ats_type = ats_type
                company.ats_slug = slug
                detected += 1
            else:
                company.ats_type = "none"
    return detected


def _discover_careers_urls(limit: int = 40) -> int:
    """The seed spreadsheet only ever had a company's homepage (`website`),
    never a direct careers-page URL — so this finds one, once, for
    companies that don't have `ats_type` in (greenhouse/lever/ashby/
    smartrecruiters) and haven't been probed yet. One session per company,
    same reasoning as _detect_ats_for_unknown_companies: this is
    network-bound and must not hold one transaction open across the whole
    batch. Companies where nothing plausible is found are marked
    ats_type='none' with careers_url still null, so they're not re-probed
    every run forever (a human can always add a careers_url by hand on
    the Companies page to force a retry)."""
    with get_session() as db:
        target_ids = [
            c.id for c in company_repo.list_all(db)
            if c.ats_type in ("unknown", "none") and c.careers_url is None and c.website
        ][:limit]

    found = 0
    for i, company_id in enumerate(target_ids, start=1):
        if i % 25 == 0:
            logger.info(f"Careers-URL discovery progress: {i}/{len(target_ids)}, {found} found so far")

        with get_session() as db:
            company = db.get(Company, company_id)
            website = company.website

        careers_url = careers_generic.discover_careers_url(website)

        with get_session() as db:
            company = db.get(Company, company_id)
            if careers_url:
                company.careers_url = careers_url
                company.ats_type = "generic"
                found += 1
            else:
                company.ats_type = "none"
    return found


def _scan_generic_careers_pages(limit: int = 60) -> int:
    """Fetches postings for companies with a discovered careers_url.
    Always flags results needs_review — the extraction is heuristic (see
    collectors/careers_generic.py), so a human glances at it once rather
    than trusting a guess. Unlike the ATS scan, this doesn't call
    mark_stale_not_seen_since: a generic HTML scrape is far more likely to
    miss a still-open posting (pagination, JS-rendered listings, a
    slightly different page layout) than an ATS API is, so treating "not
    found this time" as "closed" would be unreliable here."""
    new_postings = 0
    with get_session() as db:
        targets = [
            (c.id, c.careers_url) for c in company_repo.list_all(db)
            if c.ats_type == "generic" and c.careers_url
        ][:limit]

    for company_id, careers_url in targets:
        jobs = careers_generic.fetch(careers_url)
        if not jobs:
            continue
        with get_session() as db:
            db_company = db.get(Company, company_id)
            db_company.needs_review = True
            for job in jobs:
                _, is_new = job_repo.upsert_posting(
                    db,
                    company_id=db_company.id,
                    external_id=job["external_id"],
                    source="generic",
                    title=job.get("title", ""),
                    url=job.get("url", ""),
                )
                if is_new:
                    new_postings += 1
    return new_postings


def _discover_via_google() -> int:
    """Google Custom Search JSON API (not scraping google.com — see
    collectors/google_search.py for why that distinction matters). Only
    runs if GOOGLE_CSE_KEY/GOOGLE_CSE_CX are set; a fresh checkout without
    those free credentials just skips this and relies on RemoteOK/HN.
    Candidates come with a real careers_url already, so this fetches
    postings immediately rather than waiting for the next
    _discover_careers_urls pass."""
    extra_tags = _profile_tech_tags()
    tags = list(dict.fromkeys(google_search.TECH_TAGS + extra_tags))  # dedupe, preserve order
    candidates = google_search.discover_companies(tags)
    discovered = 0
    for candidate in candidates:
        with get_session() as db:
            company = company_repo.upsert(
                db,
                name=candidate["company_name"],
                website=candidate["website"],
                careers_url=candidate["careers_url"],
                technology_tag=candidate["technology_tag"],
                ats_type="generic",
                source="discovered",
                needs_review=True,
            )
            company_id = company.id

        jobs = careers_generic.fetch(candidate["careers_url"])
        if not jobs:
            continue
        with get_session() as db:
            for job in jobs:
                _, is_new = job_repo.upsert_posting(
                    db, company_id=company_id, external_id=job["external_id"], source="generic",
                    title=job.get("title", ""), url=job.get("url", ""),
                )
                if is_new:
                    discovered += 1
    return discovered


def _discover_new_companies() -> int:
    """RemoteOK + HN Who's Hiring, filtered to hardware/AI-chip keywords
    plus every profile's own target_tech_tags — grows the company list
    beyond the seeded spreadsheet, and beyond just one person's domain."""
    extra = tuple(t.lower() for t in _profile_tech_tags())
    remoteok_keywords = remoteok.HARDWARE_KEYWORDS + extra
    hn_keywords = hn_hiring.HARDWARE_KEYWORDS + extra

    discovered = 0
    with get_session() as db:
        for job in remoteok.fetch(tag_filter=remoteok_keywords):
            if not job.get("company_name"):
                continue
            company = company_repo.upsert(db, name=job["company_name"], source="discovered", needs_review=True)
            _, is_new = job_repo.upsert_posting(
                db, company_id=company.id, external_id=job["external_id"], source="remoteok",
                title=job.get("title", ""), url=job.get("url", ""), location=job.get("location"),
                remote_flag=job.get("remote_flag"), posted_at=job.get("posted_at"),
                raw_description=job.get("raw_description"),
            )
            if is_new:
                discovered += 1

        for job in hn_hiring.fetch(tag_filter=hn_keywords):
            company = company_repo.upsert(db, name=job["company_name"], source="discovered", needs_review=True)
            _, is_new = job_repo.upsert_posting(
                db, company_id=company.id, external_id=job["external_id"], source="hn_hiring",
                title=job.get("title", ""), url=job.get("url", ""), remote_flag=job.get("remote_flag"),
                raw_description=job.get("raw_description"),
            )
            if is_new:
                discovered += 1
    return discovered


def run(detect_limit: int = 40, careers_discovery_limit: int = 40) -> dict:
    logger.info("Starting daily job scan")
    # Detect first: a company detected this run should still get scanned
    # this run, not wait until tomorrow.
    detected = _detect_ats_for_unknown_companies(limit=detect_limit)
    checked, new_from_ats, errors = _scan_known_ats_companies()
    careers_urls_found = _discover_careers_urls(limit=careers_discovery_limit)
    new_from_generic = _scan_generic_careers_pages()
    new_from_discovery = _discover_new_companies()
    new_from_google = _discover_via_google()

    total_new = new_from_ats + new_from_generic + new_from_discovery + new_from_google
    with get_session() as db:
        db.add(SourceRunLog(source="daily_job_scan", companies_checked=checked, new_postings_found=total_new, errors=errors or None))

    logger.info(
        f"Daily job scan complete: {checked} companies checked, {detected} newly ATS-detected, "
        f"{careers_urls_found} careers pages newly found, "
        f"{total_new} new postings ({new_from_ats} ATS, {new_from_generic} generic, "
        f"{new_from_discovery} discovered, {new_from_google} via Google), "
        f"{len(errors)} source errors"
    )
    return {
        "companies_checked": checked,
        "new_postings": total_new,
        "newly_ats_detected": detected,
        "careers_urls_found": careers_urls_found,
        "errors": errors,
    }


if __name__ == "__main__":
    run()
