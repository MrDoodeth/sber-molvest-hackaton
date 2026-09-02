"""Initial modular-monolith schema.

Revision ID: 0001_initial
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENUMS: dict[str, tuple[str, ...]] = {
    "user_role": ("user", "operator", "admin"),
    "dialog_status": ("active", "closed"),
    "dialog_mode": ("ai_support", "operator_support"),
    "dialog_channel": ("web", "bitrix24", "redmine"),
    "feedback_verdict": ("helpful", "ai_error"),
    "message_author": ("user", "assistant", "operator", "system"),
    "document_source_type": ("official_1c_docs", "internal_kb", "resolved_case"),
    "document_index_status": ("uploaded", "processing", "indexed", "failed"),
    "candidate_source": ("user_feedback", "operator", "admin"),
    "candidate_status": ("pending", "approved", "rejected"),
    "prompt_type": ("user_support", "operator_gigachat"),
}


def enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role", enum("user_role"), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "knowledge_sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "dialogs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", enum("dialog_status"), nullable=False),
        sa.Column("mode", enum("dialog_mode"), nullable=False),
        sa.Column("channel", enum("dialog_channel"), nullable=False),
        sa.Column("dialog_confidence", sa.Float(), nullable=False),
        sa.Column("assigned_operator_id", sa.Uuid(), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dialog_confidence >= 0 AND dialog_confidence <= 1",
            name="ck_dialog_confidence_range",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND closed_at IS NULL) OR "
            "(status = 'closed' AND closed_at IS NOT NULL)",
            name="ck_dialog_closed_at_matches_status",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_operator_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dialog_user_updated", "dialogs", ["user_id", "updated_at"])
    op.create_index(
        "ix_dialog_operator_queue",
        "dialogs",
        ["status", "mode", "assigned_operator_id"],
    )
    op.create_index(
        "ix_dialogs_assigned_operator_id", "dialogs", ["assigned_operator_id"]
    )
    op.create_index("ix_dialogs_user_id", "dialogs", ["user_id"])

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", enum("document_source_type"), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("one_c_version", sa.String(length=100), nullable=True),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("index_status", enum("document_index_status"), nullable=False),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["section_id"], ["knowledge_sections.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_document_section_status",
        "knowledge_documents",
        ["section_id", "index_status"],
    )
    op.create_index(
        "ix_knowledge_documents_section_id", "knowledge_documents", ["section_id"]
    )

    op.create_table(
        "system_prompts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", enum("prompt_type"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint("version >= 1", name="ck_prompt_version_positive"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("type", "version", name="uq_prompt_type_version"),
    )
    op.create_index(
        "uq_prompt_active_type",
        "system_prompts",
        ["type"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "dialog_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dialog_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", enum("feedback_verdict"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dialog_id"], ["dialogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dialog_id", name="uq_feedback_dialog"),
    )
    op.create_index("ix_dialog_feedback_dialog_id", "dialog_feedback", ["dialog_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dialog_id", sa.Uuid(), nullable=False),
        sa.Column("client_message_id", sa.Uuid(), nullable=True),
        sa.Column("author_type", enum("message_author"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_message_confidence_range",
        ),
        sa.ForeignKeyConstraint(["dialog_id"], ["dialogs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dialog_id", "client_message_id", name="uq_message_dialog_client_id"
        ),
    )
    op.create_index(
        "ix_message_dialog_created", "messages", ["dialog_id", "created_at", "id"]
    )
    op.create_index("ix_messages_dialog_id", "messages", ["dialog_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("doc_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("vector_id", sa.Uuid(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["doc_id"], ["knowledge_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vector_id", name="uq_chunk_vector_id"),
    )
    op.create_index("ix_chunk_doc", "chunks", ["doc_id"])

    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("gigachat_file_id", sa.String(length=255), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("visual_summary", sa.Text(), nullable=True),
        sa.Column("remote_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_attachment_message"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_attachments_message_id", "attachments", ["message_id"])

    op.create_table(
        "operator_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dialog_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_message_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_draft_confidence_range",
        ),
        sa.ForeignKeyConstraint(["dialog_id"], ["dialogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["trigger_message_id"], ["messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trigger_message_id", name="uq_draft_trigger_message"),
    )
    op.create_index("ix_operator_drafts_dialog_id", "operator_drafts", ["dialog_id"])
    op.create_index(
        "ix_operator_drafts_trigger_message_id",
        "operator_drafts",
        ["trigger_message_id"],
    )

    op.create_table(
        "knowledge_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dialog_id", sa.Uuid(), nullable=False),
        sa.Column("source", enum("candidate_source"), nullable=False),
        sa.Column(
            "generated_card", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("status", enum("candidate_status"), nullable=False),
        sa.Column("resulting_document_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dialog_id"], ["dialogs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resulting_document_id"],
            ["knowledge_documents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dialog_id", name="uq_candidate_dialog"),
    )
    op.create_index(
        "ix_knowledge_candidates_dialog_id", "knowledge_candidates", ["dialog_id"]
    )

    op.create_table(
        "metric_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dialog_id", sa.Uuid(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("escalated", sa.Boolean(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("precached_prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("gigachat_model", sa.String(length=100), nullable=True),
        sa.Column("system_prompt_version", sa.Integer(), nullable=True),
        sa.Column("rag_top_k", sa.Integer(), nullable=True),
        sa.Column("operator_escalation_threshold", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("latency_ms >= 0", name="ck_metric_latency_nonnegative"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_metric_confidence_range",
        ),
        sa.CheckConstraint(
            "prompt_tokens IS NULL OR prompt_tokens >= 0",
            name="ck_metric_prompt_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "completion_tokens IS NULL OR completion_tokens >= 0",
            name="ck_metric_completion_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "precached_prompt_tokens IS NULL OR precached_prompt_tokens >= 0",
            name="ck_metric_precached_tokens_nonnegative",
        ),
        sa.CheckConstraint(
            "system_prompt_version IS NULL OR system_prompt_version >= 1",
            name="ck_metric_prompt_version_positive",
        ),
        sa.CheckConstraint(
            "rag_top_k IS NULL OR rag_top_k >= 1",
            name="ck_metric_rag_top_k_positive",
        ),
        sa.CheckConstraint(
            "operator_escalation_threshold IS NULL OR "
            "(operator_escalation_threshold >= 0 AND "
            "operator_escalation_threshold <= 1)",
            name="ck_metric_threshold_range",
        ),
        sa.ForeignKeyConstraint(["dialog_id"], ["dialogs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_created", "metric_events", ["created_at"])
    op.create_index("ix_metric_events_dialog_id", "metric_events", ["dialog_id"])


def downgrade() -> None:
    op.drop_table("metric_events")
    op.drop_table("knowledge_candidates")
    op.drop_table("operator_drafts")
    op.drop_table("attachments")
    op.drop_table("chunks")
    op.drop_table("messages")
    op.drop_table("dialog_feedback")
    op.drop_index("uq_prompt_active_type", table_name="system_prompts")
    op.drop_table("system_prompts")
    op.drop_table("knowledge_documents")
    op.drop_table("dialogs")
    op.drop_table("system_settings")
    op.drop_table("knowledge_sections")
    op.drop_table("users")
    bind = op.get_bind()
    for name in reversed(tuple(ENUMS)):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
