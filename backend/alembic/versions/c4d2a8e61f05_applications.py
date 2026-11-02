"""application tracker: jobs a student saved and the status of each application

Additive only: one new table, nothing existing is touched.

Revision ID: c4d2a8e61f05
Revises: 9e5b2f31a7c4
Create Date: 2026-10-30 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4d2a8e61f05"
down_revision: Union[str, Sequence[str], None] = "9e5b2f31a7c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'saved'"), nullable=False),
        sa.Column("saved_on", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False),
        sa.Column("applied_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('saved','applied','assessment','interview','offer','rejected','withdrawn')",
            name="ck_application_status",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["job_postings.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "job_id", name="uq_application_student_job"),
    )
    op.create_index(op.f("ix_applications_student_id"), "applications", ["student_id"], unique=False)
    op.create_index(op.f("ix_applications_job_id"), "applications", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_applications_job_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_student_id"), table_name="applications")
    op.drop_table("applications")
