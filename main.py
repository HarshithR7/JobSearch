import argparse

from config import logger
from database.init_db import create_tables
from database.session import get_session
from database.repositories import profile_repo, job_repo, match_repo, prep_repo
from database.models import Company
from analysis import job_matcher, resume_tailor, prep_generator


def init_db():
    logger.info("Creating tables from SQLAlchemy metadata (dev bootstrap; use alembic for prod)")
    create_tables()


def scan_jobs():
    from scripts.daily_job_scan import run as run_scan
    return run_scan()


def match_jobs(profile_name: str | None):
    with get_session() as db:
        profiles = [profile_repo.get_by_name(db, profile_name)] if profile_name else profile_repo.list_all(db)
        profiles = [p for p in profiles if p is not None]
        if not profiles:
            logger.warning("No matching profile(s) found")
            return

        for profile in profiles:
            if not profile.resume_structured:
                logger.warning(f"{profile.name}: no parsed resume yet — skipping (use the Profiles page first)")
                continue

            postings = job_repo.list_live(db)
            logger.info(f"{profile.name}: scoring {len(postings)} live postings")
            for posting in postings:
                company = db.get(Company, posting.company_id)
                result = job_matcher.score_job(
                    profile.resume_structured,
                    posting.title,
                    posting.raw_description or posting.title,
                    company_context=f"{company.name} — {company.description or ''}" if company else "",
                )
                match_repo.upsert(
                    db,
                    job_posting_id=posting.id,
                    profile_id=profile.id,
                    overall_score=result["overall_score"],
                    sub_scores=result["sub_scores"],
                    band=result["band"],
                    matched_skills=result["matched_skills"],
                    missing_skills=result["missing_skills"],
                    rationale=result["rationale"],
                    model_used="claude",
                )


def tailor_resume(profile_name: str, job_id: int):
    from database.models import JobPosting, ResumeVersion

    with get_session() as db:
        profile = profile_repo.get_by_name(db, profile_name)
        if profile is None or not profile.resume_structured:
            logger.warning("Profile not found or has no parsed resume")
            return
        posting = db.get(JobPosting, job_id)
        if posting is None:
            logger.warning(f"No job_posting with id={job_id}")
            return
        tailored = resume_tailor.generate_tailored_content(
            profile.resume_structured, posting.title, posting.raw_description or posting.title
        )
        text = resume_tailor.to_plain_text(tailored)
        version = ResumeVersion(profile_id=profile.id, job_posting_id=posting.id, generated_text=text, model_used="claude")
        db.add(version)
        db.flush()
        logger.info(f"Tailored resume saved as resume_version id={version.id}")


def generate_prep(role_name: str, tech_tag: str | None):
    with get_session() as db:
        archetype = prep_repo.get_or_create_archetype(db, role_name, tech_tag)
        existing = prep_repo.get_fresh_content(db, archetype.id)
        if existing:
            logger.info(f"Fresh prep content already exists for '{role_name}' (generated {existing.generated_at})")
            return
        content = prep_generator.generate_prep_content(role_name, tech_tag)
        prep_repo.upsert_content(
            db,
            role_archetype_id=archetype.id,
            books=content.get("books", []),
            topics=content.get("topics", []),
            courses=content.get("courses", []),
            sample_qna=content.get("sample_qna", []),
            model_used="claude",
        )
        logger.info(f"Prep content generated for '{role_name}'")


def main():
    parser = argparse.ArgumentParser(description="Job Search Portal CLI")
    parser.add_argument(
        "command",
        choices=["init-db", "scan-jobs", "match-jobs", "tailor-resume", "generate-prep"],
    )
    parser.add_argument("--profile", required=False, help="Profile name (omit for all profiles, where applicable)")
    parser.add_argument("--job-id", type=int, required=False)
    parser.add_argument("--role", required=False, help="Role archetype name, e.g. 'RISC-V Verification Engineer'")
    parser.add_argument("--tech-tag", required=False)
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
    elif args.command == "scan-jobs":
        scan_jobs()
    elif args.command == "match-jobs":
        match_jobs(args.profile)
    elif args.command == "tailor-resume":
        if not (args.profile and args.job_id):
            parser.error("tailor-resume requires --profile and --job-id")
        tailor_resume(args.profile, args.job_id)
    elif args.command == "generate-prep":
        if not args.role:
            parser.error("generate-prep requires --role")
        generate_prep(args.role, args.tech_tag)


if __name__ == "__main__":
    main()
