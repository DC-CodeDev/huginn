from __future__ import annotations

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Board, Folder, MCPAuditLog, MCPToken, Node, Studio, User
from app.mcp.auth import _now
from app.mcp.context import MCPContext, mcp_context_var
from app.mcp.server import _build_mcp
from app.services import mcp_rate_limit


def _make_ctx(
    user_id: str,
    scopes: list[str],
    *,
    constraints: dict | None = None,
) -> MCPContext:
    now = _now()
    return MCPContext(
        user_id=user_id,
        token_id=uuid.uuid4().hex[:16],
        scopes=frozenset(scopes),
        constraints=constraints,
        token_prefix="huginn_mcp_test",
        expires_at=now + timedelta(days=90),
        client_name="pytest-read-tools",
        request_id=uuid.uuid4().hex[:16],
    )


def call_tool(tool_name: str, ctx: MCPContext, TestSession, **kwargs):
    import app.database as db_module

    mcp = _build_mcp()
    tool = mcp._tool_manager.get_tool(tool_name)
    token = mcp_context_var.set(ctx)
    try:
        with patch.object(db_module, "SessionLocal", TestSession):
            return tool.fn(**kwargs)
    finally:
        mcp_context_var.reset(token)


def _persist_mcp_token(db, user, token_id: str, scopes: list[str]) -> MCPToken:
    token = MCPToken(
        id=token_id,
        user_id=user.id,
        name=f"Token {token_id}",
        token_prefix="huginn_mcp_test",
        token_hash=(uuid.uuid4().hex + uuid.uuid4().hex)[:64],
        scopes=scopes,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


@pytest.fixture(autouse=True)
def _reset_rate_limit_env(monkeypatch):
    for name in (
        "MCP_RATE_LIMIT_ENABLED",
        "MCP_RATE_LIMIT_PATCH_PER_MINUTE",
        "MCP_RATE_LIMIT_READ_PER_MINUTE",
        "MCP_RATE_LIMIT_WRITE_PER_MINUTE",
        "MCP_RATE_LIMIT_BATCH_PER_MINUTE",
        "MCP_RATE_LIMIT_LAYOUT_PER_MINUTE",
        "MCP_RATE_LIMIT_BUCKET_TTL_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    mcp_rate_limit.clear_default_rate_limiter()
    yield
    mcp_rate_limit.clear_default_rate_limiter()


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def TestSession(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db(TestSession):
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db) -> User:
    item = User(
        id=uuid.uuid4().hex[:16],
        email="read-tools@test.com",
        name="Read Tools",
        auth_provider="google",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def studio(db, user) -> Studio:
    item = Studio(
        id=uuid.uuid4().hex[:16],
        name="Studio",
        color="azul",
        user_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def folder(db, studio) -> Folder:
    item = Folder(
        id=uuid.uuid4().hex[:16],
        name="Folder",
        studio_id=studio.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def root_board(db, studio) -> Board:
    item = Board(
        id=uuid.uuid4().hex[:16],
        name="Root Board",
        studio_id=studio.id,
        version=1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def node(db, root_board) -> Node:
    item = Node(
        id=uuid.uuid4().hex[:16],
        board_id=root_board.id,
        type="card",
        title="Sensitive Node Title",
        x=100,
        y=200,
        w=280,
        ports=[],
        tags=["secret-tag"],
        blocks=[
            {
                "type": "image",
                "id": "img-1",
                "src": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
            }
        ],
        stages=[],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _audits(db):
    return list(
        db.query(MCPAuditLog)
        .order_by(MCPAuditLog.created_at.asc(), MCPAuditLog.id.asc())
        .all()
    )


class TestReadGuardToolIntegration:
    def test_success_audits_all_real_read_tools(self, TestSession, db, user, studio, folder, root_board, node):
        scopes = ["studios:read", "folders:read", "boards:read", "nodes:read"]
        ctx = _make_ctx(user.id, scopes=scopes)
        _persist_mcp_token(db, user, ctx.token_id, scopes)

        list_studios = call_tool("list_studios", ctx, TestSession)
        list_folders = call_tool("list_folders", ctx, TestSession, studio_id=studio.id)
        list_boards = call_tool("list_boards", ctx, TestSession, studio_id=studio.id)
        summary = call_tool("get_board_summary", ctx, TestSession, board_id=root_board.id)
        board = call_tool("get_board", ctx, TestSession, board_id=root_board.id, include_images=True)
        single_node = call_tool("get_node", ctx, TestSession, node_id=node.id, include_images=True)

        assert list_studios["studios"][0]["id"] == studio.id
        assert list_folders["folders"][0]["id"] == folder.id
        assert list_boards["boards"][0]["id"] == root_board.id
        assert summary["id"] == root_board.id
        assert board["nodes"][0]["id"] == node.id
        assert single_node["node"]["id"] == node.id

        audits = _audits(db)
        assert len(audits) == 6
        assert [item.tool_name for item in audits] == [
            "list_studios",
            "list_folders",
            "list_boards",
            "get_board_summary",
            "get_board",
            "get_node",
        ]
        assert all(item.status == "success" for item in audits)
        assert [item.affected_count for item in audits] == [1, 1, 1, 1, 1, 1]
        assert audits[1].resource_type == "studio"
        assert audits[1].resource_id == studio.id
        assert audits[2].resource_type == "studio"
        assert audits[2].resource_id == studio.id
        assert audits[4].metadata_json == {
            "returned_count": 1,
            "include_images": True,
            "response_truncated": False,
        }
        assert audits[5].metadata_json == {
            "returned_count": 1,
            "include_images": True,
        }
        serialised = json.dumps([item.metadata_json for item in audits], ensure_ascii=False)
        for forbidden in (
            "Sensitive Node Title",
            "secret-tag",
            "data:image",
            "Root Board",
            "Folder",
            "Studio",
            "blocks",
            "stages",
            "tags",
            "label",
        ):
            assert forbidden not in serialised

    @pytest.mark.parametrize(
        ("tool_name", "scopes", "kwargs"),
        [
            ("list_studios", ["boards:read"], {}),
            ("list_folders", ["boards:read"], {"studio_id": "studio-id"}),
            ("list_boards", ["nodes:read"], {"studio_id": "studio-id"}),
            ("get_board_summary", ["nodes:read"], {"board_id": "board-id"}),
            ("get_board", ["nodes:read"], {"board_id": "board-id"}),
            ("get_node", ["boards:read"], {"node_id": "node-id"}),
        ],
    )
    def test_scope_errors_are_audited(self, tool_name, scopes, kwargs, TestSession, db, user):
        ctx = _make_ctx(user.id, scopes=scopes)
        _persist_mcp_token(db, user, ctx.token_id, scopes)

        with pytest.raises(Exception):
            call_tool(tool_name, ctx, TestSession, **kwargs)

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].tool_name == tool_name
        assert audits[0].status == "error"
        assert audits[0].error_code == "FORBIDDEN_RESOURCE"

    @pytest.mark.parametrize(
        ("tool_name", "kwargs", "constraints"),
        [
            ("list_folders", lambda studio, root_board, node: {"studio_id": studio.id}, {"studio_ids": []}),
            ("list_boards", lambda studio, root_board, node: {"studio_id": studio.id}, {"studio_ids": []}),
            ("get_board_summary", lambda studio, root_board, node: {"board_id": root_board.id}, {"board_ids": []}),
            ("get_board", lambda studio, root_board, node: {"board_id": root_board.id}, {"board_ids": []}),
            ("get_node", lambda studio, root_board, node: {"node_id": node.id}, {"board_ids": []}),
        ],
    )
    def test_constraint_errors_are_audited(
        self,
        tool_name,
        kwargs,
        constraints,
        TestSession,
        db,
        user,
        studio,
        root_board,
        node,
    ):
        scopes = ["studios:read", "folders:read", "boards:read", "nodes:read"]
        ctx = _make_ctx(user.id, scopes=scopes, constraints=constraints)
        _persist_mcp_token(db, user, ctx.token_id, scopes)

        with pytest.raises(Exception):
            call_tool(tool_name, ctx, TestSession, **kwargs(studio, root_board, node))

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].tool_name == tool_name
        assert audits[0].status == "error"
        assert audits[0].error_code == "FORBIDDEN_RESOURCE"

    def test_rate_limit_and_quota_isolation_between_read_tools_and_tokens(
        self,
        TestSession,
        db,
        user,
        studio,
        root_board,
        node,
        monkeypatch,
    ):
        scopes = ["studios:read", "boards:read", "nodes:read"]
        ctx_a = _make_ctx(user.id, scopes=scopes)
        ctx_b = _make_ctx(user.id, scopes=scopes)
        _persist_mcp_token(db, user, ctx_a.token_id, scopes)
        _persist_mcp_token(db, user, ctx_b.token_id, scopes)
        monkeypatch.setenv("MCP_RATE_LIMIT_READ_PER_MINUTE", "1")
        mcp_rate_limit.clear_default_rate_limiter()

        call_tool("list_studios", ctx_a, TestSession)
        with pytest.raises(ValueError, match="RATE_LIMIT_EXCEEDED"):
            call_tool("list_studios", ctx_a, TestSession)

        boards = call_tool("get_board", ctx_a, TestSession, board_id=root_board.id)
        node_result = call_tool("get_node", ctx_a, TestSession, node_id=node.id)
        studios_other_token = call_tool("list_studios", ctx_b, TestSession)

        assert boards["id"] == root_board.id
        assert node_result["node"]["id"] == node.id
        assert studios_other_token["studios"][0]["id"] == studio.id

        audits = _audits(db)
        assert [item.tool_name for item in audits] == [
            "list_studios",
            "list_studios",
            "get_board",
            "get_node",
            "list_studios",
        ]
        assert [item.status for item in audits] == [
            "success",
            "error",
            "success",
            "success",
            "success",
        ]
        assert audits[1].metadata_json == {
            "limit": 1,
            "window_seconds": 60,
            "retry_after_seconds": 60,
        }

    def test_invalid_structural_payload_does_not_audit(self, TestSession, db, user, studio):
        scopes = ["boards:read"]
        ctx = _make_ctx(user.id, scopes=scopes)
        _persist_mcp_token(db, user, ctx.token_id, scopes)

        with pytest.raises(ValueError, match="limit debe estar entre 1 y 100"):
            call_tool("list_boards", ctx, TestSession, studio_id=studio.id, limit=101)

        assert _audits(db) == []

    def test_get_board_marks_truncated_without_changing_public_shape(self, TestSession, db, user, studio, root_board):
        scopes = ["boards:read"]
        ctx = _make_ctx(user.id, scopes=scopes)
        _persist_mcp_token(db, user, ctx.token_id, scopes)

        for index in range(1001):
            db.add(
                Node(
                    id=uuid.uuid4().hex[:16],
                    board_id=root_board.id,
                    type="card",
                    title=f"Node {index}",
                    x=index,
                    y=index,
                    w=280,
                    ports=[],
                    tags=[],
                    blocks=[],
                    stages=[],
                )
            )
        db.commit()

        result = call_tool("get_board", ctx, TestSession, board_id=root_board.id)

        assert result["id"] == root_board.id
        assert len(result["nodes"]) == 1000
        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].metadata_json == {
            "returned_count": 1,
            "include_images": False,
            "response_truncated": True,
        }
