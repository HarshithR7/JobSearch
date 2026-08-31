"""Widen company.technology_tag and company.country — the seed spreadsheet
has misaligned columns on some sheets that put free-text descriptions in
these slots.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("company", "technology_tag", type_=sa.String(500))
    op.alter_column("company", "country", type_=sa.String(500))


def downgrade() -> None:
    op.alter_column("company", "technology_tag", type_=sa.String(120))
    op.alter_column("company", "country", type_=sa.String(80))
