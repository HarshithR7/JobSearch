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
from database.repositories import company_repo, job_repo
from collectors import ats_detect, careers_generic, hn_hiring, remoteok
from collectors.ats_detect import FETCHERS


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
    """Tries to identify the ATS for companies still marked 'unknown',
    a handful per run so a full backlog doesn't turn one run into hundreds
    of probe requests."""
    detected = 0
    with get_session() as db:
        unknown = [c for c in company_repo.list_all(db) if c.ats_type == "unknown"][:limit]
        for company in unknown:
            ats_type, slug = ats_detect.detect(company.name, company.careers_url)
            if ats_type:
                company.ats_type = ats_type
                company.ats_slug = slug
                detected += 1
            else:
                company.ats_type = "none"
    return detected


def _scan_generic_careers_pages(limit: int = 20) -> int:
    """Best-effort fallback for companies with a careers_url but no known
    ATS. Always flags results needs_review — see collectors/careers_generic.py."""
    new_postings = 0
    with get_session() as db:
        targets = [
            c for c in company_repo.list_all(db)
            if c.ats_type in ("none", "generic") and c.careers_url
        ][:limit]

    for company in targets:
        jobs = careers_generic.fetch(company.careers_url)
        if not jobs:
            continue
        with get_session() as db:
            db_company = db.get(Company, company.id)
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


def _discover_new_companies() -> int:
    """RemoteOK + HN Who's Hiring, filtered to hardware/AI-chip keywords —
    grows the company list beyond the seeded spreadsheet."""
    discovered = 0
    with get_session() as db:
        for job in remoteok.fetch():
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

        for job in hn_hiring.fetch():
            company = company_repo.upsert(db, name=job["company_name"], source="discovered", needs_review=True)
            _, is_new = job_repo.upsert_posting(
                db, company_id=company.id, external_id=job["external_id"], source="hn_hiring",
                title=job.get("title", ""), url=job.get("url", ""), remote_flag=job.get("remote_flag"),
                raw_description=job.get("raw_description"),
            )
            if is_new:
                discovered += 1
    return discovered


def run() -> dict:
    logger.info("Starting daily job scan")
    checked, new_from_ats, errors = _scan_known_ats_companies()
    detected = _detect_ats_for_unknown_companies()
    new_from_generic = _scan_generic_careers_pages()
    new_from_discovery = _discover_new_companies()

    total_new = new_from_ats + new_from_generic + new_from_discovery
    with get_session() as db:
        db.add(SourceRunLog(source="daily_job_scan", companies_checked=checked, new_postings_found=total_new, errors=errors or None))

    logger.info(
        f"Daily job scan complete: {checked} companies checked, {detected} newly ATS-detected, "
        f"{total_new} new postings ({new_from_ats} ATS, {new_from_generic} generic, {new_from_discovery} discovered), "
        f"{len(errors)} source errors"
    )
    return {
        "companies_checked": checked,
        "new_postings": total_new,
        "newly_ats_detected": detected,
        "errors": errors,
    }


if __name__ == "__main__":
    run()
