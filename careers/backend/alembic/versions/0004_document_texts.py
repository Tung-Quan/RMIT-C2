"""Add cached extracted document text.

Revision ID: 0004_document_texts
Revises: 0003_bigint_job_salaries
Create Date: 2026-07-06
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_document_texts"
down_revision = "0003_bigint_job_salaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_texts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("blocks_json", sa.JSON(), nullable=True),
        sa.Column("semantic_groups_json", sa.JSON(), nullable=True),
        sa.Column("parser_name", sa.String(length=100), nullable=False),
        sa.Column("parser_version", sa.String(length=100), nullable=False),
        sa.Column("text_hash", sa.String(length=128), nullable=True),
        sa.Column("extraction_status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_texts_document_id"), "document_texts", ["document_id"], unique=True
    )
    op.create_index(
        op.f("ix_document_texts_extraction_status"),
        "document_texts",
        ["extraction_status"],
        unique=False,
    )
    op.create_index(op.f("ix_document_texts_id"), "document_texts", ["id"], unique=False)
    op.create_index(
        op.f("ix_document_texts_text_hash"), "document_texts", ["text_hash"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_texts_text_hash"), table_name="document_texts")
    op.drop_index(op.f("ix_document_texts_id"), table_name="document_texts")
    op.drop_index(op.f("ix_document_texts_extraction_status"), table_name="document_texts")
    op.drop_index(op.f("ix_document_texts_document_id"), table_name="document_texts")
    op.drop_table("document_texts")
