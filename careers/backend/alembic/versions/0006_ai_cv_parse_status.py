"""Add AI CV parsing fields

Revision ID: 0006_ai_cv_parse_status
Revises: 0005_ai_parse_status
Create Date: 2026-07-22

"""

import sqlalchemy as sa

from alembic import op

revision = "0006_ai_cv_parse_status"
down_revision = "0005_ai_parse_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_applications", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "ai_cv_parse_status",
                sa.String(length=50),
                server_default="not_started",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("ai_cv_parsed_profile", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("ai_cv_parse_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("ai_cv_parsed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column(
                "ai_cv_parse_revision",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("job_applications", schema=None) as batch_op:
        batch_op.drop_column("ai_cv_parse_revision")
        batch_op.drop_column("ai_cv_parsed_at")
        batch_op.drop_column("ai_cv_parse_error")
        batch_op.drop_column("ai_cv_parsed_profile")
        batch_op.drop_column("ai_cv_parse_status")
