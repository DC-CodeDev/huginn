"""add_mcp_idempotency_records_table

Revision ID: 76c0f900b1a1
Revises: 7cd589ffac5e
Create Date: 2026-07-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "76c0f900b1a1"
down_revision: Union[str, Sequence[str], None] = "c112271853fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mcp_idempotency_records",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), nullable=False),
        sa.Column("token_id", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("resource_version_before", sa.Integer(), nullable=True),
        sa.Column("resource_version_after", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["mcp_tokens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "token_id",
            "tool_name",
            "idempotency_key",
            name="uq_mcp_idempotency_token_tool_key",
        ),
    )
    op.create_index(
        "ix_mcp_idempotency_records_user_id",
        "mcp_idempotency_records",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_idempotency_records_token_id",
        "mcp_idempotency_records",
        ["token_id"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_idempotency_records_expires_at",
        "mcp_idempotency_records",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_idempotency_records_status",
        "mcp_idempotency_records",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_mcp_idempotency_records_status", table_name="mcp_idempotency_records")
    op.drop_index("ix_mcp_idempotency_records_expires_at", table_name="mcp_idempotency_records")
    op.drop_index("ix_mcp_idempotency_records_token_id", table_name="mcp_idempotency_records")
    op.drop_index("ix_mcp_idempotency_records_user_id", table_name="mcp_idempotency_records")
    op.drop_table("mcp_idempotency_records")
