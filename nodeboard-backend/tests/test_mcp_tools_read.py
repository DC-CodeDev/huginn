"""Tests de las tools MCP de solo lectura.

Usa una base de datos en memoria con datos de prueba y llama
a las funciones de tool directamente (sin transporte HTTP).
"""
import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Board, Edge, Folder, MCPToken, Node, Studio, User
from app.mcp.auth import _now
from app.mcp.context import MCPContext, mcp_context_var
from app.mcp.server import _build_mcp


# ======================================================================
# Helpers
# ======================================================================


def _make_raw_token(user_id: str = "u1", scopes: list[str] | None = None,
                    constraints: dict | None = None) -> tuple[str, MCPContext]:
    """Crea un MCPContext de prueba."""
    import secrets
    prefix = "huginn_mcp_"
    secret = secrets.token_urlsafe(32)
    token_prefix = f"{prefix}{secret[:6]}"
    now = _now()

    if scopes is None:
        scopes = ["studios:read", "folders:read", "boards:read", "nodes:read"]

    ctx = MCPContext(
        user_id=user_id,
        token_id=uuid.uuid4().hex[:16],
        scopes=frozenset(scopes),
        constraints=constraints,
        token_prefix=token_prefix,
        expires_at=now + timedelta(days=90),
    )
    return f"{prefix}{secret}", ctx


def call_tool(name: str, ctx: MCPContext, TestSession, **kwargs):
    """Llama a una tool registrada con el contexto y argumentos dados.

    Parchea ``app.database.SessionLocal`` con *TestSession* para que
    las tools usen la BD del test.
    """
    from app.mcp.server import _build_mcp
    import app.database as db_module
    from unittest.mock import patch

    mcp = _build_mcp()
    tool = mcp._tool_manager.get_tool(name)
    if tool is None:
        raise ValueError(f"Tool not found: {name}")
    token = mcp_context_var.set(ctx)
    try:
        with patch.object(db_module, 'SessionLocal', TestSession):
            return tool.fn(**kwargs)
    finally:
        mcp_context_var.reset(token)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture()
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass

    Base.metadata.create_all(bind=e)
    return e


@pytest.fixture()
def TestSession(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db(TestSession):
    s = TestSession()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def user(db) -> User:
    u = User(id=uuid.uuid4().hex[:16], email="owner@test.com", name="Owner", auth_provider="google")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def other_user(db) -> User:
    u = User(id=uuid.uuid4().hex[:16], email="other@test.com", name="Other", auth_provider="google")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def studio(db, user) -> Studio:
    s = Studio(id=uuid.uuid4().hex[:16], name="Test Studio", color="azul", user_id=user.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture()
def other_studio(db, other_user) -> Studio:
    s = Studio(id=uuid.uuid4().hex[:16], name="Other Studio", color="verde", user_id=other_user.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture()
def folder(db, studio) -> Folder:
    f = Folder(id=uuid.uuid4().hex[:16], name="Test Folder", studio_id=studio.id)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


@pytest.fixture()
def board(db, studio, folder) -> Board:
    b = Board(id=uuid.uuid4().hex[:16], name="Test Board", studio_id=studio.id, folder_id=folder.id)
    db.add(b)
    db.commit()
    return b


@pytest.fixture()
def node(db, board) -> Node:
    n = Node(
        id=uuid.uuid4().hex[:16],
        board_id=board.id,
        type="card",
        x=100, y=200, w=280,
        title="Test Node",
        ports=[{"id": "p1", "side": "left", "color": "#4ADE80", "label": "out"}],
        blocks=[{"type": "text", "id": "b1", "value": "hello"}],
        tags=["tag1"],
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


@pytest.fixture()
def other_board(db, other_user, other_studio) -> Board:
    b = Board(id=uuid.uuid4().hex[:16], name="Other Board", studio_id=other_studio.id)
    db.add(b)
    db.commit()
    return b


# ======================================================================
# Tests: list_studios
# ======================================================================


class TestListStudios:
    def test_lists_own_studios(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_studios", ctx, TestSession)
        assert len(result["studios"]) == 1
        assert result["studios"][0]["name"] == "Test Studio"

    def test_does_not_include_other_users(self, TestSession, db, user, other_user, studio, other_studio):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_studios", ctx, TestSession)
        assert len(result["studios"]) == 1
        assert result["studios"][0]["id"] == studio.id

    def test_scope_missing(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id, scopes=["boards:read"])
        from app.mcp.errors import InsufficientScope
        with pytest.raises(InsufficientScope):
            call_tool("list_studios", ctx, TestSession)

    def test_empty_list(self, TestSession, db, user):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_studios", ctx, TestSession)
        assert result["studios"] == []

    def test_studio_ids_constraint(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id, constraints={"studio_ids": [studio.id]})
        result = call_tool("list_studios", ctx, TestSession)
        assert len(result["studios"]) == 1

    def test_studio_ids_empty(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id, constraints={"studio_ids": []})
        result = call_tool("list_studios", ctx, TestSession)
        assert result["studios"] == []

    def test_board_ids_constraint(self, TestSession, db, user, studio, board):
        _, ctx = _make_raw_token(user_id=user.id, constraints={"board_ids": [board.id]})
        result = call_tool("list_studios", ctx, TestSession)
        assert len(result["studios"]) == 1
        assert result["studios"][0]["id"] == studio.id

    def test_stable_order(self, TestSession, db, user, studio):
        s2 = Studio(id=uuid.uuid4().hex[:16], name="Alpha Studio", color="verde", user_id=user.id)
        db.add(s2)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_studios", ctx, TestSession)
        names = [s["name"] for s in result["studios"]]
        assert names == sorted(names)


# ======================================================================
# Tests: list_folders
# ======================================================================


class TestListFolders:
    def test_lists_folders(self, TestSession, db, user, studio, folder):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_folders", ctx, TestSession, studio_id=studio.id)
        assert len(result["folders"]) == 1
        assert result["folders"][0]["name"] == "Test Folder"

    def test_wrong_studio(self, TestSession, db, user, other_studio):
        _, ctx = _make_raw_token(user_id=user.id)
        with pytest.raises(ValueError, match="no encontrado"):
            call_tool("list_folders", ctx, TestSession, studio_id=other_studio.id)

    def test_scope_missing(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id, scopes=["boards:read"])
        from app.mcp.errors import InsufficientScope
        with pytest.raises(InsufficientScope):
            call_tool("list_folders", ctx, TestSession, studio_id=studio.id)

    def test_studio_constraint(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id, constraints={"studio_ids": ["nonexistent"]})
        from app.mcp.errors import ConstraintViolation
        with pytest.raises(ConstraintViolation):
            call_tool("list_folders", ctx, TestSession, studio_id=studio.id)


# ======================================================================
# Tests: list_boards
# ======================================================================


class TestListBoards:
    def test_lists_boards(self, TestSession, db, user, studio, board):
        # Board sin folder para el test
        root_board = Board(id=uuid.uuid4().hex[:16], name="Root Board", studio_id=studio.id)
        db.add(root_board)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_boards", ctx, TestSession, studio_id=studio.id)
        assert len(result["boards"]) == 1
        assert result["boards"][0]["name"] == "Root Board"
        assert result["returned"] == 1

    def test_filters_by_folder(self, TestSession, db, user, studio, folder, board):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_boards", ctx, TestSession, studio_id=studio.id, folder_id=folder.id)
        assert len(result["boards"]) == 1

    def test_wrong_studio(self, TestSession, db, user, other_studio):
        _, ctx = _make_raw_token(user_id=user.id)
        with pytest.raises(ValueError, match="no encontrado"):
            call_tool("list_boards", ctx, TestSession, studio_id=other_studio.id)

    def test_pagination(self, TestSession, db, user, studio):
        for i in range(5):
            b = Board(id=uuid.uuid4().hex[:16], name=f"Board {i}", studio_id=studio.id)
            db.add(b)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("list_boards", ctx, TestSession, studio_id=studio.id, limit=2, offset=0)
        assert len(result["boards"]) == 2
        assert result["limit"] == 2
        assert result["offset"] == 0

    def test_invalid_limit(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id)
        with pytest.raises(ValueError):
            call_tool("list_boards", ctx, TestSession, studio_id=studio.id, limit=0)
        with pytest.raises(ValueError):
            call_tool("list_boards", ctx, TestSession, studio_id=studio.id, limit=101)

    def test_board_ids_constraint(self, TestSession, db, user, studio, board):
        # board tiene folder; crear uno root para el test
        root1 = Board(id=uuid.uuid4().hex[:16], name="Root1", studio_id=studio.id)
        root2 = Board(id=uuid.uuid4().hex[:16], name="Root2", studio_id=studio.id)
        db.add(root1)
        db.add(root2)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id, constraints={"board_ids": [root1.id]})
        result = call_tool("list_boards", ctx, TestSession, studio_id=studio.id)
        assert len(result["boards"]) == 1
        assert result["boards"][0]["id"] == root1.id

    def test_scope_missing(self, TestSession, db, user, studio):
        _, ctx = _make_raw_token(user_id=user.id, scopes=["nodes:read"])
        from app.mcp.errors import InsufficientScope
        with pytest.raises(InsufficientScope):
            call_tool("list_boards", ctx, TestSession, studio_id=studio.id)


# ======================================================================
# Tests: get_board_summary
# ======================================================================


class TestGetBoardSummary:
    def test_returns_summary(self, TestSession, db, user, studio, board, node):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("get_board_summary", ctx, TestSession, board_id=board.id)
        assert result["id"] == board.id
        assert result["name"] == "Test Board"
        assert result["version"] == 1
        assert result["node_count"] == 1
        assert result["edge_count"] == 0
        assert result["studio_id"] == studio.id

    def test_other_users_board(self, TestSession, db, user, other_board):
        _, ctx = _make_raw_token(user_id=user.id)
        with pytest.raises(ValueError, match="no encontrado"):
            call_tool("get_board_summary", ctx, TestSession, board_id=other_board.id)

    def test_board_constraint(self, TestSession, db, user, studio, board):
        _, ctx = _make_raw_token(user_id=user.id, constraints={"board_ids": []})
        from app.mcp.errors import ConstraintViolation
        with pytest.raises(ConstraintViolation):
            call_tool("get_board_summary", ctx, TestSession, board_id=board.id)

    def test_does_not_return_nodes(self, TestSession, db, user, board, node):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("get_board_summary", ctx, TestSession, board_id=board.id)
        assert "nodes" not in result
        assert "edges" not in result


# ======================================================================
# Tests: get_board
# ======================================================================


class TestGetBoard:
    def test_returns_full_state(self, TestSession, db, user, board, node):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("get_board", ctx, TestSession, board_id=board.id)
        assert result["id"] == board.id
        assert result["version"] == 1
        assert len(result["nodes"]) == 1
        assert len(result["edges"]) == 0

    def test_images_omitted_by_default(self, TestSession, db, user, board):
        n = Node(
            id=uuid.uuid4().hex[:16], board_id=board.id, type="card",
            blocks=[{"type": "image", "id": "img1", "src": "data:image/png;base64,iVBORw0KGgo="}],
        )
        db.add(n)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("get_board", ctx, TestSession, board_id=board.id)
        blocks = result["nodes"][0]["blocks"]
        assert blocks[0]["image_omitted"] is True
        assert blocks[0]["mime_type"] == "image/png"
        assert "src" not in blocks[0]

    def test_images_included_when_requested(self, TestSession, db, user, board):
        n = Node(
            id=uuid.uuid4().hex[:16], board_id=board.id, type="card",
            blocks=[{"type": "image", "id": "img1", "src": "data:image/png;base64,iVBORw0KGgo="}],
        )
        db.add(n)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("get_board", ctx, TestSession, board_id=board.id, include_images=True)
        blocks = result["nodes"][0]["blocks"]
        assert blocks[0]["type"] == "image"
        assert blocks[0]["src"] == "data:image/png;base64,iVBORw0KGgo="

    def test_other_users_board(self, TestSession, db, user, other_board):
        _, ctx = _make_raw_token(user_id=user.id)
        with pytest.raises(ValueError, match="no encontrado"):
            call_tool("get_board", ctx, TestSession, board_id=other_board.id)

    def test_does_not_mutate_db(self, TestSession, db, user, board):
        _, ctx = _make_raw_token(user_id=user.id)
        v_before = board.version
        call_tool("get_board", ctx, TestSession, board_id=board.id)
        db.refresh(board)
        assert board.version == v_before


# ======================================================================
# Tests: get_node
# ======================================================================


class TestGetNode:
    def test_returns_node(self, TestSession, db, user, board, node):
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("get_node", ctx, TestSession, node_id=node.id)
        assert result["node"]["id"] == node.id
        assert result["node"]["type"] == "card"
        assert result["node"]["title"] == "Test Node"
        assert result["node"]["board_id"] == board.id

    def test_scope_boards_read_not_enough(self, TestSession, db, user, board, node):
        _, ctx = _make_raw_token(user_id=user.id, scopes=["boards:read"])
        from app.mcp.errors import InsufficientScope
        with pytest.raises(InsufficientScope):
            call_tool("get_node", ctx, TestSession, node_id=node.id)

    def test_scope_nodes_read_enough(self, TestSession, db, user, board, node):
        _, ctx = _make_raw_token(user_id=user.id, scopes=["nodes:read"])
        result = call_tool("get_node", ctx, TestSession, node_id=node.id)
        assert result["node"]["id"] == node.id

    def test_other_users_node(self, TestSession, db, user, other_board):
        n = Node(id=uuid.uuid4().hex[:16], board_id=other_board.id, type="card", title="Other Node")
        db.add(n)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id)
        with pytest.raises(ValueError, match="no encontrado"):
            call_tool("get_node", ctx, TestSession, node_id=n.id)

    def test_images_omitted(self, TestSession, db, user, board):
        n = Node(
            id=uuid.uuid4().hex[:16], board_id=board.id, type="card",
            blocks=[{"type": "image", "id": "img1", "src": "data:image/jpeg;base64,/9j/4AAQ"}],
        )
        db.add(n)
        db.commit()
        _, ctx = _make_raw_token(user_id=user.id)
        result = call_tool("get_node", ctx, TestSession, node_id=n.id)
        blocks = result["node"]["blocks"]
        assert blocks[0]["image_omitted"] is True
        assert blocks[0]["mime_type"] == "image/jpeg"


# ======================================================================
# Tests de solo lectura
# ======================================================================


class TestReadOnly:
    def test_no_state_changes(self, TestSession, db, user, studio, folder, board, node):
        """Ejecuta todas las tools y verifica que nada cambia."""
        _, ctx = _make_raw_token(user_id=user.id)
        db.refresh(board)
        v_before = board.version
        t_before = board.updated_at

        call_tool("list_studios", ctx, TestSession)
        call_tool("list_folders", ctx, TestSession, studio_id=studio.id)
        call_tool("list_boards", ctx, TestSession, studio_id=studio.id)
        call_tool("get_board_summary", ctx, TestSession, board_id=board.id)
        call_tool("get_board", ctx, TestSession, board_id=board.id)
        call_tool("get_node", ctx, TestSession, node_id=node.id)

        db.refresh(board)
        assert board.version == v_before
        assert board.updated_at == t_before
