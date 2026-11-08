"""Add owner column to scriptjob for per-user daily quota.

Revision ID: 0002_owner
Revises: 0001_initial

0001_initial creates tables from the live SQLModel metadata, so on a *fresh* database
the owner column already exists. This migration is therefore idempotent: it only adds
the column/index for databases created before the feature.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_owner"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table)}


def _index_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    if "scriptjob" not in sa.inspect(op.get_bind()).get_table_names():
        return
    if "owner" not in _column_names("scriptjob"):
        with op.batch_alter_table("scriptjob") as batch_op:
            batch_op.add_column(sa.Column("owner", sa.String(), nullable=False, server_default="global"))
    if "ix_scriptjob_owner" not in _index_names("scriptjob"):
        op.create_index("ix_scriptjob_owner", "scriptjob", ["owner"])


def downgrade() -> None:
    if "scriptjob" not in sa.inspect(op.get_bind()).get_table_names():
        return
    if "ix_scriptjob_owner" in _index_names("scriptjob"):
        op.drop_index("ix_scriptjob_owner", table_name="scriptjob")
    if "owner" in _column_names("scriptjob"):
        with op.batch_alter_table("scriptjob") as batch_op:
            batch_op.drop_column("owner")
