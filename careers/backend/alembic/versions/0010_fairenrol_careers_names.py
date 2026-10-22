"""Rename the candidate's personal application tracker to FairEnrol terminology.

Revision ID: 0010_fairenrol_careers_names
Revises: 0009_tide_identity
"""
from alembic import op

revision = "0010_fairenrol_careers_names"
down_revision = "0009_tide_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE job_postings SET employment_type='early_career' WHERE employment_type='internship'")
    op.rename_table("internship_applications", "candidate_applications")
    op.drop_index("ix_internship_applications_id", table_name="candidate_applications")
    op.drop_index("ix_internship_applications_user_id", table_name="candidate_applications")
    op.create_index("ix_candidate_applications_id", "candidate_applications", ["id"])
    op.create_index("ix_candidate_applications_user_id", "candidate_applications", ["user_id"])


def downgrade():
    op.drop_index("ix_candidate_applications_user_id", table_name="candidate_applications")
    op.drop_index("ix_candidate_applications_id", table_name="candidate_applications")
    op.rename_table("candidate_applications", "internship_applications")
    op.execute("UPDATE job_postings SET employment_type='internship' WHERE employment_type='early_career'")
    op.create_index("ix_internship_applications_id", "internship_applications", ["id"])
    op.create_index("ix_internship_applications_user_id", "internship_applications", ["user_id"])
