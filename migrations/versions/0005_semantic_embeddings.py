"""Add pgvector embedding columns for semantic job matching.

Layered on top of (not replacing) the existing free keyword scorer — a
third signal that catches conceptual matches the keyword vocabulary
can't ("Tomasulo algorithm with reorder buffer" <-> "out-of-order
execution", 0.74 cosine similarity despite zero shared keywords,
verified against the actual embedding model before this was built).
384-dim: BAAI/bge-small-en-v1.5 via fastembed (ONNX, no PyTorch — chosen
over sentence-transformers specifically to stay light enough for
Streamlit Community Cloud deployment).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("job_posting", sa.Column("embedding", Vector(384), nullable=True))
    op.add_column("profile", sa.Column("resume_embedding", Vector(384), nullable=True))


def downgrade() -> None:
    op.drop_column("profile", "resume_embedding")
    op.drop_column("job_posting", "embedding")
