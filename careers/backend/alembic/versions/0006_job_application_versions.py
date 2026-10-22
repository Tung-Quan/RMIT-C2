"""Add job and application version columns.

Revision ID: 0006_job_application_versions
Revises: 0005_idempotency_status_check
Create Date: 2026-07-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_job_application_versions"
down_revision = "0005_idempotency_status_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "job_applications",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("job_applications", "version")
    op.drop_column("job_postings", "version")
