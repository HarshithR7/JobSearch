"""One-time seed of health-IT/EHR/clinical-informatics employers for
Srilekha's profile — the existing 583-company database is almost entirely
semiconductor/hardware startups (Harshith's domain), so her Job Feed had
nothing relevant to score against. Adds real companies, auto-detects their
ATS the same way scripts/daily_job_scan.py does for discovered companies
(live HTTP probes, not guesses), then pulls their current postings.

Run: python -m scripts.seed_health_it_companies
"""

from datetime import datetime, timezone

from config import logger
from database.session import get_session
from database.models import Company
from database.repositories import company_repo, job_repo
from collectors import ats_detect
from collectors.ats_detect import FETCHERS

# name, website — EHR/health-IT vendors, health-data/interoperability
# companies, clinical-documentation AI, and large hospital systems (the
# latter often run Workday for their job boards, which this project added
# a real collector for in the same session this list was compiled).
HEALTH_IT_COMPANIES = [
    ("Epic Systems", "https://www.epic.com"),
    ("Oracle Health", "https://www.oracle.com/health/"),
    ("Netsmart Technologies", "https://www.ntst.com"),
    ("eClinicalWorks", "https://www.eclinicalworks.com"),
    ("athenahealth", "https://www.athenahealth.com"),
    ("Veradigm", "https://veradigm.com"),
    ("MEDITECH", "https://ehr.meditech.com"),
    ("NextGen Healthcare", "https://www.nextgen.com"),
    ("Greenway Health", "https://www.greenwayhealth.com"),
    ("WellSky", "https://www.wellsky.com"),
    ("PointClickCare", "https://pointclickcare.com"),
    ("Optum", "https://www.optum.com"),
    ("Included Health", "https://includedhealth.com"),
    ("Health Catalyst", "https://www.healthcatalyst.com"),
    ("Innovaccer", "https://innovaccer.com"),
    ("Komodo Health", "https://www.komodohealth.com"),
    ("Datavant", "https://www.datavant.com"),
    ("Truveta", "https://www.truveta.com"),
    ("Cedar", "https://cedar.com"),
    ("Flatiron Health", "https://flatiron.com"),
    ("Tempus AI", "https://www.tempus.com"),
    ("Suki AI", "https://www.suki.ai"),
    ("Abridge", "https://www.abridge.com"),
    ("Nuance Communications", "https://www.nuance.com"),
    ("Commure", "https://www.commure.com"),
    ("Particle Health", "https://www.particlehealth.com"),
    ("Redox", "https://www.redoxengine.com"),
    ("1upHealth", "https://1up.health"),
    ("CareEvolution", "https://careevolution.com"),
    ("Bamboo Health", "https://www.bamboohealth.com"),
    ("Surescripts", "https://surescripts.com"),
    ("Carbon Health", "https://carbonhealth.com"),
    ("Oscar Health", "https://www.hioscar.com"),
    ("Clover Health", "https://www.cloverhealth.com"),
    ("Arcadia", "https://arcadia.io"),
    ("Cohere Health", "https://coherehealth.com"),
    ("Relias", "https://www.relias.com"),
    ("Leidos", "https://www.leidos.com"),
    ("HCA Healthcare", "https://careers.hcahealthcare.com"),
    ("Providence", "https://www.providence.org"),
    ("Kaiser Permanente", "https://www.kaiserpermanente.org"),
    ("Mass General Brigham", "https://www.massgeneralbrigham.org"),
    ("Cleveland Clinic", "https://my.clevelandclinic.org"),
    ("Mayo Clinic", "https://www.mayoclinic.org"),
    ("Indiana University Health", "https://iuhealth.org"),
    ("CommonSpirit Health", "https://www.commonspirit.org"),
]


def main() -> None:
    added = 0
    with get_session() as db:
        for name, website in HEALTH_IT_COMPANIES:
            existing = company_repo.get_by_name(db, name)
            if existing is not None:
                continue
            company_repo.upsert(
                db, name=name, website=website, technology_tag="Health IT",
                source="manual", priority_tier="Tier 1 Primary",
            )
            added += 1
    logger.info(f"Seeded {added} new health-IT companies ({len(HEALTH_IT_COMPANIES) - added} already existed)")

    # ATS detection — live probes against each new company's name/website,
    # same function daily_job_scan.py uses for discovered companies.
    with get_session() as db:
        target_ids = [
            c.id for c in company_repo.list_all(db)
            if c.name in {n for n, _ in HEALTH_IT_COMPANIES} and c.ats_type == "unknown"
        ]

    detected = 0
    for company_id in target_ids:
        with get_session() as db:
            company = db.get(Company, company_id)
            name, careers_url, website = company.name, company.careers_url, company.website

        ats_type, slug = ats_detect.detect(name, careers_url)
        if ats_type is None:
            workday_slug = ats_detect.detect_workday(website)
            if workday_slug:
                ats_type, slug = "workday", workday_slug

        with get_session() as db:
            company = db.get(Company, company_id)
            if ats_type:
                company.ats_type = ats_type
                company.ats_slug = slug
                detected += 1
            else:
                company.needs_review = True
    logger.info(f"ATS detected for {detected}/{len(target_ids)} new companies")

    # Pull live postings for every new company where a known ATS was found.
    with get_session() as db:
        to_fetch = [
            c for c in company_repo.list_all(db)
            if c.name in {n for n, _ in HEALTH_IT_COMPANIES} and c.ats_type in FETCHERS
        ]

    run_start = datetime.now(timezone.utc)
    total_new_postings = 0
    for company in to_fetch:
        fetcher = FETCHERS[company.ats_type]
        jobs = fetcher(company.ats_slug)
        if not jobs:
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
                    total_new_postings += 1
            db.query(Company).filter(Company.id == company.id).update({"last_checked_at": run_start})
        logger.info(f"{company.name} ({company.ats_type}): {len(jobs)} live postings")

    logger.info(f"Done. {total_new_postings} new postings ingested from {len(to_fetch)} health-IT companies with known ATS.")


if __name__ == "__main__":
    main()
