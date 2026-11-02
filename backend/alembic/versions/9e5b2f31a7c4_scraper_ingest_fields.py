"""scraper ingest fields: identity, freshness, india/remote flags, alert opt-in

Revision ID: 9e5b2f31a7c4
Revises: 7c1e4a90b2d3
Create Date: 2026-10-18 12:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9e5b2f31a7c4"
down_revision: Union[str, Sequence[str], None] = "7c1e4a90b2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("source", sa.String(length=50), nullable=True))
    op.add_column("job_postings", sa.Column("external_id", sa.String(length=255), nullable=True))
    op.add_column("job_postings", sa.Column("source_content_hash", sa.String(length=64), nullable=True))
    op.add_column("job_postings", sa.Column("is_remote", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("job_postings", sa.Column("is_india", sa.Boolean(), nullable=True))
    op.add_column("job_postings", sa.Column("work_mode", sa.String(length=20), nullable=True))
    op.add_column("job_postings", sa.Column("posted_date", sa.Date(), nullable=True))
    op.add_column("job_postings", sa.Column("last_seen_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False))
    op.add_column("job_postings", sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False))
    op.create_index(op.f("ix_job_postings_source"), "job_postings", ["source"], unique=False)
    # NULLs are distinct in Postgres, so legacy rows (no source/external_id) never collide.
    op.create_unique_constraint("uq_job_source_external_id", "job_postings", ["source", "external_id"])
    op.add_column("students", sa.Column("alerts_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    op.drop_column("students", "alerts_enabled")
    op.drop_constraint("uq_job_source_external_id", "job_postings", type_="unique")
    op.drop_index(op.f("ix_job_postings_source"), table_name="job_postings")
    for col in ("updated_at", "last_seen_at", "posted_date", "work_mode", "is_india", "is_remote",
                "source_content_hash", "external_id", "source"):
        op.drop_column("job_postings", col)
