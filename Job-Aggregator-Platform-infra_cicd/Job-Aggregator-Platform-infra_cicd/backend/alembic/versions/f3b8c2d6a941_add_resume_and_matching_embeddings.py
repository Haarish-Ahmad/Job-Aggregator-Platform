"""add resume storage and matching embeddings

Revision ID: f3b8c2d6a941
Revises: 9e5b2f31a7c4
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f3b8c2d6a941"
down_revision: Union[str, Sequence[str], None] = "9e5b2f31a7c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("students",sa.Column("resume_file",sa.String(length=100),nullable=True))
    op.add_column("students",sa.Column("embedding",postgresql.ARRAY(sa.Float()),nullable=True))
    op.add_column("job_postings",sa.Column("embedding",postgresql.ARRAY(sa.Float()),nullable=True))
    op.alter_column(
        "students",
        "alerts_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "students",
        "alerts_enabled",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
    op.drop_column("job_postings","embedding")
    op.drop_column("students","embedding")
    op.drop_column("students","resume_file")
