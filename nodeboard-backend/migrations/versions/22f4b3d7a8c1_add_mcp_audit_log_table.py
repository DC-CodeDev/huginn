"""add_mcp_audit_log_table

Revision ID: 22f4b3d7a8c1
Revises: 76c0f900b1a1
Create Date: 2026-07-12 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "22f4b3d7a8c1"
down_revision: Union[str, Sequence[str], None] = "76c0f900b1a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mcp_audit_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=True),
        sa.Column("token_id", sa.String(32), nullable=True),
        sa.Column("client_name", sa.String(200), nullable=True),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(200), nullable=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("affected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version_before", sa.Integer(), nullable=True),
        sa.Column("version_after", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("is_replay", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("idempotency_key_prefix", sa.String(32), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["mcp_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_mcp_audit_log_user_id", "mcp_audit_log", ["user_id"], unique=False)
    op.create_index("ix_mcp_audit_log_token_id", "mcp_audit_log", ["token_id"], unique=False)
    op.create_index("ix_mcp_audit_log_tool_name", "mcp_audit_log", ["tool_name"], unique=False)
    op.create_index("ix_mcp_audit_log_request_id", "mcp_audit_log", ["request_id"], unique=False)
    op.create_index("ix_mcp_audit_log_resource_id", "mcp_audit_log", ["resource_id"], unique=False)
    op.create_index("ix_mcp_audit_log_status", "mcp_audit_log", ["status"], unique=False)
    op.create_index("ix_mcp_audit_log_created_at", "mcp_audit_log", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_mcp_audit_log_created_at", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_log_status", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_log_resource_id", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_log_request_id", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_log_tool_name", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_log_token_id", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_log_user_id", table_name="mcp_audit_log")
    op.drop_table("mcp_audit_log")
