from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.mcp.context import MCPContext
from app.mcp.errors import InsufficientScope
from app.mcp.read_guard import ReadResult, execute_read_tool
from app.models import MCPAuditLog, MCPToken, User
from app.mcp.auth import _now
from app.services import mcp_rate_limit
from app.services.errors import ResourceNotFound, ValidationFailure


@pytest.fixture(autouse=True)
def _reset_rate_limit(monkeypatch):
    for name in (
        "MCP_RATE_LIMIT_ENABLED",
        "MCP_RATE_LIMIT_READ_PER_MINUTE",
        "MCP_RATE_LIMIT_WRITE_PER_MINUTE",
        "MCP_RATE_LIMIT_BATCH_PER_MINUTE",
        "MCP_RATE_LIMIT_PATCH_PER_MINUTE",
        "MCP_RATE_LIMIT_LAYOUT_PER_MINUTE",
        "MCP_RATE_LIMIT_BUCKET_TTL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    mcp_rate_limit.clear_default_rate_limiter()
    yield
    mcp_rate_limit.clear_default_rate_limiter()


@pytest.fixture()
def db_session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db(db_session_factory):
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db) -> User:
    item = User(
        id=uuid.uuid4().hex[:16],
        email="read-guard@test.com",
        name="Read Guard User",
        auth_provider="google",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def ctx(db, user) -> MCPContext:
    token = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=user.id,
        name="Read Guard Token",
        token_prefix="huginn_mcp_read_guard",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        scopes=["boards:read", "nodes:read", "studios:read", "folders:read"],
    )
    db.add(token)
    db.commit()
    now = _now()
    return MCPContext(
        user_id=user.id,
        token_id=token.id,
        scopes=frozenset(token.scopes),
        constraints=None,
        token_prefix=token.token_prefix,
        expires_at=now + timedelta(days=30),
        client_name="pytest-read-guard",
        request_id="req-read-guard-001",
    )


def _audits(db: Session) -> list[MCPAuditLog]:
    return list(
        db.query(MCPAuditLog)
        .order_by(MCPAuditLog.created_at.asc(), MCPAuditLog.id.asc())
        .all()
    )


class TestExecuteReadTool:
    def test_success_audits_and_preserves_response(self, db, db_session_factory, ctx):
        result = execute_read_tool(
            db_session_factory,
            ctx=ctx,
            tool_name="get_board",
            capability_type="board",
            audit_resource_type="board",
            audit_resource_id="board-1",
            operation=lambda: ReadResult(
                response={"id": "board-1", "nodes": []},
                resource_type="board",
                resource_id="board-1",
                returned_count=1,
                metadata={
                    "returned_count": 1,
                    "include_images": False,
                    "title": "secreto",
                },
            ),
        )

        assert result == {"id": "board-1", "nodes": []}
        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].tool_name == "get_board"
        assert audits[0].status == "success"
        assert audits[0].resource_type == "board"
        assert audits[0].resource_id == "board-1"
        assert audits[0].affected_count == 1
        assert audits[0].request_id == "req-read-guard-001"
        assert audits[0].client_name == "pytest-read-guard"
        assert audits[0].metadata_json == {
            "returned_count": 1,
            "include_images": False,
        }

    def test_domain_error_is_audited_and_mapped(self, db, db_session_factory, ctx):
        with pytest.raises(ValueError, match="Board no encontrado"):
            execute_read_tool(
                db_session_factory,
                ctx=ctx,
                tool_name="get_board",
                capability_type="board",
                audit_resource_type="board",
                audit_resource_id="board-x",
                operation=lambda: (_ for _ in ()).throw(
                    ResourceNotFound("board", "board-x", "Board no encontrado")
                ),
            )

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].status == "error"
        assert audits[0].error_code == "RESOURCE_NOT_FOUND"

    def test_validation_value_error_is_audited_and_preserved(self, db, db_session_factory, ctx):
        with pytest.raises(ValueError, match="limit debe"):
            execute_read_tool(
                db_session_factory,
                ctx=ctx,
                tool_name="list_boards",
                capability_type="board",
                audit_resource_type="studio",
                audit_resource_id="studio-1",
                operation=lambda: (_ for _ in ()).throw(ValueError("limit debe estar entre 1 y 100")),
            )

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].error_code == "VALIDATION_FAILURE"

    def test_forbidden_error_is_audited_and_preserved(self, db, db_session_factory, ctx):
        with pytest.raises(InsufficientScope):
            execute_read_tool(
                db_session_factory,
                ctx=ctx,
                tool_name="get_node",
                capability_type="node",
                audit_resource_type="node",
                audit_resource_id="node-1",
                operation=lambda: (_ for _ in ()).throw(InsufficientScope("faltan scopes")),
            )

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].error_code == "FORBIDDEN_RESOURCE"

    def test_unexpected_error_is_audited_and_preserved(self, db, db_session_factory, ctx):
        with pytest.raises(RuntimeError, match="boom"):
            execute_read_tool(
                db_session_factory,
                ctx=ctx,
                tool_name="list_studios",
                capability_type="studio",
                audit_resource_type="studio",
                audit_resource_id=None,
                operation=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            )

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].error_code == "INTERNAL_ERROR"

    def test_rate_limit_is_audited_before_operation(self, db, db_session_factory, ctx, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT_READ_PER_MINUTE", "1")
        mcp_rate_limit.clear_default_rate_limiter()
        calls = {"count": 0}

        def op():
            calls["count"] += 1
            return ReadResult(
                response={"studios": []},
                resource_type="studio",
                resource_id=None,
                returned_count=0,
            )

        execute_read_tool(
            db_session_factory,
            ctx=ctx,
            tool_name="list_studios",
            capability_type="studio",
            audit_resource_type="studio",
            audit_resource_id=None,
            operation=op,
        )
        with pytest.raises(ValueError, match="RATE_LIMIT_EXCEEDED"):
            execute_read_tool(
                db_session_factory,
                ctx=ctx,
                tool_name="list_studios",
                capability_type="studio",
                audit_resource_type="studio",
                audit_resource_id=None,
                operation=op,
            )

        assert calls["count"] == 1
        audits = _audits(db)
        assert [item.status for item in audits] == ["success", "error"]
        assert audits[1].error_code == "RATE_LIMIT_EXCEEDED"
        assert audits[1].metadata_json == {
            "limit": 1,
            "window_seconds": 60,
            "retry_after_seconds": 60,
        }

    def test_duration_is_recorded(self, db, db_session_factory, ctx, monkeypatch):
        import app.mcp.read_guard as guard

        values = iter([10.0, 10.25])
        monkeypatch.setattr(guard.time, "perf_counter", lambda: next(values))

        execute_read_tool(
            db_session_factory,
            ctx=ctx,
            tool_name="get_board_summary",
            capability_type="board",
            audit_resource_type="board",
            audit_resource_id="board-1",
            operation=lambda: ReadResult(
                response={"id": "board-1"},
                resource_type="board",
                resource_id="board-1",
                returned_count=1,
            ),
        )

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].duration_ms == 250

    def test_audit_failure_does_not_replace_original_exception(self, db_session_factory, ctx, monkeypatch):
        import app.mcp.mutation_guard as guard

        def boom(*args, **kwargs):
            raise RuntimeError("audit failed")

        monkeypatch.setattr(guard, "create_audit_entry", boom)

        with pytest.raises(RuntimeError, match="boom-real"):
            execute_read_tool(
                db_session_factory,
                ctx=ctx,
                tool_name="get_node",
                capability_type="node",
                audit_resource_type="node",
                audit_resource_id="node-1",
                operation=lambda: (_ for _ in ()).throw(RuntimeError("boom-real")),
            )

    def test_domain_exception_preserves_original_message_when_mapped(self, db, db_session_factory, ctx):
        with pytest.raises(ValueError, match="payload inválido"):
            execute_read_tool(
                db_session_factory,
                ctx=ctx,
                tool_name="list_boards",
                capability_type="board",
                audit_resource_type="studio",
                audit_resource_id="studio-1",
                operation=lambda: (_ for _ in ()).throw(ValidationFailure("payload inválido")),
            )

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].error_code == "VALIDATION_FAILURE"
