"""add scraper identity and freshness fields

Revision ID: e4c7a19b2d60
Revises: d4a9f6b2e8c1
Create Date: 2026-10-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e4c7a19b2d60"
down_revision: Union[str, Sequence[str], None] = "d4a9f6b2e8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_postings",sa.Column("source",sa.String(length=50),nullable=True))
    op.add_column("job_postings",sa.Column("external_id",sa.String(length=255),nullable=True))
    op.add_column("job_postings",sa.Column("source_content_hash",sa.String(length=64),nullable=True))
    op.add_column("job_postings",sa.Column("is_remote",sa.Boolean(),server_default=sa.text("false"),nullable=False))
    op.add_column("job_postings",sa.Column("is_india",sa.Boolean(),nullable=True))
    op.add_column("job_postings",sa.Column("work_mode",sa.String(length=20),nullable=True))
    op.add_column("job_postings",sa.Column("posted_date",sa.Date(),nullable=True))
    op.add_column("job_postings",sa.Column("updated_at",sa.DateTime(),server_default=sa.text("now()"),nullable=False))
    op.create_index("ix_job_postings_source","job_postings",["source"],unique=False)
    op.create_unique_constraint("uq_job_source_external_id","job_postings",["source","external_id"])


def downgrade() -> None:
    op.drop_constraint("uq_job_source_external_id","job_postings",type_="unique")
    op.drop_index("ix_job_postings_source",table_name="job_postings")
    op.drop_column("job_postings","updated_at")
    op.drop_column("job_postings","posted_date")
    op.drop_column("job_postings","work_mode")
    op.drop_column("job_postings","is_india")
    op.drop_column("job_postings","is_remote")
    op.drop_column("job_postings","source_content_hash")
    op.drop_column("job_postings","external_id")
    op.drop_column("job_postings","source")
