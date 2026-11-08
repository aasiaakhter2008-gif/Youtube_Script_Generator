"""Initial schema (all SQLModel tables).

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-05
"""

from alembic import op

from app.models.db import SQLModel

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind())
