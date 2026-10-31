"""application statuses: down to saved, applied, interview, offer, rejected

'withdrawn' and 'assessment' are no longer offered. Existing rows are kept and moved to the
closest remaining status (withdrawn -> rejected, assessment -> applied) before the check is narrowed.

Revision ID: e81f3b5c9a27
Revises: c4d2a8e61f05
Create Date: 2026-10-30 15:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e81f3b5c9a27"
down_revision: Union[str, Sequence[str], None] = "c4d2a8e61f05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE applications SET status = 'rejected', updated_at = now() WHERE status = 'withdrawn'")
    op.execute("UPDATE applications SET status = 'applied', updated_at = now() WHERE status = 'assessment'")
    op.drop_constraint("ck_application_status", "applications", type_="check")
    op.create_check_constraint(
        "ck_application_status", "applications", "status IN ('saved','applied','interview','offer','rejected')"
    )


def downgrade() -> None:
    # Only widens the check again: converted rows can't be told apart, so they stay as they are.
    op.drop_constraint("ck_application_status", "applications", type_="check")
    op.create_check_constraint(
        "ck_application_status",
        "applications",
        "status IN ('saved','applied','assessment','interview','offer','rejected','withdrawn')",
    )
