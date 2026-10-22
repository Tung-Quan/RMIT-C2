"""Bind Tide identities and reject replayed private request assertions."""
from alembic import op
import sqlalchemy as sa

revision = "0009_tide_identity"
down_revision = "0008_async_processing_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "email", nullable=True)
    op.alter_column("users", "hashed_password", nullable=True)
    op.add_column("users", sa.Column("tide_identity_key", sa.String(64), nullable=True))
    op.create_index("ix_users_tide_identity_key", "users", ["tide_identity_key"], unique=True)
    op.create_table("gateway_assertions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("expires_at", sa.BigInteger(), nullable=False))
    op.create_index("ix_gateway_assertions_expires_at", "gateway_assertions", ["expires_at"])


def downgrade():
    # Explicitly refuse to turn Tide-only accounts into password-login identities.
    raise RuntimeError("Restore a pre-migration backup to reverse the identity migration")
