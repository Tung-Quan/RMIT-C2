"""Add async processing jobs.

Revision ID: 0008_async_processing_jobs
Revises: 0007_outbox_events
Create Date: 2026-07-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_async_processing_jobs"
down_revision = "0007_outbox_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "async_processing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("requester_user_id", sa.Integer(), nullable=True),
        sa.Column("related_entity_type", sa.String(length=80), nullable=True),
        sa.Column("related_entity_id", sa.String(length=80), nullable=True),
        sa.Column("source_entity_type", sa.String(length=80), nullable=True),
        sa.Column("source_entity_id", sa.String(length=80), nullable=True),
        sa.Column("source_version", sa.Integer(), nullable=True),
        sa.Column("source_checksum", sa.String(length=128), nullable=True),
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column(
            "input_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.String(length=512), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_async_processing_jobs_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deduplication_key", name="uq_async_processing_jobs_deduplication_key"),
    )
    op.create_index(
        "ix_async_processing_jobs_claimable",
        "async_processing_jobs",
        ["status", "available_at"],
    )
    op.create_index(
        "ix_async_processing_jobs_running_lease",
        "async_processing_jobs",
        ["status", "locked_until"],
    )
    op.create_index(
        "ix_async_processing_jobs_owner_status",
        "async_processing_jobs",
        ["owner_user_id", "status"],
    )
    op.create_index(
        "ix_async_processing_jobs_type_status",
        "async_processing_jobs",
        ["job_type", "status"],
    )
    op.create_index(
        "ix_async_processing_jobs_related_entity",
        "async_processing_jobs",
        ["related_entity_type", "related_entity_id"],
    )
    op.create_index(
        "ix_async_processing_jobs_source_entity",
        "async_processing_jobs",
        ["source_entity_type", "source_entity_id", "source_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_async_processing_jobs_source_entity", table_name="async_processing_jobs")
    op.drop_index("ix_async_processing_jobs_related_entity", table_name="async_processing_jobs")
    op.drop_index("ix_async_processing_jobs_type_status", table_name="async_processing_jobs")
    op.drop_index("ix_async_processing_jobs_owner_status", table_name="async_processing_jobs")
    op.drop_index("ix_async_processing_jobs_running_lease", table_name="async_processing_jobs")
    op.drop_index("ix_async_processing_jobs_claimable", table_name="async_processing_jobs")
    op.drop_table("async_processing_jobs")
