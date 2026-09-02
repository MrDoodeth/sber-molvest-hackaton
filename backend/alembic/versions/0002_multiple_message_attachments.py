"""Allow multiple runtime attachments on one message.

Revision ID: 0002_multi_attachments
Revises: 0001_initial
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_multi_attachments"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_attachment_message", "attachments", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_attachment_message", "attachments", ["message_id"]
    )
