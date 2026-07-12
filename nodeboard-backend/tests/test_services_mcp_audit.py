"""Tests del servicio de auditoría MCP."""

from __future__ import annotations

import uuid
from datetime import datetime
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MCPAuditLog, MCPToken, Studio, User
from app.services.mcp_audit import (
    MCP_AUDIT_STATUS_ERROR,
    MCP_AUDIT_STATUS_REPLAY,
    MCP_AUDIT_STATUS_STATE_UNCERTAIN,
    MCP_AUDIT_STATUS_SUCCESS,
    build_audit_metadata,
    create_audit_entry,
    get_audit_entry,
    list_audit_entries,
    purge_old_audit_entries,
    summarise_idempotency_key,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db) -> User:
    item = User(
        id=uuid.uuid4().hex[:16],
        email="audit-owner@test.com",
        name="Audit Owner",
        auth_provider="google",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def other_user(db) -> User:
    item = User(
        id=uuid.uuid4().hex[:16],
        email="audit-other@test.com",
        name="Audit Other",
        auth_provider="google",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def token(db, user) -> MCPToken:
    studio = Studio(
        id=uuid.uuid4().hex[:16],
        name="Studio",
        color="blue",
        user_id=user.id,
    )
    db.add(studio)
    db.commit()

    item = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=user.id,
        name="Primary",
        token_prefix="huginn_mcp_audit",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        scopes=["boards:write"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def other_token(db, other_user) -> MCPToken:
    studio = Studio(
        id=uuid.uuid4().hex[:16],
        name="Other Studio",
        color="green",
        user_id=other_user.id,
    )
    db.add(studio)
    db.commit()

    item = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=other_user.id,
        name="Secondary",
        token_prefix="huginn_mcp_audit2",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        scopes=["boards:write"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


class TestBuildAuditMetadata:
    def test_filters_sensitive_fields(self):
        metadata = build_audit_metadata(
            {
                "operation_count": 5,
                "summary": {
                    "nodes_created": 1,
                    "nodes_updated": 1,
                    "blocks": 99,
                    "label": "secret",
                },
                "dry_run": False,
                "token": "secret-token",
                "token_hash": "hash",
                "Authorization": "Bearer secret",
                "blocks": [{"id": "b1"}],
                "stages": [{"id": "s1"}],
                "tags": ["sensitive"],
                "label": "hidden",
                "payload": {"raw": True},
                "response_json": {"raw": True},
                "request_hash": "abc",
                "limit": 10,
                "window_seconds": 60,
                "retry_after_seconds": 12,
            }
        )
        assert metadata == {
            "operation_count": 5,
            "summary": {
                "nodes_created": 1,
                "nodes_updated": 1,
            },
            "dry_run": False,
            "limit": 10,
            "window_seconds": 60,
            "retry_after_seconds": 12,
        }

    def test_idempotency_prefix_is_shortened(self):
        assert summarise_idempotency_key("patch-2024-long-key") == "patch-20…"


class TestCreateAndReadAuditEntries:
    def test_create_success_entry(self, db, user, token):
        entry = create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name="pytest-client",
            tool_name="apply_board_patch",
            request_id="req-1",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_SUCCESS,
            affected_count=5,
            version_before=1,
            version_after=2,
            duration_ms=12.4,
            idempotency_key="patch-2024-long-key",
            metadata={
                "operation_count": 5,
                "summary": {"nodes_created": 1},
                "dry_run": False,
            },
        )
        loaded = get_audit_entry(db, entry.id)
        assert loaded is not None
        assert loaded.status == "success"
        assert loaded.error_code is None
        assert loaded.duration_ms == 12
        assert loaded.idempotency_key_prefix == "patch-20…"
        assert loaded.metadata_json == {
            "operation_count": 5,
            "summary": {"nodes_created": 1},
            "dry_run": False,
        }

    def test_create_error_replay_and_uncertain_entries(self, db, user, token):
        error_entry = create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-err",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_ERROR,
            error_code="VERSION_CONFLICT",
            affected_count=0,
            duration_ms=5,
        )
        replay_entry = create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-replay",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_REPLAY,
            affected_count=0,
            version_before=1,
            version_after=2,
            duration_ms=6,
            is_replay=True,
            metadata={"original_affected_count": 5},
        )
        uncertain_entry = create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-uncertain",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_STATE_UNCERTAIN,
            error_code="IDEMPOTENCY_STATE_UNCERTAIN",
            affected_count=5,
            version_before=1,
            version_after=2,
            duration_ms=7,
        )
        assert error_entry.error_code == "VERSION_CONFLICT"
        assert replay_entry.is_replay is True
        assert replay_entry.metadata_json == {"original_affected_count": 5}
        assert uncertain_entry.status == "state_uncertain"

    def test_list_filters_and_limit(self, db, user, token, other_user, other_token):
        create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-a",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_SUCCESS,
            affected_count=1,
            duration_ms=1,
        )
        create_audit_entry(
            db,
            user_id=other_user.id,
            token_id=other_token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-b",
            resource_type="board",
            resource_id="board-2",
            status=MCP_AUDIT_STATUS_ERROR,
            error_code="VALIDATION_FAILURE",
            affected_count=0,
            duration_ms=2,
        )
        create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-c",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_REPLAY,
            affected_count=0,
            duration_ms=3,
            is_replay=True,
        )

        entries = list_audit_entries(db, user_id=user.id, limit=200)
        assert len(entries) == 2
        assert all(item.user_id == user.id for item in entries)

        filtered = list_audit_entries(
            db,
            token_id=token.id,
            status=MCP_AUDIT_STATUS_REPLAY,
            resource_id="board-1",
            limit=10,
        )
        assert len(filtered) == 1
        assert filtered[0].request_id == "req-c"

    def test_purge_old_entries(self, db, user, token):
        now = datetime(2026, 7, 12, 12, 0, 0)
        old_entry = create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-old",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_SUCCESS,
            affected_count=1,
            duration_ms=1,
            created_at=now - timedelta(days=91),
        )
        old_entry_id = old_entry.id
        create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-new",
            resource_type="board",
            resource_id="board-1",
            status=MCP_AUDIT_STATUS_SUCCESS,
            affected_count=1,
            duration_ms=1,
            created_at=now - timedelta(days=1),
        )

        deleted = purge_old_audit_entries(db, now=now, retention_days=90)

        assert deleted == 1
        assert get_audit_entry(db, old_entry_id) is None

    def test_preserves_audit_when_token_is_deleted(self, db, user, token):
        entry = create_audit_entry(
            db,
            user_id=user.id,
            token_id=token.id,
            client_name=None,
            tool_name="apply_board_patch",
            request_id="req-delete",
            resource_type="board",
            resource_id="board-9",
            status=MCP_AUDIT_STATUS_SUCCESS,
            affected_count=1,
            duration_ms=1,
        )

        db.delete(token)
        db.commit()

        loaded = get_audit_entry(db, entry.id)
        assert loaded is not None
        assert loaded.token_id is None
        assert loaded.user_id == user.id
