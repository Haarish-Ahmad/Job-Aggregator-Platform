"""add student resume and alert fields

Revision ID: d4a9f6b2e8c1
Revises: c1cf2ee23d51
Create Date: 2026-10-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4a9f6b2e8c1'
down_revision: Union[str, Sequence[str], None] = 'c1cf2ee23d51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('students', sa.Column('resume_file', sa.String(length=100), nullable=True))
    op.add_column('students', sa.Column('alerts_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.alter_column('students', 'branch',
               existing_type=sa.String(length=100),
               nullable=True)


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE students SET branch = 'N/A' WHERE branch IS NULL"
    ))
    op.alter_column('students', 'branch',
               existing_type=sa.String(length=100),
               nullable=False)
    op.drop_column('students', 'alerts_enabled')
    op.drop_column('students', 'resume_file')
