"""Initial schema: profile, company, job_posting, job_snapshot, job_match,
application, application_event, resume_version, role_archetype,
prep_content, linkedin_alert_email, source_run_log.

Revision ID: 0001
Revises:
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("resume_raw_text", sa.Text, nullable=True),
        sa.Column("resume_structured", postgresql.JSONB, nullable=True),
        sa.Column("resume_file_path", sa.String(500), nullable=True),
        sa.Column("target_roles", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("target_tech_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("visa_status", sa.String(120), nullable=True),
        sa.Column("location_preference", sa.String(255), nullable=True),
        sa.Column("github_username", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "company",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("careers_url", sa.String(500), nullable=True),
        sa.Column("ats_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("ats_slug", sa.String(255), nullable=True),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("technology_tag", sa.String(120), nullable=True),
        sa.Column("country", sa.String(80), nullable=True),
        sa.Column("founded_year", sa.Integer, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("priority_tier", sa.String(40), nullable=True),
        sa.Column("visa_sponsor_known", sa.Boolean, nullable=True),
        sa.Column("source", sa.String(40), nullable=False, server_default="manual"),
        sa.Column("legacy_notes", sa.Text, nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "job_posting",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("company.id"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("remote_flag", sa.Boolean, nullable=True),
        sa.Column("department", sa.String(255), nullable=True),
        sa.Column("tech_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(20), nullable=False, server_default="live"),
        sa.Column("raw_description", sa.Text, nullable=True),
        sa.UniqueConstraint("company_id", "external_id", name="uq_job_company_external"),
    )

    op.create_table(
        "job_snapshot",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_posting_id", sa.Integer, sa.ForeignKey("job_posting.id"), nullable=False),
        sa.Column("description_hash", sa.String(64), nullable=False),
        sa.Column("description_text", sa.Text, nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "job_match",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_posting_id", sa.Integer, sa.ForeignKey("job_posting.id"), nullable=False),
        sa.Column("profile_id", sa.Integer, sa.ForeignKey("profile.id"), nullable=False),
        sa.Column("overall_score", sa.Integer, nullable=False),
        sa.Column("sub_scores", postgresql.JSONB, nullable=False),
        sa.Column("band", sa.String(30), nullable=False),
        sa.Column("matched_skills", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("missing_skills", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("model_used", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("job_posting_id", "profile_id", name="uq_match_job_profile"),
    )

    op.create_table(
        "resume_version",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_id", sa.Integer, sa.ForeignKey("profile.id"), nullable=False),
        sa.Column("job_posting_id", sa.Integer, sa.ForeignKey("job_posting.id"), nullable=True),
        sa.Column("generated_text", sa.Text, nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("ats_missing_keywords", sa.Text, nullable=True),
        sa.Column("model_used", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "application",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_id", sa.Integer, sa.ForeignKey("profile.id"), nullable=False),
        sa.Column("job_posting_id", sa.Integer, sa.ForeignKey("job_posting.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="discovered"),
        sa.Column("resume_version_id", sa.Integer, sa.ForeignKey("resume_version.id"), nullable=True),
        sa.Column("cover_note", sa.Text, nullable=True),
        sa.Column("recruiter", sa.String(255), nullable=True),
        sa.Column("referral", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("follow_up_date", sa.Date, nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "application_event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("application_id", sa.Integer, sa.ForeignKey("application.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "role_archetype",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("tech_tag", sa.String(120), nullable=True),
    )

    op.create_table(
        "prep_content",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("role_archetype_id", sa.Integer, sa.ForeignKey("role_archetype.id"), nullable=False, unique=True),
        sa.Column("books", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("topics", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("courses", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("sample_qna", postgresql.JSONB, nullable=True),
        sa.Column("model_used", sa.String(80), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "linkedin_alert_email",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_id", sa.Integer, sa.ForeignKey("profile.id"), nullable=False),
        sa.Column("message_id", sa.String(500), nullable=False, unique=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "source_run_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("companies_checked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("new_postings_found", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB, nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("source_run_log")
    op.drop_table("linkedin_alert_email")
    op.drop_table("prep_content")
    op.drop_table("role_archetype")
    op.drop_table("application_event")
    op.drop_table("application")
    op.drop_table("resume_version")
    op.drop_table("job_match")
    op.drop_table("job_snapshot")
    op.drop_table("job_posting")
    op.drop_table("company")
    op.drop_table("profile")
