"""store uploaded student resumes

Revision ID: a93e7f2c51d6
Revises: e81f3b5c9a27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a93e7f2c51d6"
down_revision: Union[str, Sequence[str], None] = "e81f3b5c9a27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("students", sa.Column("resume_file", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("students", "resume_file")
