"""Persist runtime message processing state for reconnecting clients.

Revision ID: 0003_message_processing
Revises: 0002_multi_attachments
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0003_message_processing"
down_revision: str | None = "0002_multi_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("processing_status", sa.String(length=16), nullable=True),
    )
    op.add_column("messages", sa.Column("processing_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_message_processing_status",
        "messages",
        "processing_status IS NULL OR processing_status IN "
        "('pending', 'processing', 'completed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_message_processing_status", "messages", type_="check")
    op.drop_column("messages", "processing_error")
    op.drop_column("messages", "processing_status")
