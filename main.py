import argparse

import anthropic

from config import logger
from database.init_db import create_tables
from database.session import get_session
from database.repositories import profile_repo, job_repo, match_repo, prep_repo
from database.models import Company, JobMatch, JobPosting
from analysis import job_matcher, resume_tailor, prep_generator


def init_db():
    logger.info("Creating tables from SQLAlchemy metadata (dev bootstrap; use alembic for prod)")
    create_tables()


def scan_jobs():
    from scripts.daily_job_scan import run as run_scan
    return run_scan()


def match_jobs(profile_name: str | None, engine: str = "free", limit: int | None = None):
    """One short-lived DB session per posting, with the slow Claude call
    happening outside any session — scoring hundreds of postings can take
    many minutes, and holding a single transaction open that whole time
    risks the DB dropping an idle connection before anything gets
    committed (see the ATS-detection bug this pattern caused).

    engine="free" (default): analysis.job_matcher.score_job_free — pure
    keyword/skill-overlap, no API calls, no cost. Safe to run daily.
    engine="ai": analysis.job_matcher.score_job — Claude-scored, costs
    real money per posting (see README "Known account-level blockers" for
    the actual per-run cost math); use for a higher-quality pass on your
    current top candidates, not for scoring thousands of postings daily."""
    with get_session() as db:
        profiles = [profile_repo.get_by_name(db, profile_name)] if profile_name else profile_repo.list_all(db)
        profiles = [p for p in profiles if p is not None]
    if not profiles:
        logger.warning("No matching profile(s) found")
        return

    score_fn = job_matcher.score_job if engine == "ai" else job_matcher.score_job_free
    model_used = "claude" if engine == "ai" else "keyword_v1"

    for profile in profiles:
        if not profile.resume_structured:
            logger.warning(f"{profile.name}: no parsed resume yet — skipping (use the Profiles page first)")
            continue

        with get_session() as db:
            if engine == "ai" and limit:
                # Validating a capped/costed AI pass should prioritize the
                # postings a wrong free-engine score costs the most on —
                # the profile's current top-scored matches — not arbitrary
                # recency (see: the d-matrix "100% but wants 8+ years" report).
                top_matches = match_repo.top_for_profile(db, profile.id, limit=limit)
                postings = [
                    p for p in (db.get(JobPosting, m.job_posting_id) for m in top_matches)
                    if p is not None and p.status == "live"
                ]
            elif engine == "free":
                postings = job_repo.list_live(db, limit=100_000)  # no cap — no per-job cost
                # Never let a free rerun silently downgrade a posting that
                # already has a paid Claude score for this profile — same
                # (job_posting_id, profile_id) row gets overwritten by
                # match_repo.upsert() regardless of which engine wrote it
                # last, so without this a routine free rescore would erase
                # real money already spent on --engine ai.
                claude_scored_ids = {
                    row[0] for row in db.query(JobMatch.job_posting_id).filter(
                        JobMatch.profile_id == profile.id, JobMatch.model_used == "claude"
                    )
                }
                if claude_scored_ids:
                    postings = [p for p in postings if p.id not in claude_scored_ids]
                    logger.info(f"{profile.name}: skipping {len(claude_scored_ids)} postings with an existing Claude score")
            else:
                postings = job_repo.list_live(db, limit=limit or 500)
        logger.info(f"{profile.name}: scoring {len(postings)} live postings ({engine} engine)")

        for i, posting in enumerate(postings, start=1):
            if i % 100 == 0:
                logger.info(f"{profile.name}: scored {i}/{len(postings)} postings so far")

            with get_session() as db:
                company = db.get(Company, posting.company_id)
                company_context = f"{company.name} — {company.description or ''}" if company else ""

            try:
                result = score_fn(
                    profile.resume_structured,
                    posting.title,
                    posting.raw_description or posting.title,
                    company_context=company_context,
                )
            except (ValueError, anthropic.APIError) as exc:
                # ValueError covers json.JSONDecodeError (e.g. the model's JSON
                # response got truncated mid-string) — one bad response used to
                # crash the entire batch, losing every posting after it. Skip
                # this posting (no match row written for it — never fabricate
                # a score) and keep going; postings already scored this run
                # stay committed since each upsert is its own session.
                logger.warning(f"{profile.name}: failed to score posting {posting.id} ({posting.title[:60]!r}): {exc}")
                continue

            with get_session() as db:
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
                    model_used=model_used,
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
    parser.add_argument(
        "--engine", choices=["free", "ai"], default="free",
        help="match-jobs scoring engine: 'free' (default) = keyword overlap, no API calls, no cost, "
             "scores every live posting. 'ai' = Claude-scored, real cost per posting, capped at 500 postings.",
    )
    parser.add_argument(
        "--limit", type=int, required=False,
        help="match-jobs: cap the number of postings scored. With --engine ai, also changes selection "
             "to the profile's current top-scored postings (highest value target for a paid validation "
             "pass) instead of most-recent. Ignored by --engine free (always scores every live posting).",
    )
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
    elif args.command == "scan-jobs":
        scan_jobs()
    elif args.command == "match-jobs":
        match_jobs(args.profile, args.engine, args.limit)
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
