"""Remove persisted model timer artifacts from chat output.

Revision ID: 0004_clean_model_output_artifacts
Revises: 0003_message_processing
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0004_clean_output"
down_revision: str | None = "0003_message_processing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LEADING_TIMER = r"^[[:space:]]*осталось[[:space:]]+[0-9]{1,2}:[0-9]{2}[[:space:]]*"


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE messages
            SET text = regexp_replace(text, :pattern, '', 'i')
            WHERE author_type = 'assistant' AND text ~* :pattern
            """
        ),
        {"pattern": _LEADING_TIMER},
    )
    connection.execute(
        sa.text(
            """
            UPDATE operator_drafts
            SET text = regexp_replace(text, :pattern, '', 'i')
            WHERE text ~* :pattern
            """
        ),
        {"pattern": _LEADING_TIMER},
    )


def downgrade() -> None:
    pass
