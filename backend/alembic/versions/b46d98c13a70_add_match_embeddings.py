"""store sentence-transformer embeddings for student and job matching

Revision ID: b46d98c13a70
Revises: a93e7f2c51d6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b46d98c13a70"
down_revision: Union[str, Sequence[str], None] = "a93e7f2c51d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("students", sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True))
    op.add_column("job_postings", sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True))


def downgrade() -> None:
    op.drop_column("job_postings", "embedding")
    op.drop_column("students", "embedding")
