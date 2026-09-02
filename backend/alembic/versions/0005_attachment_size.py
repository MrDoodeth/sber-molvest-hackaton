"""Persist runtime attachment sizes for validation and UI display.

Revision ID: 0005_attachment_size
Revises: 0004_clean_output
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0005_attachment_size"
down_revision: str | None = "0004_clean_output"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("size_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attachments", "size_bytes")
