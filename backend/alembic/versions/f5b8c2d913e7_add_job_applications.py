"""add job application tracking

Revision ID: f5b8c2d913e7
Revises: e4c7a19b2d60
Create Date: 2026-10-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f5b8c2d913e7"
down_revision: Union[str, Sequence[str], None] = "e4c7a19b2d60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id",sa.Integer(),nullable=False),
        sa.Column("student_id",sa.Integer(),nullable=False),
        sa.Column("job_id",sa.Integer(),nullable=False),
        sa.Column("status",sa.String(length=20),server_default="applied",nullable=False),
        sa.Column("notes",sa.Text(),nullable=True),
        sa.Column("applied_at",sa.DateTime(),nullable=True),
        sa.Column("created_at",sa.DateTime(),server_default=sa.text("now()"),nullable=False),
        sa.Column("updated_at",sa.DateTime(),server_default=sa.text("now()"),nullable=False),
        sa.CheckConstraint(
            "status IN ('saved','applied','assessment','interview','offer','rejected','withdrawn')",
            name="ck_application_status",
        ),
        sa.ForeignKeyConstraint(["job_id"],["job_postings.id"],ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"],["students.id"],ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id","job_id",name="uq_application_student_job"),
    )
    op.create_index("ix_applications_student_id","applications",["student_id"],unique=False)
    op.create_index("ix_applications_job_id","applications",["job_id"],unique=False)


def downgrade() -> None:
    op.drop_index("ix_applications_job_id",table_name="applications")
    op.drop_index("ix_applications_student_id",table_name="applications")
    op.drop_table("applications")
