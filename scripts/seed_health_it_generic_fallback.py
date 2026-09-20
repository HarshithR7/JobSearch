"""Second pass for scripts/seed_health_it_companies.py: for health-IT
companies where no known ATS was auto-detected (large enterprises often run
custom/unsupported job boards — iCIMS, SuccessFactors, Taleo, or fully
custom), try the generic careers-page scraper as a best-effort fallback.
Skips anything careers_generic itself flags as JS-rendered (it can't scrape
those; they'd need Selenium/Playwright, out of scope here).

Run: python -m scripts.seed_health_it_generic_fallback
"""

from datetime import datetime, timezone

from config import logger
from database.session import get_session
from database.models import Company
from database.repositories import company_repo, job_repo
from collectors import careers_generic

HEALTH_IT_TAG = "Health IT"


def main() -> None:
    with get_session() as db:
        companies = [
            c for c in company_repo.list_all(db)
            if c.technology_tag == HEALTH_IT_TAG and c.ats_type == "unknown"
        ]

    run_start = datetime.now(timezone.utc)
    total_new = 0
    scraped_ok = 0
    for company in companies:
        careers_url = company.careers_url or careers_generic.discover_careers_url(company.website)
        if not careers_url:
            logger.info(f"{company.name}: no careers page found")
            continue

        jobs = careers_generic.fetch(careers_url)
        if jobs is None:
            logger.info(f"{company.name}: fetch failed/skipped ({careers_url})")
            continue
        if not jobs:
            logger.info(f"{company.name}: careers page found but 0 jobs parsed ({careers_url})")
            continue

        scraped_ok += 1
        new_here = 0
        with get_session() as db:
            company_row = db.get(Company, company.id)
            company_row.careers_url = careers_url
            company_row.ats_type = "generic"
            for job in jobs:
                _, is_new = job_repo.upsert_posting(
                    db,
                    company_id=company.id,
                    external_id=job["external_id"],
                    source="generic",
                    title=job.get("title", ""),
                    url=job.get("url", ""),
                    location=job.get("location"),
                    remote_flag=job.get("remote_flag"),
                    department=job.get("department"),
                    posted_at=job.get("posted_at"),
                    raw_description=job.get("raw_description"),
                )
                if is_new:
                    new_here += 1
            company_row.last_checked_at = run_start
        total_new += new_here
        logger.info(f"{company.name}: {len(jobs)} parsed, {new_here} new ({careers_url})")

    logger.info(f"Done. {scraped_ok}/{len(companies)} companies scraped successfully, {total_new} new postings total.")


if __name__ == "__main__":
    main()
