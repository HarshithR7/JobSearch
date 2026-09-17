"""Add per-profile IMAP credentials for the LinkedIn alert-email parser.

collectors/linkedin_email_parser.py existed but was hardcoded to one
global mailbox (settings.IMAP_*) and never called from anywhere — dead
code. Multi-profile means each person needs their own mailbox: Harshith's
LinkedIn alerts land in Harshith's inbox, not a friend's.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profile", sa.Column("imap_host", sa.String(255), nullable=True))
    op.add_column("profile", sa.Column("imap_user", sa.String(255), nullable=True))
    op.add_column("profile", sa.Column("imap_app_password", sa.String(255), nullable=True))
    op.add_column("profile", sa.Column("imap_label", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("profile", "imap_label")
    op.drop_column("profile", "imap_app_password")
    op.drop_column("profile", "imap_user")
    op.drop_column("profile", "imap_host")
