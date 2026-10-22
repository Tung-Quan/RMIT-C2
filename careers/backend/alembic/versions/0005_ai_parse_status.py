"""Add ai parse status to job_postings

Revision ID: 0005_ai_parse_status
Revises: 0004_document_texts
Create Date: 2026-07-22

"""

import sqlalchemy as sa

from alembic import op

revision = "0005_ai_parse_status"
down_revision = "0004_document_texts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column(
            "ai_parse_status", sa.String(length=50), server_default="not_started", nullable=False
        ),
    )
    op.add_column("job_postings", sa.Column("ai_parsed_profile", sa.JSON(), nullable=True))
    op.add_column("job_postings", sa.Column("ai_parse_error", sa.Text(), nullable=True))
    op.add_column(
        "job_postings", sa.Column("ai_parsed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "job_postings",
        sa.Column("ai_parse_revision", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("job_postings", "ai_parse_revision")
    op.drop_column("job_postings", "ai_parsed_at")
    op.drop_column("job_postings", "ai_parse_error")
    op.drop_column("job_postings", "ai_parsed_profile")
    op.drop_column("job_postings", "ai_parse_status")
