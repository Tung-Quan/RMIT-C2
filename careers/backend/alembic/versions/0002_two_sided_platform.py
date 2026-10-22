"""Add two-sided platform foundation.

Revision ID: 0002_two_sided_platform
Revises: 0001_initial
Create Date: 2026-06-09
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_two_sided_platform"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "role" not in user_columns:
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=20), nullable=False, server_default="candidate"),
        )

    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("university", sa.String(length=255), nullable=True),
        sa.Column("major", sa.String(length=255), nullable=True),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("github_url", sa.String(length=500), nullable=True),
        sa.Column("portfolio_url", sa.String(length=500), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_candidate_profiles_id"), "candidate_profiles", ["id"], unique=False)
    op.create_index(
        op.f("ix_candidate_profiles_user_id"),
        "candidate_profiles",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
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
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_companies_id"), "companies", ["id"], unique=False)
    op.create_index(op.f("ix_companies_owner_user_id"), "companies", ["owner_user_id"], unique=True)

    op.create_table(
        "job_postings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("employment_type", sa.String(length=50), nullable=False),
        sa.Column("work_mode", sa.String(length=50), nullable=False),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
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
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_job_postings_company_id"), "job_postings", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_job_postings_created_by_user_id"),
        "job_postings",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_job_postings_id"), "job_postings", ["id"], unique=False)

    op.create_table(
        "job_applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_posting_id", sa.Integer(), nullable=False),
        sa.Column("candidate_user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("cover_letter_text", sa.Text(), nullable=True),
        sa.Column("candidate_note", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
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
        sa.ForeignKeyConstraint(["candidate_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_postings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_posting_id",
            "candidate_user_id",
            name="uq_job_applications_job_candidate",
        ),
    )
    op.create_index(
        op.f("ix_job_applications_candidate_user_id"),
        "job_applications",
        ["candidate_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_job_applications_id"), "job_applications", ["id"], unique=False)
    op.create_index(
        op.f("ix_job_applications_job_posting_id"),
        "job_applications",
        ["job_posting_id"],
        unique=False,
    )

    op.create_table(
        "job_application_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_application_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["job_application_id"], ["job_applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_application_id",
            "document_id",
            name="uq_job_application_documents_attachment",
        ),
    )
    op.create_index(
        op.f("ix_job_application_documents_document_id"),
        "job_application_documents",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_application_documents_id"),
        "job_application_documents",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_job_application_documents_job_application_id"),
        "job_application_documents",
        ["job_application_id"],
        unique=False,
    )

    op.create_table(
        "application_status_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_application_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["job_application_id"], ["job_applications.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_status_history_changed_by_user_id"),
        "application_status_history",
        ["changed_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_status_history_id"),
        "application_status_history",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_application_status_history_job_application_id"),
        "application_status_history",
        ["job_application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_application_status_history_job_application_id"),
        table_name="application_status_history",
    )
    op.drop_index(
        op.f("ix_application_status_history_id"),
        table_name="application_status_history",
    )
    op.drop_index(
        op.f("ix_application_status_history_changed_by_user_id"),
        table_name="application_status_history",
    )
    op.drop_table("application_status_history")

    op.drop_index(
        op.f("ix_job_application_documents_job_application_id"),
        table_name="job_application_documents",
    )
    op.drop_index(op.f("ix_job_application_documents_id"), table_name="job_application_documents")
    op.drop_index(
        op.f("ix_job_application_documents_document_id"),
        table_name="job_application_documents",
    )
    op.drop_table("job_application_documents")

    op.drop_index(op.f("ix_job_applications_job_posting_id"), table_name="job_applications")
    op.drop_index(op.f("ix_job_applications_id"), table_name="job_applications")
    op.drop_index(op.f("ix_job_applications_candidate_user_id"), table_name="job_applications")
    op.drop_table("job_applications")

    op.drop_index(op.f("ix_job_postings_id"), table_name="job_postings")
    op.drop_index(op.f("ix_job_postings_created_by_user_id"), table_name="job_postings")
    op.drop_index(op.f("ix_job_postings_company_id"), table_name="job_postings")
    op.drop_table("job_postings")

    op.drop_index(op.f("ix_companies_owner_user_id"), table_name="companies")
    op.drop_index(op.f("ix_companies_id"), table_name="companies")
    op.drop_table("companies")

    op.drop_index(op.f("ix_candidate_profiles_user_id"), table_name="candidate_profiles")
    op.drop_index(op.f("ix_candidate_profiles_id"), table_name="candidate_profiles")
    op.drop_table("candidate_profiles")

    op.drop_column("users", "role")
