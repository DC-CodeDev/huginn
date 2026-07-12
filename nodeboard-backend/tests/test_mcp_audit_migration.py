"""Tests de esquema y migración de auditoría MCP."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MCPAuditLog, MCPToken, User
from tests.test_mcp_tokens_migration import (
    _run_downgrade_via_alembic,
    _run_upgrade_via_alembic,
)


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / "nodeboard.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestSchema:
    def test_table_created(self, db_session):
        engine = db_session.get_bind()
        assert "mcp_audit_log" in inspect(engine).get_table_names()

    def test_columns_exist(self, db_session):
        engine = db_session.get_bind()
        columns = {col["name"]: col for col in inspect(engine).get_columns("mcp_audit_log")}
        expected = {
            "id",
            "user_id",
            "token_id",
            "client_name",
            "tool_name",
            "request_id",
            "resource_type",
            "resource_id",
            "status",
            "error_code",
            "affected_count",
            "version_before",
            "version_after",
            "duration_ms",
            "is_replay",
            "idempotency_key_prefix",
            "metadata_json",
            "created_at",
        }
        assert expected.issubset(columns.keys())
        assert columns["user_id"]["nullable"]
        assert columns["token_id"]["nullable"]
        assert not columns["duration_ms"]["nullable"]

    def test_foreign_keys_set_null_when_token_deleted(self, db_session):
        user = User(
            id="user-audit-1",
            email="audit1@example.com",
            name="Audit One",
            auth_provider="google",
        )
        token = MCPToken(
            id="token-audit-1",
            user_id=user.id,
            name="Token",
            token_prefix="huginn_mcp_audit",
            token_hash="a" * 64,
            scopes=["boards:write"],
        )
        db_session.add(user)
        db_session.commit()
        db_session.add(token)
        db_session.commit()
        entry = MCPAuditLog(
            id="audit-1",
            user_id=user.id,
            token_id=token.id,
            client_name="pytest",
            tool_name="apply_board_patch",
            request_id="req-1",
            resource_type="board",
            resource_id="board-1",
            status="success",
            affected_count=1,
            duration_ms=12,
            is_replay=False,
            idempotency_key_prefix="patch-20…",
            metadata_json={"operation_count": 1, "dry_run": False},
            created_at=datetime(2026, 7, 12, 12, 0, 0),
        )
        db_session.add(entry)
        db_session.commit()

        db_session.delete(token)
        db_session.commit()

        loaded = db_session.get(MCPAuditLog, "audit-1")
        assert loaded is not None
        assert loaded.token_id is None
        assert loaded.user_id == user.id

    def test_foreign_keys_set_null_when_user_deleted(self, db_session):
        user = User(
            id="user-audit-2",
            email="audit2@example.com",
            name="Audit Two",
            auth_provider="google",
        )
        token = MCPToken(
            id="token-audit-2",
            user_id=user.id,
            name="Token",
            token_prefix="huginn_mcp_audit",
            token_hash="b" * 64,
            scopes=["boards:write"],
        )
        db_session.add(user)
        db_session.commit()
        db_session.add(token)
        db_session.commit()
        entry = MCPAuditLog(
            id="audit-2",
            user_id=user.id,
            token_id=token.id,
            client_name="pytest",
            tool_name="apply_board_patch",
            request_id="req-2",
            resource_type="board",
            resource_id="board-2",
            status="error",
            error_code="VERSION_CONFLICT",
            affected_count=0,
            duration_ms=20,
            is_replay=False,
            metadata_json={"operation_count": 2, "dry_run": False},
            created_at=datetime(2026, 7, 12, 12, 0, 0),
        )
        db_session.add(entry)
        db_session.commit()

        db_session.delete(user)
        db_session.commit()

        loaded = db_session.get(MCPAuditLog, "audit-2")
        assert loaded is not None
        assert loaded.user_id is None
        assert loaded.token_id is None

    def test_indexes_exist(self, db_session):
        engine = db_session.get_bind()
        indexes = inspect(engine).get_indexes("mcp_audit_log")
        names = {item["name"] for item in indexes}
        assert "ix_mcp_audit_log_user_id" in names
        assert "ix_mcp_audit_log_token_id" in names
        assert "ix_mcp_audit_log_tool_name" in names
        assert "ix_mcp_audit_log_request_id" in names
        assert "ix_mcp_audit_log_resource_id" in names
        assert "ix_mcp_audit_log_status" in names
        assert "ix_mcp_audit_log_created_at" in names

    def test_metadata_and_timestamps_persist(self, db_session):
        entry = MCPAuditLog(
            id="audit-3",
            user_id=None,
            token_id=None,
            client_name="client",
            tool_name="apply_board_patch",
            request_id="req-3",
            resource_type="board",
            resource_id="board-3",
            status="replay",
            affected_count=0,
            version_before=4,
            version_after=5,
            duration_ms=9,
            is_replay=True,
            idempotency_key_prefix="patch-30…",
            metadata_json={"operation_count": 3, "dry_run": False},
            created_at=datetime(2026, 7, 12, 12, 0, 0),
        )
        db_session.add(entry)
        db_session.commit()

        loaded = db_session.get(MCPAuditLog, "audit-3")
        assert loaded.metadata_json == {"operation_count": 3, "dry_run": False}
        assert loaded.version_before == 4
        assert loaded.version_after == 5
        assert loaded.is_replay is True


class TestMigrationScript:
    def test_upgrade_creates_table(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"
        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_audit_log" in inspect(engine).get_table_names()
        engine.dispose()

    def test_upgrade_downgrade_upgrade(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"

        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_audit_log" in inspect(engine).get_table_names()
        engine.dispose()

        _run_downgrade_via_alembic(tmp_path, "76c0f900b1a1")

        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_audit_log" not in inspect(engine).get_table_names()
        assert "mcp_idempotency_records" in inspect(engine).get_table_names()
        engine.dispose()

        _run_upgrade_via_alembic(tmp_path)
        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_audit_log" in inspect(engine).get_table_names()
        engine.dispose()
