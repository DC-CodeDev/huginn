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
from app.models import Board, Edge, MCPAuditLog, MCPToken, Node, Studio, User
from app.mcp.auth import _now
from app.mcp.context import MCPContext, mcp_context_var
from app.mcp.server import _build_mcp
from app.services import mcp_rate_limit


def _make_ctx(
    user_id: str,
    scopes: list[str],
) -> MCPContext:
    now = _now()
    return MCPContext(
        user_id=user_id,
        token_id=uuid.uuid4().hex[:16],
        scopes=frozenset(scopes),
        constraints=None,
        token_prefix="huginn_mcp_test",
        expires_at=now + timedelta(days=90),
        client_name="pytest-client",
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


def _persist_node(db, board, *, node_id: str, title: str = "Node", ports=None) -> Node:
    item = Node(
        id=node_id,
        board_id=board.id,
        title=title,
        x=100,
        y=200,
        w=280,
        ports=ports or [],
        blocks=[],
        stages=[],
        tags=[],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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
        email="guard-tools@test.com",
        name="Guard Tools",
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
def board(db, studio) -> Board:
    item = Board(
        id=uuid.uuid4().hex[:16],
        name="Board",
        studio_id=studio.id,
        version=1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def board_with_two_nodes(db, board) -> Board:
    _persist_node(
        db,
        board,
        node_id="edge-n1",
        title="Source",
        ports=[{"id": "out", "side": "right", "color": "#60A5FA", "label": ""}],
    )
    _persist_node(
        db,
        board,
        node_id="edge-n2",
        title="Target",
        ports=[{"id": "in", "side": "left", "color": "#4ADE80", "label": ""}],
    )
    db.refresh(board)
    return board


def _audits(db):
    return list(
        db.query(MCPAuditLog)
        .order_by(MCPAuditLog.created_at.asc(), MCPAuditLog.id.asc())
        .all()
    )


class TestMutationGuardToolIntegration:
    def test_success_audits_all_nine_mutating_tools(self, TestSession, db, user, studio, board_with_two_nodes):
        scopes = [
            "boards:create",
            "boards:update",
            "nodes:create",
            "nodes:update",
            "edges:create",
            "edges:update",
        ]
        ctx = _make_ctx(user.id, scopes=scopes)
        _persist_mcp_token(db, user, ctx.token_id, scopes)

        created_board = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="Created by tool",
        )
        created_board_id = created_board["data"]["board"]["id"]

        renamed = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=created_board_id,
            name="Renamed",
            expected_version=1,
        )
        create_node = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board_with_two_nodes.id,
            expected_version=1,
            node={"type": "card", "title": "Card", "x": 10, "y": 20},
        )
        node_id = create_node["data"]["node"]["id"]
        call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node_id,
            expected_version=2,
            changes={"title": "Updated", "tags": ["a"]},
        )
        call_tool(
            "move_node",
            ctx,
            TestSession,
            node_id=node_id,
            x=300,
            y=400,
            expected_version=3,
        )
        call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=created_board_id,
            expected_version=2,
            nodes=[
                {"client_id": "n1", "node": {"type": "card", "title": "A", "x": 0, "y": 0}},
                {"client_id": "n2", "node": {"type": "card", "title": "B", "x": 5, "y": 5}},
            ],
        )
        create_edge = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board_with_two_nodes.id,
            expected_version=4,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = create_edge["data"]["edge"]["id"]
        call_tool(
            "update_edge",
            ctx,
            TestSession,
            edge_id=edge_id,
            expected_version=5,
            changes={"label": "ok", "curved": False},
        )
        call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board_with_two_nodes.id,
            expected_version=6,
            edges=[
                {
                    "client_id": "e1",
                    "edge": {
                        "from": {"nodeId": "edge-n1", "portId": "out"},
                        "to": {"nodeId": node_id, "portId": ""},
                    },
                }
            ],
        )

        audits = _audits(db)
        assert len(audits) == 9
        assert [item.tool_name for item in audits] == [
            "create_board",
            "rename_board",
            "create_node",
            "update_node",
            "move_node",
            "create_nodes_batch",
            "create_edge",
            "update_edge",
            "create_edges_batch",
        ]
        assert all(item.status == "success" for item in audits)
        assert all(item.request_id == ctx.request_id for item in audits)
        assert all(item.client_name == "pytest-client" for item in audits)
        serialised = json.dumps([item.metadata_json for item in audits], ensure_ascii=False)
        for forbidden in ("title", "blocks", "stages", "tags", "label", "x", "y", "ports"):
            assert forbidden not in serialised
        assert renamed["data"]["board_version"] == 2
        assert create_node["data"]["board_version"] == 2
        assert create_edge["data"]["board_version"] == 5

    @pytest.mark.parametrize(
        ("tool_name", "invoke"),
        [
            ("create_board", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("create_board", ctx, TestSession, studio_id=studio.id, name="Nope")),
            ("rename_board", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("rename_board", ctx, TestSession, board_id=board.id, name="Nope", expected_version=1)),
            ("create_node", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("create_node", ctx, TestSession, board_id=board.id, expected_version=1, node={"type": "card", "title": "Nope"})),
            ("update_node", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("update_node", ctx, TestSession, node_id=_create_existing_node(TestSession, board), expected_version=1, changes={"title": "Nope"})),
            ("move_node", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("move_node", ctx, TestSession, node_id=_create_existing_node(TestSession, board), x=1, y=2, expected_version=1)),
            ("create_nodes_batch", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("create_nodes_batch", ctx, TestSession, board_id=board.id, expected_version=1, nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Nope"}}])),
            ("create_edge", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("create_edge", ctx, TestSession, board_id=board_with_two_nodes.id, expected_version=1, edge={"from": {"nodeId": "edge-n1", "portId": "out"}, "to": {"nodeId": "edge-n2", "portId": "in"}})),
            ("update_edge", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("update_edge", ctx, TestSession, edge_id=_create_existing_edge(TestSession, board_with_two_nodes), expected_version=1, changes={"label": "x"})),
            ("create_edges_batch", lambda ctx, TestSession, studio, board, board_with_two_nodes: call_tool("create_edges_batch", ctx, TestSession, board_id=board_with_two_nodes.id, expected_version=1, edges=[{"client_id": "e1", "edge": {"from": {"nodeId": "edge-n1", "portId": "out"}, "to": {"nodeId": "edge-n2", "portId": "in"}}}])),
        ],
    )
    def test_scope_errors_are_audited(self, tool_name, invoke, TestSession, db, user, studio, board, board_with_two_nodes):
        ctx = _make_ctx(user.id, scopes=["boards:read"])
        _persist_mcp_token(db, user, ctx.token_id, ["boards:read"])

        with pytest.raises(Exception):
            invoke(ctx, TestSession, studio, board, board_with_two_nodes)

        audits = _audits(db)
        assert len(audits) == 1
        assert audits[0].tool_name == tool_name
        assert audits[0].status == "error"
        assert audits[0].error_code == "FORBIDDEN_RESOURCE"

    def test_rate_limit_and_quota_isolation_between_tools_and_categories(self, TestSession, db, user, board_with_two_nodes, monkeypatch):
        scopes = ["nodes:create", "nodes:update", "edges:create", "edges:update"]
        ctx = _make_ctx(user.id, scopes=scopes)
        _persist_mcp_token(db, user, ctx.token_id, scopes)
        monkeypatch.setenv("MCP_RATE_LIMIT_WRITE_PER_MINUTE", "1")
        monkeypatch.setenv("MCP_RATE_LIMIT_BATCH_PER_MINUTE", "1")
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "1")
        mcp_rate_limit.clear_default_rate_limiter()

        call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board_with_two_nodes.id,
            expected_version=1,
            node={"type": "card", "title": "Uno"},
        )
        with pytest.raises(ValueError, match="RATE_LIMIT_EXCEEDED"):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board_with_two_nodes.id,
                expected_version=2,
                node={"type": "card", "title": "Dos"},
            )
        call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id="edge-n1",
            expected_version=2,
            changes={"title": "allowed"},
        )
        call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board_with_two_nodes.id,
            expected_version=3,
            nodes=[{"client_id": "n1", "node": {"type": "card", "title": "batch"}}],
        )
        with pytest.raises(ValueError, match="RATE_LIMIT_EXCEEDED"):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board_with_two_nodes.id,
                expected_version=4,
                nodes=[{"client_id": "n2", "node": {"type": "card", "title": "batch2"}}],
            )
        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board_with_two_nodes.id,
            expected_version=4,
            dry_run=True,
            operations=[{"op": "move_node", "node_id": "edge-n1", "x": 5, "y": 6}],
        )

        audits = _audits(db)
        error_codes = [item.error_code for item in audits if item.status == "error"]
        assert error_codes.count("RATE_LIMIT_EXCEEDED") == 2
        assert any(item.tool_name == "update_node" and item.status == "success" for item in audits)
        assert any(item.tool_name == "apply_board_patch" and item.status == "success" for item in audits)


def _create_existing_node(TestSession, board) -> str:
    db = TestSession()
    try:
        node_id = uuid.uuid4().hex[:16]
        _persist_node(
            db,
            db.get(Board, board.id),
            node_id=node_id,
        )
        return node_id
    finally:
        db.close()


def _create_existing_edge(TestSession, board_with_two_nodes) -> str:
    db = TestSession()
    try:
        edge = Edge(
            id=uuid.uuid4().hex[:16],
            board_id=board_with_two_nodes.id,
            from_node="edge-n1",
            from_port="out",
            to_node="edge-n2",
            to_port="in",
            curved=True,
            label="",
        )
        db.add(edge)
        db.commit()
        return edge.id
    finally:
        db.close()
