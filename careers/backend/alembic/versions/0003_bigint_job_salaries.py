"""Use 64-bit integers for job salary ranges.

Revision ID: 0003_bigint_job_salaries
Revises: 0002_two_sided_platform
Create Date: 2026-06-22
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_bigint_job_salaries"
down_revision = "0002_two_sided_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_postings", schema=None) as batch_op:
        batch_op.alter_column(
            "salary_min",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "salary_max",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("job_postings", schema=None) as batch_op:
        batch_op.alter_column(
            "salary_min",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "salary_max",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
