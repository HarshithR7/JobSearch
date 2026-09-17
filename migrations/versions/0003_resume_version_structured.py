"""Add resume_version.tailored_structured — persists the structured
{summary, experience, projects, skills} dict alongside the flattened
generated_text, so a properly-formatted .docx can be re-rendered for a
past version later instead of falling back to a flat-text reconstruction.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resume_version", sa.Column("tailored_structured", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("resume_version", "tailored_structured")
