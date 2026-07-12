"""Tests de esquema y migración de idempotencia MCP."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MCPIdempotencyRecord, MCPToken, User
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
        assert "mcp_idempotency_records" in inspect(engine).get_table_names()

    def test_columns_exist(self, db_session):
        engine = db_session.get_bind()
        columns = {col["name"]: col for col in inspect(engine).get_columns("mcp_idempotency_records")}
        expected = {
            "id",
            "user_id",
            "token_id",
            "tool_name",
            "idempotency_key",
            "request_hash",
            "status",
            "response_json",
            "resource_version_before",
            "resource_version_after",
            "created_at",
            "updated_at",
            "expires_at",
        }
        assert expected.issubset(columns.keys())
        assert not columns["expires_at"]["nullable"]

    def test_foreign_keys_and_cascade(self, db_session):
        user = User(
            id="user1",
            email="test@example.com",
            name="Test",
            auth_provider="google",
        )
        token = MCPToken(
            id="token1",
            user_id="user1",
            name="Token",
            token_prefix="huginn_mcp_abc123",
            token_hash="a" * 64,
            scopes=["boards:write"],
        )
        db_session.add(user)
        db_session.commit()
        db_session.add(token)
        db_session.commit()
        record = MCPIdempotencyRecord(
            id="rec1",
            user_id="user1",
            token_id="token1",
            tool_name="apply_board_patch",
            idempotency_key="idem-key-01",
            request_hash="b" * 64,
            status="completed",
            response_json={"ok": True},
            expires_at=datetime(2026, 7, 13, 12, 0, 0),
        )
        db_session.add(record)
        db_session.commit()
        assert db_session.query(MCPIdempotencyRecord).count() == 1

        db_session.delete(token)
        db_session.commit()
        assert db_session.query(MCPIdempotencyRecord).count() == 0

    def test_unique_constraint(self, db_session):
        engine = db_session.get_bind()
        uniques = inspect(engine).get_unique_constraints("mcp_idempotency_records")
        assert any(
            item["name"] == "uq_mcp_idempotency_token_tool_key"
            and item["column_names"] == ["token_id", "tool_name", "idempotency_key"]
            for item in uniques
        )

    def test_indexes_exist(self, db_session):
        engine = db_session.get_bind()
        indexes = inspect(engine).get_indexes("mcp_idempotency_records")
        names = {item["name"] for item in indexes}
        assert "ix_mcp_idempotency_records_user_id" in names
        assert "ix_mcp_idempotency_records_token_id" in names
        assert "ix_mcp_idempotency_records_expires_at" in names
        assert "ix_mcp_idempotency_records_status" in names

    def test_status_response_json_and_versions_persist(self, db_session):
        user = User(
            id="user2",
            email="test2@example.com",
            name="Test2",
            auth_provider="google",
        )
        token = MCPToken(
            id="token2",
            user_id="user2",
            name="Token2",
            token_prefix="huginn_mcp_def456",
            token_hash="c" * 64,
            scopes=["boards:write"],
        )
        db_session.add(user)
        db_session.commit()
        db_session.add(token)
        db_session.commit()
        record = MCPIdempotencyRecord(
            id="rec2",
            user_id="user2",
            token_id="token2",
            tool_name="apply_board_patch",
            idempotency_key="idem-key-02",
            request_hash="d" * 64,
            status="completed",
            response_json={"ok": True, "data": {"board_id": "b1"}},
            resource_version_before=7,
            resource_version_after=8,
            expires_at=datetime(2026, 7, 13, 12, 0, 0),
        )
        db_session.add(record)
        db_session.commit()
        loaded = db_session.get(MCPIdempotencyRecord, "rec2")
        assert loaded.status == "completed"
        assert loaded.response_json == {"ok": True, "data": {"board_id": "b1"}}
        assert loaded.resource_version_before == 7
        assert loaded.resource_version_after == 8


class TestMigrationScript:
    def test_upgrade_creates_table(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"
        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_idempotency_records" in inspect(engine).get_table_names()
        engine.dispose()

    def test_upgrade_downgrade_upgrade(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"

        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_idempotency_records" in inspect(engine).get_table_names()
        engine.dispose()

        _run_downgrade_via_alembic(tmp_path, "c112271853fd")

        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_idempotency_records" not in inspect(engine).get_table_names()
        assert "mcp_tokens" in inspect(engine).get_table_names()
        engine.dispose()

        _run_upgrade_via_alembic(tmp_path)
        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_idempotency_records" in inspect(engine).get_table_names()
        engine.dispose()

    def test_other_tables_not_altered(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"
        engine = create_engine(f"sqlite:///{db_path}")
        tables = set(inspect(engine).get_table_names())
        expected = {
            "users",
            "sessions",
            "studios",
            "folders",
            "boards",
            "nodes",
            "edges",
            "mcp_tokens",
            "mcp_idempotency_records",
            "mcp_audit_log",
        }
        for table in expected:
            assert table in tables, f"Falta {table}"
        extra = tables - expected - {"alembic_version"}
        assert not extra, f"Tablas extra: {extra}"
        engine.dispose()
