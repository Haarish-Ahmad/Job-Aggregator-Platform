"""fix drift between the initial migration and models.py

The initial migration was generated before the models were changed, so it created
students.year_grad / job_postings.year_grad (NOT NULL, never filled by any code),
a nullable students.grad_year, a unique password-hash index and a NOT NULL branch.
This brings the database in line with the models without editing the shipped migration.

Revision ID: 7c1e4a90b2d3
Revises: ab7b8208ab2d
Create Date: 2026-10-18 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7c1e4a90b2d3"
down_revision: Union[str, Sequence[str], None] = "ab7b8208ab2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep any existing data: grad_year was nullable, year_grad was the NOT NULL twin.
    op.execute("UPDATE students SET grad_year = year_grad WHERE grad_year IS NULL")
    op.alter_column("students", "grad_year", existing_type=sa.Integer(), nullable=False)
    op.drop_column("students", "year_grad")
    op.drop_column("job_postings", "year_grad")
    op.alter_column("students", "branch", existing_type=sa.String(length=100), nullable=True)
    op.drop_index(op.f("ix_students_password_hash"), table_name="students")
    op.create_index(op.f("ix_students_password_hash"), "students", ["password_hash"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_students_password_hash"), table_name="students")
    op.create_index(op.f("ix_students_password_hash"), "students", ["password_hash"], unique=True)
    op.execute("UPDATE students SET branch = '' WHERE branch IS NULL")
    op.alter_column("students", "branch", existing_type=sa.String(length=100), nullable=False)
    op.add_column("job_postings", sa.Column("year_grad", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("students", sa.Column("year_grad", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE students SET year_grad = grad_year")
    op.alter_column("job_postings", "year_grad", server_default=None)
    op.alter_column("students", "year_grad", server_default=None)
    op.alter_column("students", "grad_year", existing_type=sa.Integer(), nullable=True)
