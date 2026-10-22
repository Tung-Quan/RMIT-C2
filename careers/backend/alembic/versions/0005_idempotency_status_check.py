"""Constrain idempotency record status values.

Revision ID: 0005_idempotency_status_check
Revises: 0004_idempotency_records
Create Date: 2026-07-22
"""

from alembic import op

revision = "0005_idempotency_status_check"
down_revision = "0004_idempotency_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_idempotency_records_status",
        "idempotency_records",
        "status IN ('processing', 'completed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_idempotency_records_status",
        "idempotency_records",
        type_="check",
    )
