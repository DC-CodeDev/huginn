"""Tests de la primera tool MCP de escritura: create_board."""

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
from app.models import Board, Edge, Folder, MCPAuditLog, MCPIdempotencyRecord, MCPToken, Node, Studio, User
from app.mcp.auth import _now
from app.mcp.context import MCPContext, mcp_context_var
from app.mcp.errors import ConstraintViolation, InsufficientScope
from app.mcp.server import _build_mcp
from app.services import mcp_rate_limit


def _make_ctx(
    user_id: str,
    scopes: list[str] | None = None,
    constraints: dict | None = None,
) -> MCPContext:
    now = _now()
    return MCPContext(
        user_id=user_id,
        token_id=uuid.uuid4().hex[:16],
        scopes=frozenset(scopes or ["boards:create"]),
        constraints=constraints,
        token_prefix="huginn_mcp_test",
        expires_at=now + timedelta(days=90),
    )


def call_tool(tool_name: str, ctx: MCPContext, TestSession, **kwargs):
    import app.database as db_module

    mcp = _build_mcp()
    tool = mcp._tool_manager.get_tool(tool_name)
    if tool is None:
        raise ValueError(f"Tool not found: {tool_name}")
    token = mcp_context_var.set(ctx)
    try:
        with patch.object(db_module, "SessionLocal", TestSession):
            return tool.fn(**kwargs)
    finally:
        mcp_context_var.reset(token)


def call_tool_without_context(tool_name: str, TestSession, **kwargs):
    import app.database as db_module

    mcp = _build_mcp()
    tool = mcp._tool_manager.get_tool(tool_name)
    if tool is None:
        raise ValueError(f"Tool not found: {tool_name}")
    with patch.object(db_module, "SessionLocal", TestSession):
        return tool.fn(**kwargs)


def _card_node_payload(**overrides):
    payload = {
        "type": "card",
        "title": "Card MCP",
        "x": 100,
        "y": 200,
        "w": 280,
        "ports": [],
        "tags": [],
        "blocks": [],
    }
    payload.update(overrides)
    return payload


def _timeline_node_payload(**overrides):
    payload = {
        "type": "timeline",
        "title": "Timeline MCP",
        "x": 100,
        "y": 200,
        "w": 360,
        "ports": [],
        "tags": [],
        "stages": [],
    }
    payload.update(overrides)
    return payload


def _persist_node(db, board, **overrides) -> Node:
    payload = {
        "id": uuid.uuid4().hex[:16],
        "board_id": board.id,
        "type": "card",
        "title": "",
        "x": 100,
        "y": 200,
        "w": 280,
        "ports": [],
        "blocks": [],
        "stages": [],
        "tags": [],
        "orientation": None,
    }
    payload.update(overrides)
    node = Node(**payload)
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


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


class _FakeMonotonicClock:
    def __init__(self, start: float = 0.0):
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass

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
def user(db) -> User:
    user = User(
        id=uuid.uuid4().hex[:16],
        email="owner@test.com",
        name="Owner",
        auth_provider="google",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def other_user(db) -> User:
    user = User(
        id=uuid.uuid4().hex[:16],
        email="other@test.com",
        name="Other",
        auth_provider="google",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def studio(db, user) -> Studio:
    studio = Studio(
        id=uuid.uuid4().hex[:16],
        name="Studio",
        color="azul",
        user_id=user.id,
    )
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


@pytest.fixture()
def other_studio(db, other_user) -> Studio:
    studio = Studio(
        id=uuid.uuid4().hex[:16],
        name="Other Studio",
        color="verde",
        user_id=other_user.id,
    )
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


@pytest.fixture()
def folder(db, studio) -> Folder:
    folder = Folder(
        id=uuid.uuid4().hex[:16],
        name="Folder",
        studio_id=studio.id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@pytest.fixture()
def other_folder(db, other_studio) -> Folder:
    folder = Folder(
        id=uuid.uuid4().hex[:16],
        name="Other Folder",
        studio_id=other_studio.id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@pytest.fixture()
def second_studio(db, user) -> Studio:
    studio = Studio(
        id=uuid.uuid4().hex[:16],
        name="Second Studio",
        color="verde",
        user_id=user.id,
    )
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


@pytest.fixture()
def second_folder(db, second_studio) -> Folder:
    folder = Folder(
        id=uuid.uuid4().hex[:16],
        name="Second Folder",
        studio_id=second_studio.id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@pytest.fixture()
def board(db, studio) -> Board:
    board = Board(
        id=uuid.uuid4().hex[:16],
        name="Board original",
        studio_id=studio.id,
        version=1,
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


@pytest.fixture()
def board_with_folder(db, studio, folder) -> Board:
    board = Board(
        id=uuid.uuid4().hex[:16],
        name="Board en carpeta",
        studio_id=studio.id,
        folder_id=folder.id,
        version=1,
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


@pytest.fixture()
def other_board(db, other_studio) -> Board:
    board = Board(
        id=uuid.uuid4().hex[:16],
        name="Board ajeno",
        studio_id=other_studio.id,
        version=1,
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


@pytest.fixture()
def board_with_graph(db, studio) -> Board:
    board = Board(
        id=uuid.uuid4().hex[:16],
        name="Board con grafo",
        studio_id=studio.id,
        version=1,
    )
    node_a = Node(
        id="node-a",
        board_id=board.id,
        title="A",
        ports=[{"id": "p1", "side": "right", "color": "#60A5FA", "label": ""}],
    )
    node_b = Node(
        id="node-b",
        board_id=board.id,
        title="B",
        ports=[{"id": "p2", "side": "left", "color": "#4ADE80", "label": ""}],
    )
    edge = Edge(
        id="edge-a",
        board_id=board.id,
        from_node=node_a.id,
        from_port="p1",
        to_node=node_b.id,
        to_port="p2",
        label="rel",
    )
    db.add_all([board, node_a, node_b, edge])
    db.commit()
    db.refresh(board)
    return board


class TestCreateBoardToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("create_board") == 1

    def test_create_board_in_own_studio(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id, scopes=["boards:create"])
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="Nuevo Board",
        )
        board = result["data"]["board"]
        assert result["ok"] is True
        assert board["name"] == "Nuevo Board"
        assert board["studio_id"] == studio.id
        assert board["folder_id"] is None
        assert board["version"] == 1

    def test_create_board_without_folder(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id)
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="Sin carpeta",
        )
        created = db.get(Board, result["data"]["board"]["id"])
        assert created is not None
        assert created.folder_id is None

    def test_create_board_with_valid_folder(self, TestSession, db, user, studio, folder):
        ctx = _make_ctx(user.id)
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="En carpeta",
            folder_id=folder.id,
        )
        created = db.get(Board, result["data"]["board"]["id"])
        assert created is not None
        assert created.folder_id == folder.id

    def test_response_uses_uniform_shape(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id)
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="Forma uniforme",
        )
        assert set(result.keys()) == {"ok", "data"}
        assert "board" in result["data"]
        assert result["data"]["board"]["created_at"] is not None
        assert result["data"]["board"]["updated_at"] is not None


class TestCreateBoardToolScopes:
    def test_boards_create_scope_allows(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id, scopes=["boards:create"])
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="Permitido",
        )
        assert result["ok"] is True

    def test_missing_boards_create_scope_rejected(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id, scopes=["boards:read"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="No permitido",
            )

    def test_context_not_authenticated_rejected(self, TestSession, db, studio):
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            call_tool_without_context(
                "create_board",
                TestSession,
                studio_id=studio.id,
                name="Sin auth",
            )


class TestCreateBoardToolConstraints:
    def test_allowed_studio_works(self, TestSession, db, user, studio):
        ctx = _make_ctx(
            user.id,
            constraints={"studio_ids": [studio.id]},
        )
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="Permitido",
        )
        assert result["ok"] is True

    def test_studio_outside_constraints_fails(self, TestSession, db, user, studio):
        ctx = _make_ctx(
            user.id,
            constraints={"studio_ids": ["other-studio"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="Bloqueado",
            )

    def test_board_ids_constraint_blocks_creation(self, TestSession, db, user, studio):
        ctx = _make_ctx(
            user.id,
            constraints={"board_ids": ["board-a"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="Bloqueado",
            )

    def test_folder_outside_studio_fails(self, TestSession, db, user, studio, second_folder):
        ctx = _make_ctx(user.id)
        with pytest.raises(ValueError, match="carpeta no pertenece"):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="Invalido",
                folder_id=second_folder.id,
            )

    def test_folder_other_user_fails(self, TestSession, db, user, studio, other_folder):
        ctx = _make_ctx(user.id)
        with pytest.raises(ValueError, match="Carpeta no encontrada"):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="Ajeno",
                folder_id=other_folder.id,
            )

    def test_folder_allowed_under_allowed_studio(self, TestSession, db, user, studio, folder):
        ctx = _make_ctx(
            user.id,
            constraints={"studio_ids": [studio.id]},
        )
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="Ok",
            folder_id=folder.id,
        )
        assert result["data"]["board"]["folder_id"] == folder.id


class TestCreateBoardToolValidation:
    def test_empty_name_rejected(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id)
        count_before = db.query(Board).count()
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="",
        )
        assert result["ok"] is True
        count_after = db.query(Board).count()
        assert count_after == count_before + 1

    def test_name_too_long_follows_rest_contract(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id)
        result = call_tool(
            "create_board",
            ctx,
            TestSession,
            studio_id=studio.id,
            name="x" * 500,
        )
        assert result["ok"] is True

    def test_nonexistent_studio(self, TestSession, db, user):
        ctx = _make_ctx(user.id)
        with pytest.raises(ValueError, match="Studio no encontrado"):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id="missing",
                name="Nope",
            )

    def test_nonexistent_folder(self, TestSession, db, user, studio):
        ctx = _make_ctx(user.id)
        with pytest.raises(ValueError, match="Carpeta no encontrada"):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="Nope",
                folder_id="missing-folder",
            )

    def test_missing_required_studio_id_is_invalid_payload(self, TestSession, db, user):
        ctx = _make_ctx(user.id)
        with pytest.raises(TypeError):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                name="Sin studio",
            )


class TestCreateBoardToolIntegrity:
    def test_error_does_not_create_partial_board(self, TestSession, db, user, studio):
        ctx = _make_ctx(
            user.id,
            constraints={"board_ids": ["existing-board"]},
        )
        count_before = db.query(Board).count()
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="No crear",
            )
        count_after = db.query(Board).count()
        assert count_after == count_before

    def test_error_does_not_modify_other_resources(self, TestSession, db, user, studio):
        existing = Board(
            id=uuid.uuid4().hex[:16],
            name="Existente",
            studio_id=studio.id,
            version=4,
        )
        db.add(existing)
        db.commit()
        ctx = _make_ctx(
            user.id,
            constraints={"board_ids": ["existing-board"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=studio.id,
                name="No tocar",
            )
        db.refresh(existing)
        assert existing.name == "Existente"
        assert existing.version == 4

    def test_user_cannot_create_in_other_users_studio(self, TestSession, db, user, other_studio):
        ctx = _make_ctx(user.id)
        with pytest.raises(ValueError, match="Studio no encontrado"):
            call_tool(
                "create_board",
                ctx,
                TestSession,
                studio_id=other_studio.id,
                name="Intruso",
            )


class TestRenameBoardToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("rename_board") == 1

    def test_rename_board_own_board(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Nuevo nombre",
            expected_version=1,
        )
        db.refresh(board)
        assert result["ok"] is True
        assert result["data"]["board"]["name"] == "Nuevo nombre"
        assert result["data"]["board"]["version"] == 2
        assert board.name == "Nuevo nombre"
        assert board.version == 2

    def test_response_includes_versions(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Versionado",
            expected_version=1,
        )
        assert result["data"]["previous_version"] == 1
        assert result["data"]["board_version"] == 2

    def test_updated_at_changes(self, TestSession, db, user, board):
        import time

        before = board.updated_at
        time.sleep(0.02)
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Con timestamp",
            expected_version=1,
        )
        db.refresh(board)
        assert board.updated_at > before

    def test_folder_and_studio_preserved(self, TestSession, db, user, board_with_folder):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board_with_folder.id,
            name="Solo nombre",
            expected_version=1,
        )
        db.refresh(board_with_folder)
        payload = result["data"]["board"]
        assert payload["studio_id"] == board_with_folder.studio_id
        assert payload["folder_id"] == board_with_folder.folder_id
        assert board_with_folder.folder_id is not None

    def test_empty_name_follows_rest_contract(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="",
            expected_version=1,
        )
        assert result["ok"] is True
        db.refresh(board)
        assert board.name == ""

    def test_long_name_follows_rest_contract(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        long_name = "x" * 500
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name=long_name,
            expected_version=1,
        )
        assert result["ok"] is True
        db.refresh(board)
        assert board.name == long_name


class TestRenameBoardToolScopes:
    def test_boards_update_scope_allows(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Permitido",
            expected_version=1,
        )
        assert result["ok"] is True

    def test_boards_create_scope_not_enough(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:create"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="No permitido",
                expected_version=1,
            )

    def test_boards_read_scope_not_enough(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:read"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="No permitido",
                expected_version=1,
            )

    def test_context_not_authenticated_rejected(self, TestSession, board):
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            call_tool_without_context(
                "rename_board",
                TestSession,
                board_id=board.id,
                name="Sin auth",
                expected_version=1,
            )


class TestRenameBoardToolConstraints:
    def test_board_allowed_by_board_ids(self, TestSession, user, board):
        ctx = _make_ctx(
            user.id,
            scopes=["boards:update"],
            constraints={"board_ids": [board.id]},
        )
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Permitido",
            expected_version=1,
        )
        assert result["ok"] is True

    def test_board_outside_board_ids_fails(self, TestSession, user, board):
        ctx = _make_ctx(
            user.id,
            scopes=["boards:update"],
            constraints={"board_ids": ["otro-board"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="Bloqueado",
                expected_version=1,
            )

    def test_board_inside_studio_ids_works(self, TestSession, user, board):
        ctx = _make_ctx(
            user.id,
            scopes=["boards:update"],
            constraints={"studio_ids": [board.studio_id]},
        )
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Permitido",
            expected_version=1,
        )
        assert result["ok"] is True

    def test_board_outside_studio_ids_fails(self, TestSession, user, board):
        ctx = _make_ctx(
            user.id,
            scopes=["boards:update"],
            constraints={"studio_ids": ["otro-studio"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="Bloqueado",
                expected_version=1,
            )

    def test_other_user_board_fails_as_not_found(self, TestSession, user, other_board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(ValueError, match="Tablero no encontrado"):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=other_board.id,
                name="Intruso",
                expected_version=1,
            )

    def test_without_constraints_works_on_owned_board(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"], constraints=None)
        result = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Libre",
            expected_version=1,
        )
        assert result["ok"] is True


class TestRenameBoardToolVersioning:
    def test_expected_version_correct(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Ok",
            expected_version=1,
        )
        db.refresh(board)
        assert board.version == 2

    def test_expected_version_old_fails_without_changes(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="Nope",
                expected_version=0,
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert payload["expected_version"] == 0
        assert payload["current_version"] == 1
        db.refresh(board)
        assert board.name == "Board original"
        assert board.version == 1

    def test_expected_version_future_fails_without_changes(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="Nope",
                expected_version=9,
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert payload["expected_version"] == 9
        assert payload["current_version"] == 1
        db.refresh(board)
        assert board.name == "Board original"
        assert board.version == 1

    def test_two_renames_with_same_version_only_one_succeeds(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        first = call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board.id,
            name="Primero",
            expected_version=1,
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="Segundo",
                expected_version=1,
            )
        payload = json.loads(str(exc.value))
        assert first["data"]["board_version"] == 2
        assert payload["code"] == "VERSION_CONFLICT"
        db.refresh(board)
        assert board.name == "Primero"
        assert board.version == 2


class TestRenameBoardToolValidation:
    def test_missing_expected_version_invalid_payload(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(TypeError):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="Sin version",
            )

    def test_missing_name_invalid_payload(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(TypeError):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
            )

    def test_missing_board_id_invalid_payload(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(TypeError):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                name="Sin board",
                expected_version=1,
            )

    def test_extra_fields_invalid_payload(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(TypeError):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="Extra",
                expected_version=1,
                studio_id="unexpected",
            )

    def test_nonexistent_board(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(ValueError, match="Tablero no encontrado"):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id="missing-board",
                name="Nope",
                expected_version=1,
            )


class TestRenameBoardToolIntegrity:
    def test_rename_does_not_move_board(self, TestSession, db, user, board_with_folder):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        original_studio = board_with_folder.studio_id
        original_folder = board_with_folder.folder_id
        call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board_with_folder.id,
            name="Solo rename",
            expected_version=1,
        )
        db.refresh(board_with_folder)
        assert board_with_folder.studio_id == original_studio
        assert board_with_folder.folder_id == original_folder

    def test_rename_does_not_modify_nodes_or_edges(self, TestSession, db, user, board_with_graph):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        before_nodes = db.query(Node).filter(Node.board_id == board_with_graph.id).count()
        before_edges = db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
        call_tool(
            "rename_board",
            ctx,
            TestSession,
            board_id=board_with_graph.id,
            name="Sin tocar grafo",
            expected_version=1,
        )
        after_nodes = db.query(Node).filter(Node.board_id == board_with_graph.id).count()
        after_edges = db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
        assert after_nodes == before_nodes
        assert after_edges == before_edges

    def test_error_does_not_leave_partial_state(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:update"])
        with pytest.raises(ValueError):
            call_tool(
                "rename_board",
                ctx,
                TestSession,
                board_id=board.id,
                name="No persistir",
                expected_version=99,
            )
        db.refresh(board)
        assert board.name == "Board original"
        assert board.version == 1


class TestCreateNodeToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("create_node") == 1

    def test_create_card_node(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        payload = result["data"]["node"]
        assert result["ok"] is True
        assert payload["id"] is not None
        assert payload["board_id"] == board.id
        assert payload["type"] == "card"
        assert payload["title"] == "Card MCP"
        assert payload["x"] == 100
        assert payload["y"] == 200
        assert payload["blocks"] == []

    def test_create_timeline_node(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_timeline_node_payload(
                stages=[{"id": "s1", "title": "Etapa", "tags": ["x"]}],
                orientation="vertical",
            ),
        )
        payload = result["data"]["node"]
        assert payload["type"] == "timeline"
        assert payload["stages"][0]["title"] == "Etapa"
        assert payload["orientation"] == "vertical"

    def test_generates_id_server_side(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        node_id = result["data"]["node"]["id"]
        assert isinstance(node_id, str)
        assert len(node_id) == 32

    def test_increments_version_once_and_updates_timestamp(self, TestSession, db, user, board):
        import time

        before = board.updated_at
        time.sleep(0.02)
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        db.refresh(board)
        assert result["data"]["previous_version"] == 1
        assert result["data"]["board_version"] == 2
        assert board.version == 2
        assert board.updated_at > before

    def test_preserves_existing_nodes_and_edges(self, TestSession, db, user, board_with_graph):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        before_nodes = db.query(Node).filter(Node.board_id == board_with_graph.id).count()
        before_edges = db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board_with_graph.id,
            expected_version=1,
            node=_card_node_payload(title="Nuevo", x=-10, y=25),
        )
        after_nodes = db.query(Node).filter(Node.board_id == board_with_graph.id).count()
        after_edges = db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
        assert after_nodes == before_nodes + 1
        assert after_edges == before_edges
        assert result["data"]["node"]["x"] == -10
        assert result["data"]["node"]["y"] == 25


class TestCreateNodeToolScopes:
    def test_nodes_create_scope_allows(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        assert result["ok"] is True

    @pytest.mark.parametrize("scopes", [["nodes:read"], ["nodes:update"], ["boards:create"]])
    def test_other_scopes_not_enough(self, TestSession, user, board, scopes):
        ctx = _make_ctx(user.id, scopes=scopes)
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_card_node_payload(),
            )

    def test_context_not_authenticated_rejected(self, TestSession, board):
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            call_tool_without_context(
                "create_node",
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_card_node_payload(),
            )


class TestCreateNodeToolConstraints:
    def test_board_allowed_by_board_ids(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"], constraints={"board_ids": [board.id]})
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        assert result["ok"] is True

    def test_board_outside_board_ids_fails(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"], constraints={"board_ids": ["other-board"]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_card_node_payload(),
            )

    def test_board_allowed_by_studio_ids(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"], constraints={"studio_ids": [board.studio_id]})
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        assert result["ok"] is True

    def test_board_outside_studio_ids_fails(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"], constraints={"studio_ids": ["other-studio"]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_card_node_payload(),
            )

    def test_other_user_board_fails_as_not_found(self, TestSession, user, other_board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError, match="Tablero no encontrado"):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=other_board.id,
                expected_version=1,
                node=_card_node_payload(),
            )

    def test_without_constraints_works(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"], constraints=None)
        result = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        assert result["ok"] is True


class TestCreateNodeToolValidation:
    def test_missing_board_id_invalid_payload(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(TypeError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                expected_version=1,
                node=_card_node_payload(),
            )

    def test_missing_expected_version_invalid_payload(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(TypeError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                node=_card_node_payload(),
            )

    def test_missing_node_invalid_payload(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(TypeError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
            )

    def test_type_missing_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node={"title": "Sin tipo", "x": 1, "y": 2},
            )

    def test_unknown_type_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node={"type": "weird", "title": "Nope", "x": 1, "y": 2},
            )

    def test_invalid_card_payload_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_card_node_payload(blocks=[{"id": "b1", "type": "number", "value": "1"}]),
            )

    def test_invalid_timeline_payload_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_timeline_node_payload(stages=[{"id": "s1", "tags": []}]),
            )

    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), -float("inf")])
    def test_invalid_coordinates_rejected(self, TestSession, user, board, bad_value):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_card_node_payload(x=bad_value),
            )

    def test_extra_fields_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node={**_card_node_payload(), "board_id": "unexpected"},
            )

    def test_timeline_fields_sent_to_card_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node={**_card_node_payload(), "stages": []},
            )

    def test_card_fields_sent_to_timeline_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node={**_timeline_node_payload(), "blocks": []},
            )


class TestCreateNodeToolVersioning:
    def test_expected_version_correct(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(),
        )
        db.refresh(board)
        assert board.version == 2

    def test_expected_version_old_fails_without_node_or_timestamp_change(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        before = board.updated_at
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=0,
                node=_card_node_payload(),
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert payload["expected_version"] == 0
        assert payload["current_version"] == 1
        assert db.query(Node).filter(Node.board_id == board.id).count() == 0
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    def test_expected_version_future_fails_without_node_or_timestamp_change(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        before = board.updated_at
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=9,
                node=_card_node_payload(),
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert payload["expected_version"] == 9
        assert payload["current_version"] == 1
        assert db.query(Node).filter(Node.board_id == board.id).count() == 0
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    def test_conflict_after_first_create_only_persists_one_node(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        first = call_tool(
            "create_node",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            node=_card_node_payload(title="Primero"),
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_node",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                node=_card_node_payload(title="Segundo"),
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert db.query(Node).filter(Node.board_id == board.id).count() == 1
        db.refresh(board)
        assert board.version == 2
        assert first["data"]["board_version"] == 2


class TestUpdateNodeToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("update_node") == 1

    def test_update_card_partial_returns_full_node(self, TestSession, db, user, board):
        node = _persist_node(
            db,
            board,
            id="card-1",
            title="Antes",
            tags=["old"],
            blocks=[{"id": "b1", "type": "text", "value": "Old"}],
            ports=[{"id": "p1", "side": "left", "color": "#60A5FA", "label": "in"}],
        )
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={
                "title": "Nuevo título",
                "tags": ["fisiología"],
                "blocks": [],
                "ports": [{"id": "p2", "side": "right", "color": "#4ADE80", "label": "out"}],
                "w": 320,
            },
        )
        payload = result["data"]["node"]
        assert result["ok"] is True
        assert payload["id"] == node.id
        assert payload["board_id"] == board.id
        assert payload["type"] == "card"
        assert payload["title"] == "Nuevo título"
        assert payload["x"] == 100
        assert payload["y"] == 200
        assert payload["w"] == 320
        assert payload["tags"] == ["fisiología"]
        assert payload["blocks"] == []
        assert payload["stages"] == []
        assert payload["orientation"] is None
        assert result["data"]["changed_fields"] == ["title", "w", "ports", "tags", "blocks"]
        assert result["data"]["previous_version"] == 1
        assert result["data"]["board_version"] == 2

    def test_update_timeline_partial_preserves_absent_fields(self, TestSession, db, user, board):
        node = _persist_node(
            db,
            board,
            id="timeline-1",
            type="timeline",
            title="Timeline",
            x=33,
            y=44,
            w=360,
            stages=[{"id": "s1", "title": "Antes", "tags": ["a"]}],
            orientation="horizontal",
            tags=["old"],
        )
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={
                "title": "Después",
                "stages": [{"id": "s2", "title": "Nueva", "tags": ["b"]}],
                "orientation": "vertical",
            },
        )
        payload = result["data"]["node"]
        assert payload["title"] == "Después"
        assert payload["stages"] == [{"id": "s2", "title": "Nueva", "tags": ["b"]}]
        assert payload["orientation"] == "vertical"
        assert payload["x"] == 33
        assert payload["y"] == 44
        assert payload["w"] == 360
        assert payload["tags"] == ["old"]
        assert result["data"]["changed_fields"] == ["title", "stages", "orientation"]

    def test_explicit_null_tags_clear(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="card-clear", tags=["a", "b"])
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"tags": None},
        )
        assert result["data"]["node"]["tags"] == []
        assert result["data"]["changed_fields"] == ["tags"]

    def test_noop_write_still_increments_version(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="card-noop", title="Igual")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"title": "Igual"},
        )
        db.refresh(board)
        assert result["data"]["changed_fields"] == ["title"]
        assert result["data"]["board_version"] == 2
        assert board.version == 2


class TestUpdateNodeToolScopes:
    def test_nodes_update_scope_allows(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="scope-ok")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"title": "ok"},
        )
        assert result["ok"] is True

    @pytest.mark.parametrize("scopes", [["nodes:create"], ["nodes:read"], ["boards:update"]])
    def test_other_scopes_not_enough(self, TestSession, user, board, db, scopes):
        node = _persist_node(db, board, id=uuid.uuid4().hex[:16])
        ctx = _make_ctx(user.id, scopes=scopes)
        with pytest.raises(InsufficientScope):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"title": "no"},
            )

    def test_context_not_authenticated_rejected(self, TestSession, board, db):
        node = _persist_node(db, board, id="scope-noctx")
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            call_tool_without_context(
                "update_node",
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"title": "x"},
            )


class TestUpdateNodeToolConstraints:
    def test_board_allowed_by_board_ids(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="allowed-board")
        ctx = _make_ctx(user.id, scopes=["nodes:update"], constraints={"board_ids": [board.id]})
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"title": "ok"},
        )
        assert result["ok"] is True

    def test_board_outside_board_ids_fails(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="blocked-board")
        ctx = _make_ctx(user.id, scopes=["nodes:update"], constraints={"board_ids": ["other-board"]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"title": "no"},
            )

    def test_board_allowed_by_studio_ids(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="allowed-studio")
        ctx = _make_ctx(user.id, scopes=["nodes:update"], constraints={"studio_ids": [board.studio_id]})
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"title": "ok"},
        )
        assert result["ok"] is True

    def test_board_outside_studio_ids_fails(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="blocked-studio")
        ctx = _make_ctx(user.id, scopes=["nodes:update"], constraints={"studio_ids": ["other-studio"]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"title": "no"},
            )

    def test_other_user_node_fails_as_not_found(self, TestSession, user, other_board, db):
        node = _persist_node(db, other_board, id="foreign-node")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError, match="Nodo no encontrado"):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"title": "no"},
            )

    def test_without_constraints_works(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="no-constraints")
        ctx = _make_ctx(user.id, scopes=["nodes:update"], constraints=None)
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"title": "ok"},
        )
        assert result["ok"] is True


class TestUpdateNodeToolValidation:
    def test_missing_node_id_invalid_payload(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                expected_version=1,
                changes={"title": "x"},
            )

    def test_missing_expected_version_invalid_payload(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="missing-version")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                changes={"title": "x"},
            )

    def test_missing_changes_invalid_payload(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="missing-changes")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
            )

    def test_empty_changes_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="empty-changes")
        before = board.updated_at
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError, match="Debe especificar al menos un cambio"):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={},
            )
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    @pytest.mark.parametrize("field_name", ["id", "node_id", "board_id", "type", "x", "y", "edges"])
    def test_immutable_or_disallowed_fields_rejected(self, TestSession, user, board, db, field_name):
        node = _persist_node(db, board, id=uuid.uuid4().hex[:16])
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={field_name: "bad"},
            )

    def test_unknown_field_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="unknown-field")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"user_id": "hack"},
            )

    def test_blocks_on_timeline_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="timeline-bad", type="timeline")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"blocks": []},
            )

    def test_stages_on_card_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="card-bad")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"stages": []},
            )

    def test_orientation_on_card_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="card-orientation")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"orientation": "vertical"},
            )

    def test_invalid_orientation_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="timeline-orientation", type="timeline")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"orientation": "diagonal"},
            )

    def test_malformed_payload_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="malformed")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"ports": "not-a-list"},
            )


class TestUpdateNodeToolIntegrity:
    def test_update_does_not_move_node(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="no-move", x=11, y=22, title="Antes")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"title": "Después"},
        )
        assert result["data"]["node"]["x"] == 11
        assert result["data"]["node"]["y"] == 22

    def test_update_does_not_change_other_nodes_or_edges(self, TestSession, db, user, board_with_graph):
        target = _persist_node(db, board_with_graph, id="target-node", title="Antes")
        before_edges = db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
        before_other = db.get(Node, "node-a").title
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=target.id,
            expected_version=1,
            changes={"title": "Después"},
        )
        db.expire_all()
        assert db.get(Node, "target-node").title == "Después"
        assert db.get(Node, "node-a").title == before_other
        assert db.query(Edge).filter(Edge.board_id == board_with_graph.id).count() == before_edges

    def test_conflict_does_not_change_content_or_version(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="conflict-node", title="Inicial")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "update_node",
            ctx,
            TestSession,
            node_id=node.id,
            expected_version=1,
            changes={"title": "Ganador"},
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=1,
                changes={"title": "Perdedor"},
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.expire_all()
        assert db.get(Node, node.id).title == "Ganador"
        assert db.get(Board, board.id).version == 2


class TestUpdateNodeToolVersioning:
    def test_expected_version_old_fails_without_timestamp_change(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="old-version")
        before = board.updated_at
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=0,
                changes={"title": "x"},
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    def test_expected_version_future_fails_without_timestamp_change(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="future-version")
        before = board.updated_at
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "update_node",
                ctx,
                TestSession,
                node_id=node.id,
                expected_version=9,
                changes={"title": "x"},
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before


class TestMoveNodeToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("move_node") == 1

    def test_move_card_node(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-card", title="Card", x=10, y=20)
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node",
            ctx,
            TestSession,
            node_id=node.id,
            x=300,
            y=400,
            expected_version=1,
        )
        payload = result["data"]["node"]
        assert result["ok"] is True
        assert payload["id"] == node.id
        assert payload["x"] == 300
        assert payload["y"] == 400
        assert result["data"]["previous_position"] == {"x": 10, "y": 20}
        assert result["data"]["position"] == {"x": 300, "y": 400}

    def test_move_timeline_node(self, TestSession, db, user, board):
        node = _persist_node(
            db, board, id="move-tl", type="timeline", title="TL",
            x=0, y=0, orientation="horizontal",
        )
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node",
            ctx,
            TestSession,
            node_id=node.id,
            x=150,
            y=250,
            expected_version=1,
        )
        payload = result["data"]["node"]
        assert payload["x"] == 150
        assert payload["y"] == 250
        assert payload["type"] == "timeline"
        assert payload["orientation"] == "horizontal"

    def test_positive_coordinates(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-pos")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=480, y=120, expected_version=1,
        )
        assert result["data"]["node"]["x"] == 480
        assert result["data"]["node"]["y"] == 120

    def test_negative_coordinates(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-neg")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=-100, y=-250, expected_version=1,
        )
        assert result["data"]["node"]["x"] == -100
        assert result["data"]["node"]["y"] == -250

    def test_float_coordinates(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-float")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100.5, y=200.75, expected_version=1,
        )
        assert result["data"]["node"]["x"] == 100.5
        assert result["data"]["node"]["y"] == 200.75

    def test_preserves_content(self, TestSession, db, user, board):
        node = _persist_node(
            db, board, id="move-content", title="Mantener",
            tags=["a", "b"],
            blocks=[{"id": "b1", "type": "text", "value": "Hello"}],
            ports=[{"id": "p1", "side": "left", "color": "#60A5FA", "label": "in"}],
        )
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        p = result["data"]["node"]
        assert p["title"] == "Mantener"
        assert p["tags"] == ["a", "b"]
        assert p["blocks"] == [{"id": "b1", "type": "text", "value": "Hello"}]
        assert p["ports"] == [{"id": "p1", "side": "left", "color": "#60A5FA", "label": "in"}]

    def test_preserves_type_and_width(self, TestSession, db, user, board):
        node = _persist_node(
            db, board, id="move-type", type="timeline", w=360, orientation="vertical",
        )
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=50, y=60, expected_version=1,
        )
        p = result["data"]["node"]
        assert p["type"] == "timeline"
        assert p["w"] == 360
        assert p["orientation"] == "vertical"

    def test_increments_version_once(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-ver")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.refresh(board)
        assert result["data"]["previous_version"] == 1
        assert result["data"]["board_version"] == 2
        assert board.version == 2

    def test_updates_timestamp(self, TestSession, db, user, board):
        import time
        node = _persist_node(db, board, id="move-ts")
        before = board.updated_at
        time.sleep(0.02)
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.refresh(board)
        assert board.updated_at > before

    def test_returns_previous_and_new_position(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-pos-rtn", x=11, y=22)
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=333, y=444, expected_version=1,
        )
        assert result["data"]["previous_position"] == {"x": 11, "y": 22}
        assert result["data"]["position"] == {"x": 333, "y": 444}


class TestMoveNodeToolScopes:
    def test_nodes_update_scope_allows(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-scope-ok")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        assert result["ok"] is True

    @pytest.mark.parametrize("scopes", [["nodes:create"], ["nodes:read"], ["boards:update"]])
    def test_other_scopes_not_enough(self, TestSession, user, board, db, scopes):
        node = _persist_node(db, board, id=uuid.uuid4().hex[:16])
        ctx = _make_ctx(user.id, scopes=scopes)
        with pytest.raises(InsufficientScope):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=1,
            )

    def test_context_not_authenticated_rejected(self, TestSession, board, db):
        node = _persist_node(db, board, id="move-scope-noctx")
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            call_tool_without_context(
                "move_node", TestSession,
                node_id=node.id, x=100, y=200, expected_version=1,
            )


class TestMoveNodeToolConstraints:
    def test_board_allowed_by_board_ids(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-const-ok")
        ctx = _make_ctx(
            user.id, scopes=["nodes:update"],
            constraints={"board_ids": [board.id]},
        )
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        assert result["ok"] is True

    def test_board_outside_board_ids_fails(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-const-block")
        ctx = _make_ctx(
            user.id, scopes=["nodes:update"],
            constraints={"board_ids": ["other-board"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=1,
            )

    def test_board_allowed_by_studio_ids(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-studio-ok")
        ctx = _make_ctx(
            user.id, scopes=["nodes:update"],
            constraints={"studio_ids": [board.studio_id]},
        )
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        assert result["ok"] is True

    def test_board_outside_studio_ids_fails(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-studio-block")
        ctx = _make_ctx(
            user.id, scopes=["nodes:update"],
            constraints={"studio_ids": ["other-studio"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=1,
            )

    def test_other_user_node_fails_as_not_found(self, TestSession, user, other_board, db):
        node = _persist_node(db, other_board, id="move-foreign")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError, match="Nodo no encontrado"):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=1,
            )

    def test_without_constraints_works(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-no-constraints")
        ctx = _make_ctx(user.id, scopes=["nodes:update"], constraints=None)
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        assert result["ok"] is True


class TestMoveNodeToolValidation:
    def test_missing_node_id_invalid_payload(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "move_node", ctx, TestSession,
                x=100, y=200, expected_version=1,
            )

    def test_missing_expected_version_invalid_payload(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-miss-ver")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200,
            )

    def test_missing_x_invalid_payload(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-miss-x")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, y=200, expected_version=1,
            )

    def test_missing_y_invalid_payload(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-miss-y")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, expected_version=1,
            )

    def test_x_string_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-str-x")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x="abc", y=200, expected_version=1,
            )

    def test_y_string_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-str-y")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y="abc", expected_version=1,
            )

    def test_boolean_x_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-bool-x")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError, match="Coordenada booleana"):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=True, y=200, expected_version=1,
            )

    def test_boolean_y_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-bool-y")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError, match="Coordenada booleana"):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=True, expected_version=1,
            )

    def test_nan_x_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-nan-x")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=float("nan"), y=200, expected_version=1,
            )

    def test_infinity_x_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-inf-x")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=float("inf"), y=200, expected_version=1,
            )

    def test_neg_infinity_x_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-neg-inf-x")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=-float("inf"), y=200, expected_version=1,
            )

    def test_extra_fields_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-extra")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=1,
                title="Hack",
            )

    def test_content_changes_rejected(self, TestSession, user, board, db):
        node = _persist_node(db, board, id="move-content-rej")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(TypeError):
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=1,
                changes={"title": "Hack"},
            )

    def test_nonexistent_node(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError, match="Nodo no encontrado"):
            call_tool(
                "move_node", ctx, TestSession,
                node_id="missing-node", x=100, y=200, expected_version=1,
            )


class TestMoveNodeToolIntegrity:
    def test_move_does_not_change_title(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-int-title", title="Fijo")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.expire_all()
        assert db.get(Node, node.id).title == "Fijo"

    def test_move_does_not_change_tags(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-int-tags", tags=["a", "b"])
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.expire_all()
        assert db.get(Node, node.id).tags == ["a", "b"]

    def test_move_does_not_change_blocks(self, TestSession, db, user, board):
        node = _persist_node(
            db, board, id="move-int-blocks",
            blocks=[{"id": "b1", "type": "text", "value": "X"}],
        )
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.expire_all()
        assert db.get(Node, node.id).blocks == [{"id": "b1", "type": "text", "value": "X"}]

    def test_move_does_not_change_stages(self, TestSession, db, user, board):
        node = _persist_node(
            db, board, id="move-int-stages", type="timeline",
            stages=[{"id": "s1", "title": "Paso", "tags": ["x"]}],
        )
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.expire_all()
        assert db.get(Node, node.id).stages == [{"id": "s1", "title": "Paso", "tags": ["x"]}]

    def test_move_does_not_change_type_or_board_id(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-int-type", type="timeline")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.expire_all()
        loaded = db.get(Node, node.id)
        assert loaded.type == "timeline"
        assert loaded.board_id == board.id

    def test_move_does_not_affect_other_nodes_or_edges(self, TestSession, db, user, board_with_graph):
        target = _persist_node(db, board_with_graph, id="move-int-only", x=0, y=0)
        before_edges = (
            db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
        )
        before_other_x = db.get(Node, "node-a").x
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=target.id, x=999, y=888, expected_version=1,
        )
        db.expire_all()
        assert db.get(Node, "node-a").x == before_other_x
        assert (
            db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
            == before_edges
        )

    def test_conflict_does_not_move_node_or_advance_version(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-conflict", x=10, y=20)
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=300, y=400, expected_version=1,
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=500, y=600, expected_version=1,
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.expire_all()
        assert db.get(Node, node.id).x == 300
        assert db.get(Node, node.id).y == 400
        assert db.get(Board, board.id).version == 2


class TestMoveNodeToolVersioning:
    def test_expected_version_correct(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-ver-ok")
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.refresh(board)
        assert board.version == 2

    def test_expected_version_old_fails_without_timestamp_change(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-ver-old")
        before = board.updated_at
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=0,
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    def test_expected_version_future_fails_without_timestamp_change(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-ver-future")
        before = board.updated_at
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=100, y=200, expected_version=9,
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    def test_two_moves_same_version_only_one_succeeds(self, TestSession, db, user, board):
        node = _persist_node(db, board, id="move-race", x=0, y=0)
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        first = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=300, y=400, expected_version=1,
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "move_node", ctx, TestSession,
                node_id=node.id, x=500, y=600, expected_version=1,
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert first["data"]["board_version"] == 2
        db.expire_all()
        assert db.get(Node, node.id).x == 300
        assert db.get(Node, node.id).y == 400
        assert db.get(Board, board.id).version == 2

    def test_noop_move_increments_version(self, TestSession, db, user, board):
        """Mover a la misma posición incrementa versión y actualiza timestamp."""
        import time
        node = _persist_node(db, board, id="move-noop", x=100, y=200)
        before = board.updated_at
        time.sleep(0.02)
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        result = call_tool(
            "move_node", ctx, TestSession,
            node_id=node.id, x=100, y=200, expected_version=1,
        )
        db.refresh(board)
        assert result["data"]["board_version"] == 2
        assert board.version == 2
        assert board.updated_at > before
        assert result["data"]["previous_position"] == {"x": 100, "y": 200}
        assert result["data"]["position"] == {"x": 100, "y": 200}


@pytest.fixture()
def board_with_two_nodes(db, user, board) -> Board:
    """Crea un board con dos nodos (n1, n2) que tienen puertos."""
    n1 = Node(
        id="edge-n1",
        board_id=board.id,
        title="Source",
        ports=[{"id": "out", "side": "right", "color": "#60A5FA", "label": ""}],
    )
    n2 = Node(
        id="edge-n2",
        board_id=board.id,
        title="Target",
        ports=[{"id": "in", "side": "left", "color": "#4ADE80", "label": ""}],
    )
    db.add_all([n1, n2])
    db.commit()
    db.refresh(board)
    return board


class TestCreateEdgeToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("create_edge") == 1

    def test_create_edge_between_two_nodes(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        payload = result["data"]["edge"]
        assert result["ok"] is True
        assert payload["id"] is not None
        assert payload["board_id"] == board.id
        assert payload["from"]["nodeId"] == "edge-n1"
        assert payload["from"]["portId"] == "out"
        assert payload["to"]["nodeId"] == "edge-n2"
        assert payload["to"]["portId"] == "in"
        assert payload["curved"] is True
        assert payload["label"] == ""

    def test_create_edge_with_label(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "depende de",
            },
        )
        assert result["data"]["edge"]["label"] == "depende de"

    def test_create_edge_without_label_uses_default(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert result["data"]["edge"]["label"] == ""

    def test_curved_true(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "curved": True,
            },
        )
        assert result["data"]["edge"]["curved"] is True

    def test_curved_false(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "curved": False,
            },
        )
        assert result["data"]["edge"]["curved"] is False

    def test_server_side_id_generated(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = result["data"]["edge"]["id"]
        assert isinstance(edge_id, str)
        assert len(edge_id) == 32

    def test_preserves_nodes(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        before_nodes = db.query(Node).filter(Node.board_id == board.id).count()
        call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        after_nodes = db.query(Node).filter(Node.board_id == board.id).count()
        assert after_nodes == before_nodes

    def test_preserves_other_edges(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        db.refresh(board)
        ctx2 = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx2,
            TestSession,
            board_id=board.id,
            expected_version=2,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert result["ok"] is True
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == 2

    def test_increments_version_once(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        db.refresh(board)
        assert result["data"]["previous_version"] == 1
        assert result["data"]["board_version"] == 2
        assert board.version == 2

    def test_updates_timestamp(self, TestSession, db, user, board_with_two_nodes):
        import time
        board = board_with_two_nodes
        before = board.updated_at
        time.sleep(0.02)
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        db.refresh(board)
        assert board.updated_at > before

    def test_uniform_response_shape(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert set(result.keys()) == {"ok", "data"}
        assert "edge" in result["data"]
        assert "previous_version" in result["data"]
        assert "board_version" in result["data"]


class TestCreateEdgeToolScopes:
    def test_edges_create_scope_allows(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert result["ok"] is True

    @pytest.mark.parametrize("scopes", [["edges:read"], ["nodes:create"], ["nodes:update"], ["boards:update"]])
    def test_other_scopes_not_enough(self, TestSession, user, board_with_two_nodes, db, scopes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=scopes)
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )

    def test_context_not_authenticated_rejected(self, TestSession, board_with_two_nodes):
        board = board_with_two_nodes
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            call_tool_without_context(
                "create_edge",
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )


class TestCreateEdgeToolConstraints:
    def test_board_allowed_by_board_ids(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(
            user.id, scopes=["edges:create"],
            constraints={"board_ids": [board.id]},
        )
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert result["ok"] is True

    def test_board_outside_board_ids_fails(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(
            user.id, scopes=["edges:create"],
            constraints={"board_ids": ["other-board"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )

    def test_board_allowed_by_studio_ids(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(
            user.id, scopes=["edges:create"],
            constraints={"studio_ids": [board.studio_id]},
        )
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert result["ok"] is True

    def test_board_outside_studio_ids_fails(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(
            user.id, scopes=["edges:create"],
            constraints={"studio_ids": ["other-studio"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )

    def test_other_user_board_fails_as_not_found(self, TestSession, user, other_board, db):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError, match="Tablero no encontrado"):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=other_board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )

    def test_without_constraints_works(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"], constraints=None)
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert result["ok"] is True


class TestCreateEdgeToolNodeValidation:
    def test_source_node_nonexistent(self, TestSession, user, board, db):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError, match="nodo"):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "no-such-node", "portId": "p"},
                    "to": {"nodeId": "no-such-node", "portId": "p"},
                },
            )

    def test_target_node_nonexistent(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError, match="nodo"):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "no-such-node", "portId": "in"},
                },
            )

    def test_source_in_other_board(self, TestSession, user, board, board_with_two_nodes, db):
        """Un nodo que no pertenece al board debe ser rechazado."""
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError, match="nodo"):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "no-such-node", "portId": "in"},
                },
            )

    def test_self_edge_allowed(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n1", "portId": "out"},
            },
        )
        assert result["ok"] is True
        assert result["data"]["edge"]["from"]["nodeId"] == "edge-n1"
        assert result["data"]["edge"]["to"]["nodeId"] == "edge-n1"


class TestCreateEdgeToolPortValidation:
    def test_valid_ports_accepted(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        assert result["ok"] is True

    def test_invalid_source_port_fails(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError, match="Puerto origen"):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "nonexistent"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )

    def test_invalid_target_port_fails(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError, match="Puerto destino"):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "nonexistent"},
                },
            )


class TestCreateEdgeToolValidation:
    def test_missing_board_id_invalid_payload(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(TypeError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                expected_version=1,
                edge={
                    "from": {"nodeId": "a", "portId": "p"},
                    "to": {"nodeId": "b", "portId": "p"},
                },
            )

    def test_missing_expected_version_invalid_payload(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(TypeError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                edge={
                    "from": {"nodeId": "a", "portId": "p"},
                    "to": {"nodeId": "b", "portId": "p"},
                },
            )

    def test_missing_edge_invalid_payload(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(TypeError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
            )

    def test_missing_from_in_edge_fails(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "to": {"nodeId": "b", "portId": "p"},
                },
            )

    def test_missing_to_in_edge_fails(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "a", "portId": "p"},
                },
            )

    def test_missing_nodeId_in_source_fails(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"portId": "p"},
                    "to": {"nodeId": "b", "portId": "p"},
                },
            )

    def test_missing_portId_in_source_fails(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "a"},
                    "to": {"nodeId": "b", "portId": "p"},
                },
            )

    def test_edge_id_in_edge_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "id": "fixed-id",
                    "from": {"nodeId": "a", "portId": "p"},
                    "to": {"nodeId": "b", "portId": "p"},
                },
            )

    def test_extra_fields_in_edge_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "a", "portId": "p"},
                    "to": {"nodeId": "b", "portId": "p"},
                    "extra": "hack",
                },
            )

    def test_extra_fields_in_root_payload_rejected(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(TypeError):
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "a", "portId": "p"},
                    "to": {"nodeId": "b", "portId": "p"},
                },
                unexpected="hack",
            )


class TestCreateEdgeToolVersioning:
    def test_expected_version_correct(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        db.refresh(board)
        assert board.version == 2

    def test_expected_version_old_fails_without_edge_or_timestamp(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        before = board.updated_at
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=0,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == 0
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    def test_expected_version_future_fails_without_edge_or_timestamp(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        before = board.updated_at
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=9,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                },
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == 0
        db.refresh(board)
        assert board.version == 1
        assert board.updated_at == before

    def test_conflict_only_one_edge_created(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        first = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edge",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edge={
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "segundo",
                },
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == 1
        db.refresh(board)
        assert board.version == 2
        assert first["data"]["board_version"] == 2


class TestUpdateEdgeToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("update_edge") == 1

    def test_update_label(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "Nueva relación"},
        )
        payload = result["data"]["edge"]
        assert result["ok"] is True
        assert payload["id"] == edge_id
        assert payload["label"] == "Nueva relación"
        assert payload["curved"] is True
        assert payload["from"]["nodeId"] == "edge-n1"
        assert payload["to"]["nodeId"] == "edge-n2"

    def test_update_curved(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"curved": False},
        )
        assert result["data"]["edge"]["curved"] is False

    def test_update_both(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "old",
                "curved": False,
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "new", "curved": True},
        )
        assert result["data"]["edge"]["label"] == "new"
        assert result["data"]["edge"]["curved"] is True
        assert result["data"]["changed_fields"] == ["curved", "label"]

    def test_partial_update_preserves_other_fields(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "keep",
                "curved": False,
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "only label"},
        )
        assert result["data"]["edge"]["label"] == "only label"
        assert result["data"]["edge"]["curved"] is False

    def test_extrema_intact(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "test"},
        )
        assert result["data"]["edge"]["from"]["nodeId"] == "edge-n1"
        assert result["data"]["edge"]["from"]["portId"] == "out"
        assert result["data"]["edge"]["to"]["nodeId"] == "edge-n2"
        assert result["data"]["edge"]["to"]["portId"] == "in"

    def test_returns_changed_fields(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x", "curved": False},
        )
        assert set(result["data"]["changed_fields"]) == {"curved", "label"}

    def test_increments_version_once(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        db.refresh(board)
        assert result["data"]["previous_version"] == 2
        assert result["data"]["board_version"] == 3
        assert board.version == 3

    def test_updates_timestamp(self, TestSession, db, user, board_with_two_nodes):
        import time
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        before = board.updated_at
        time.sleep(0.02)
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        db.refresh(board)
        assert board.updated_at > before

    def test_uniform_response_shape(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        assert set(result.keys()) == {"ok", "data"}
        assert "edge" in result["data"]
        assert "changed_fields" in result["data"]
        assert "previous_version" in result["data"]
        assert "board_version" in result["data"]

    def test_noop_update_increments_version(self, TestSession, db, user, board_with_two_nodes):
        import time
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "curved": True,
                "label": "",
            },
        )
        edge_id = created["data"]["edge"]["id"]
        before = board.updated_at
        time.sleep(0.02)
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"curved": True},
        )
        db.refresh(board)
        assert result["data"]["board_version"] == 3
        assert board.version == 3
        assert board.updated_at > before


class TestUpdateEdgeToolScopes:
    def test_edges_update_scope_allows(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        assert result["ok"] is True

    @pytest.mark.parametrize("scopes", [["edges:create"], ["edges:read"], ["nodes:update"], ["boards:update"]])
    def test_other_scopes_not_enough(self, TestSession, user, board_with_two_nodes, db, scopes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=scopes)
        with pytest.raises(InsufficientScope):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"label": "x"},
            )

    def test_context_not_authenticated_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            call_tool_without_context(
                "update_edge",
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"label": "x"},
            )


class TestUpdateEdgeToolConstraints:
    def test_board_allowed_by_board_ids(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(
            user.id, scopes=["edges:update"],
            constraints={"board_ids": [board.id]},
        )
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        assert result["ok"] is True

    def test_board_outside_board_ids_fails(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(
            user.id, scopes=["edges:update"],
            constraints={"board_ids": ["other-board"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"label": "x"},
            )

    def test_board_allowed_by_studio_ids(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(
            user.id, scopes=["edges:update"],
            constraints={"studio_ids": [board.studio_id]},
        )
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        assert result["ok"] is True

    def test_board_outside_studio_ids_fails(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(
            user.id, scopes=["edges:update"],
            constraints={"studio_ids": ["other-studio"]},
        )
        with pytest.raises(ConstraintViolation):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"label": "x"},
            )

    def test_other_user_edge_fails_as_not_found(self, TestSession, user, board_with_two_nodes, other_board, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        other_user_ctx = _make_ctx("other-user-id", scopes=["edges:update"])
        with pytest.raises(ValueError, match="Arista no encontrada"):
            call_tool(
                "update_edge",
                other_user_ctx,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"label": "x"},
            )

    def test_without_constraints_works(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"], constraints=None)
        result = call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        assert result["ok"] is True


class TestUpdateEdgeToolValidation:
    def test_missing_edge_id_invalid_payload(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(TypeError):
            call_tool(
                "update_edge",
                ctx,
                TestSession,
                expected_version=1,
                changes={"label": "x"},
            )

    def test_missing_expected_version_invalid_payload(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(TypeError):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                changes={"label": "x"},
            )

    def test_missing_changes_invalid_payload(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(TypeError):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
            )

    def test_empty_changes_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        db.refresh(board)
        before = board.updated_at
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError, match="Debe especificar al menos un cambio"):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={},
            )
        db.refresh(board)
        assert board.version == 2
        assert board.updated_at == before

    def test_id_in_changes_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"id": "new-id"},
            )

    def test_from_in_changes_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"from": {"nodeId": "x", "portId": "y"}},
            )

    def test_to_in_changes_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"to": {"nodeId": "x", "portId": "y"}},
            )

    def test_unknown_field_in_changes_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"board_id": "hack"},
            )

    def test_nonexistent_edge(self, TestSession, user):
        ctx = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError, match="Arista no encontrada"):
            call_tool(
                "update_edge",
                ctx,
                TestSession,
                edge_id="no-such-edge",
                expected_version=1,
                changes={"label": "x"},
            )

    def test_curved_non_bool_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError, match="curved debe ser un booleano"):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"curved": "true"},
            )

    def test_curved_as_int_rejected(self, TestSession, user, board_with_two_nodes, db):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError, match="curved debe ser un booleano"):
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"curved": 1},
            )


class TestUpdateEdgeToolIntegrity:
    def test_update_does_not_change_nodes(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        before_nodes = db.query(Node).filter(Node.board_id == board.id).count()
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        after_nodes = db.query(Node).filter(Node.board_id == board.id).count()
        assert after_nodes == before_nodes

    def test_update_does_not_affect_other_edges(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created_1 = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "first",
            },
        )
        created_2 = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=2,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "second",
            },
        )
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=created_2["data"]["edge"]["id"],
            expected_version=3,
            changes={"label": "updated"},
        )
        db.expire_all()
        e1 = db.get(Edge, created_1["data"]["edge"]["id"])
        assert e1.label == "first"

    def test_conflict_does_not_change_edge_or_version(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "original",
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "winner"},
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"label": "loser"},
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.expire_all()
        edge = db.get(Edge, edge_id)
        assert edge.label == "winner"
        assert db.get(Board, board.id).version == 3


class TestUpdateEdgeToolVersioning:
    def test_expected_version_correct(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        call_tool(
            "update_edge",
            ctx2,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "x"},
        )
        db.refresh(board)
        assert board.version == 3

    def test_expected_version_old_fails_without_changes(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        db.refresh(board)
        before = board.updated_at
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=0,
                changes={"label": "x"},
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.refresh(board)
        assert board.version == 2
        assert board.updated_at == before

    def test_expected_version_future_fails_without_changes(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            },
        )
        edge_id = created["data"]["edge"]["id"]
        db.refresh(board)
        before = board.updated_at
        ctx2 = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "update_edge",
                ctx2,
                TestSession,
                edge_id=edge_id,
                expected_version=9,
                changes={"label": "x"},
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.refresh(board)
        assert board.version == 2
        assert board.updated_at == before

    def test_conflict_after_first_update_preserves_original(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create", "edges:update"])
        created = call_tool(
            "create_edge",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "original",
            },
        )
        edge_id = created["data"]["edge"]["id"]
        first = call_tool(
            "update_edge",
            ctx,
            TestSession,
            edge_id=edge_id,
            expected_version=2,
            changes={"label": "A"},
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "update_edge",
                ctx,
                TestSession,
                edge_id=edge_id,
                expected_version=2,
                changes={"label": "B"},
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        assert first["data"]["board_version"] == 3
        db.expire_all()
        edge = db.get(Edge, edge_id)
        assert edge.label == "A"
        assert db.get(Board, board.id).version == 3


class TestCreateNodesBatchToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("create_nodes_batch") == 1

    def test_batch_single_card(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[
                {"client_id": "n1", "node": {"type": "card", "title": "Solo"}},
            ],
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["created_count"] == 1
        assert data["previous_version"] == 1
        assert data["board_version"] == 2
        assert "concepto-central" not in str(data)
        assert data["created"]["n1"] is not None
        assert data["nodes"][0]["client_id"] == "n1"
        assert data["nodes"][0]["node"]["title"] == "Solo"

    def test_batch_multiple_cards(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[
                {"client_id": "a", "node": {"type": "card", "title": "A", "x": 100}},
                {"client_id": "b", "node": {"type": "card", "title": "B", "x": 300}},
                {"client_id": "c", "node": {"type": "card", "title": "C", "x": 500}},
            ],
        )
        data = result["data"]
        assert data["created_count"] == 3
        assert [n["node"]["title"] for n in data["nodes"]] == ["A", "B", "C"]
        assert list(data["created"].keys()) == ["a", "b", "c"]
        # IDs server-side (no coinciden con client_id)
        for cid in ("a", "b", "c"):
            assert data["created"][cid] != cid
            assert len(data["created"][cid]) == 32

    def test_batch_mixed_card_timeline(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[
                {"client_id": "c1", "node": {"type": "card", "title": "Card"}},
                {"client_id": "t1", "node": {"type": "timeline", "title": "TL",
                                              "stages": [{"id": "s1", "title": "Paso", "tags": []}]}},
            ],
        )
        data = result["data"]
        assert data["created_count"] == 2
        assert data["nodes"][0]["node"]["type"] == "card"
        assert data["nodes"][1]["node"]["type"] == "timeline"
        assert data["nodes"][1]["node"]["stages"] is not None

    def test_batch_version_increments_once(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[
                {"client_id": "a", "node": {"type": "card", "title": "A"}},
                {"client_id": "b", "node": {"type": "card", "title": "B"}},
                {"client_id": "c", "node": {"type": "card", "title": "C"}},
            ],
        )
        db.expire_all()
        updated = db.get(Board, board.id)
        assert updated.version == 2  # una sola vez

    def test_body_shape(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[
                {"client_id": "x", "node": {"type": "card", "title": "X"}},
            ],
        )
        assert set(result.keys()) == {"ok", "data"}
        data = result["data"]
        assert "nodes" in data
        assert "created" in data
        assert "created_count" in data
        assert "previous_version" in data
        assert "board_version" in data
        assert all(k in data["nodes"][0] for k in ("client_id", "node"))


class TestCreateNodesBatchToolScopes:
    def test_nodes_create_allows(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[{"client_id": "n1", "node": {"type": "card", "title": "OK"}}],
        )
        assert result["ok"] is True

    def test_nodes_read_does_not_allow(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:read"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )

    def test_nodes_update_does_not_allow(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )

    def test_boards_create_does_not_allow(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["boards:create"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )

    def test_no_context_fails(self, TestSession):
        with pytest.raises(RuntimeError):
            call_tool_without_context(
                "create_nodes_batch",
                TestSession,
                board_id="x",
                expected_version=1,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )


class TestCreateNodesBatchToolConstraints:
    def test_board_ids_allows(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"],
                         constraints={"board_ids": [board.id]})
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[{"client_id": "n1", "node": {"type": "card", "title": "OK"}}],
        )
        assert result["ok"] is True

    def test_board_ids_denies(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"],
                         constraints={"board_ids": ["other-board"]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )

    def test_studio_ids_allows(self, TestSession, db, user, studio, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"],
                         constraints={"studio_ids": [studio.id]})
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[{"client_id": "n1", "node": {"type": "card", "title": "OK"}}],
        )
        assert result["ok"] is True

    def test_studio_ids_denies(self, TestSession, db, user, studio, other_studio, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"],
                         constraints={"studio_ids": [other_studio.id]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )

    def test_foreign_board_fails(self, TestSession, db, user, other_board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError, match="Tablero no encontrado"):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=other_board.id,
                expected_version=1,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )

    def test_token_without_constraints(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[{"client_id": "n1", "node": {"type": "card", "title": "OK"}}],
        )
        assert result["ok"] is True


class TestCreateNodesBatchToolLimits:
    def test_empty_list_rejected(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[],
            )

    def test_exactly_100_ok(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        nodes = [
            {"client_id": f"n{i:03d}", "node": {"type": "card", "title": f"N{i}"}}
            for i in range(100)
        ]
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=nodes,
        )
        assert result["ok"] is True
        assert result["data"]["created_count"] == 100

    def test_101_rejected(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        nodes = [
            {"client_id": f"n{i:03d}", "node": {"type": "card", "title": f"N{i}"}}
            for i in range(101)
        ]
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=nodes,
            )


class TestCreateNodesBatchToolClientId:
    def test_required(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"node": {"type": "card", "title": "No client_id"}}],
            )

    def test_empty_string_rejected(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"client_id": "", "node": {"type": "card", "title": "Empty"}}],
            )

    def test_duplicate_rejected(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "dup", "node": {"type": "card", "title": "A"}},
                    {"client_id": "dup", "node": {"type": "card", "title": "B"}},
                ],
            )
        assert "duplicado" in str(exc.value)

    def test_not_persisted_as_id(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[{"client_id": "my-ref", "node": {"type": "card", "title": "Ref"}}],
        )
        real_id = result["data"]["created"]["my-ref"]
        node = db.get(Node, real_id)
        assert node is not None
        assert node.id == real_id  # client_id no es el ID
        assert node.title == "Ref"


class TestCreateNodesBatchToolValidation:
    def test_invalid_element_at_start(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {"type": "invalid", "title": "X"}},
                    {"client_id": "ok", "node": {"type": "card", "title": "OK"}},
                ],
            )

    def test_invalid_element_in_middle(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "a", "node": {"type": "card", "title": "A"}},
                    {"client_id": "bad", "node": {"type": "invalid", "title": "X"}},
                    {"client_id": "c", "node": {"type": "card", "title": "C"}},
                ],
            )

    def test_invalid_element_at_end(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "a", "node": {"type": "card", "title": "A"}},
                    {"client_id": "b", "node": {"type": "card", "title": "B"}},
                    {"client_id": "bad", "node": {"type": "invalid", "title": "X"}},
                ],
            )

    def test_invalid_card(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {
                        "type": "card",
                        "stages": [{"id": "s1", "title": "A", "tags": []}]},
                    },
                ],
            )

    def test_invalid_timeline(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {
                        "type": "timeline",
                        "orientation": "diagonal",
                    }},
                ],
            )

    def test_extra_fields_rejected(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {
                        "type": "card", "title": "X", "extra_field": "nope",
                    }},
                ],
            )

    def test_node_id_field_rejected(self, TestSession, db, user, board):
        """El cliente no debe enviar id — se genera server-side."""
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {
                        "type": "card", "id": "client-chosen-id",
                    }},
                ],
            )

    def test_extra_fields_in_batch_item_rejected(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {"type": "card"}, "extra": "nope"},
                ],
            )

    def test_invalid_coordinates(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {
                        "type": "card", "x": float("inf"),
                    }},
                ],
            )

    def test_wrong_version_fails_without_creating_anything(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=99,
                nodes=[
                    {"client_id": "n1", "node": {"type": "card", "title": "Nunca"}},
                ],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 0
        assert db.get(Board, board.id).version == 1


class TestCreateNodesBatchToolIntegrity:
    def test_failure_creates_nothing(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[
                    {"client_id": "a", "node": {"type": "card", "title": "A"}},
                    {"client_id": "bad", "node": {"type": "invalid", "title": "X"}},
                ],
            )
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 0
        assert db.get(Board, board.id).version == 1

    def test_violation_does_not_affect_existing(self, TestSession, db, user, board_with_graph):
        """Un batch fallido no modifica nodes ni edges existentes."""
        before_nodes = db.query(Node).filter(Node.board_id == board_with_graph.id).count()
        before_edges = db.query(Edge).filter(Edge.board_id == board_with_graph.id).count()
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board_with_graph.id,
                expected_version=1,
                nodes=[
                    {"client_id": "bad", "node": {"type": "invalid"}},
                ],
            )
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board_with_graph.id).count() == before_nodes
        assert db.query(Edge).filter(Edge.board_id == board_with_graph.id).count() == before_edges


class TestCreateNodesBatchToolVersioning:
    def test_old_version_fails(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=0,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"

    def test_future_version_fails(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=9,
                nodes=[{"client_id": "n1", "node": {"type": "card", "title": "Fail"}}],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"


class TestCreateNodesBatchToolConcurrency:
    def test_two_batches_same_version(self, TestSession, db, user, board):
        """Primero funciona, segundo obtiene VersionConflict."""
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        first = call_tool(
            "create_nodes_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            nodes=[{"client_id": "ganador", "node": {"type": "card", "title": "Ganador"}}],
        )
        assert first["ok"] is True
        assert first["data"]["board_version"] == 2

        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_nodes_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                nodes=[{"client_id": "perdedor", "node": {"type": "card", "title": "Perdedor"}}],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"

        db.expire_all()
        nodes = db.query(Node).filter(Node.board_id == board.id).all()
        assert len(nodes) == 1
        assert nodes[0].title == "Ganador"
        assert db.get(Board, board.id).version == 2


class TestCreateEdgesBatchToolSuccess:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("create_edges_batch") == 1

    def test_batch_single_edge(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }},
            ],
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["created_count"] == 1
        assert data["previous_version"] == 1
        assert data["board_version"] == 2
        assert data["created"]["e1"] is not None
        assert data["edges"][0]["client_id"] == "e1"
        assert data["edges"][0]["edge"]["from"]["nodeId"] == "edge-n1"

    def test_batch_multiple_edges(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "a", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "A",
                }},
                {"client_id": "b", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "B",
                }},
                {"client_id": "c", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "C",
                }},
            ],
        )
        data = result["data"]
        assert data["created_count"] == 3
        assert [e["edge"]["label"] for e in data["edges"]] == ["A", "B", "C"]
        assert list(data["created"].keys()) == ["a", "b", "c"]

    def test_batch_self_edge(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "self", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n1", "portId": "out"},
                }},
            ],
        )
        assert result["ok"] is True
        assert result["data"]["created_count"] == 1

    def test_batch_duplicates_allowed(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "a", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "dup",
                }},
                {"client_id": "b", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "dup",
                }},
            ],
        )
        assert result["ok"] is True
        assert result["data"]["created_count"] == 2

    def test_client_id_map_correct(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }},
            ],
        )
        real_id = result["data"]["created"]["e1"]
        assert real_id != "e1"
        assert len(real_id) == 32
        assert result["data"]["edges"][0]["edge"]["id"] == real_id

    def test_curved_true(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "curved": True,
                }},
            ],
        )
        assert result["data"]["edges"][0]["edge"]["curved"] is True

    def test_curved_false(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "curved": False,
                }},
            ],
        )
        assert result["data"]["edges"][0]["edge"]["curved"] is False

    def test_preserves_order(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "z", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "Z",
                }},
                {"client_id": "a", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "A",
                }},
            ],
        )
        assert [e["edge"]["label"] for e in result["data"]["edges"]] == ["Z", "A"]

    def test_version_increments_once(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "a", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }},
                {"client_id": "b", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }},
            ],
        )
        db.expire_all()
        assert db.get(Board, board.id).version == 2

    def test_body_shape(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "x", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }},
            ],
        )
        assert set(result.keys()) == {"ok", "data"}
        data = result["data"]
        assert "edges" in data
        assert "created" in data
        assert "created_count" in data
        assert "previous_version" in data
        assert "board_version" in data
        assert all(k in data["edges"][0] for k in ("client_id", "edge"))


class TestCreateEdgesBatchToolScopes:
    def test_edges_create_allows(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "e1", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            }}],
        )
        assert result["ok"] is True

    def test_edges_read_does_not_allow(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:read"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_edges_update_does_not_allow(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:update"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_nodes_create_does_not_allow(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_no_context_fails(self, TestSession, board_with_two_nodes):
        with pytest.raises(RuntimeError):
            call_tool_without_context(
                "create_edges_batch",
                TestSession,
                board_id=board_with_two_nodes.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )


class TestCreateEdgesBatchToolConstraints:
    def test_board_ids_allows(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"],
                         constraints={"board_ids": [board.id]})
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "e1", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            }}],
        )
        assert result["ok"] is True

    def test_board_ids_denies(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"],
                         constraints={"board_ids": ["other-board"]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_studio_ids_allows(self, TestSession, db, user, studio, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"],
                         constraints={"studio_ids": [studio.id]})
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "e1", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            }}],
        )
        assert result["ok"] is True

    def test_studio_ids_denies(self, TestSession, db, user, studio, other_studio, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"],
                         constraints={"studio_ids": [other_studio.id]})
        with pytest.raises(ConstraintViolation):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_foreign_board_fails(self, TestSession, db, user, other_board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError, match="Tablero no encontrado"):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=other_board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_without_constraints_works(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"], constraints=None)
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "e1", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            }}],
        )
        assert result["ok"] is True


class TestCreateEdgesBatchToolLimits:
    def test_empty_list_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[],
            )

    def test_200_ok(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        # Need at least 1 node for all edges to reference
        n1 = Node(id="batch-n1", board_id=board.id, title="N1")
        n2 = Node(id="batch-n2", board_id=board.id, title="N2")
        db.add_all([n1, n2])
        db.commit()
        db.refresh(board)
        edges = [
            {"client_id": f"e{i:03d}", "edge": {
                "from": {"nodeId": "batch-n1", "portId": "p"},
                "to": {"nodeId": "batch-n2", "portId": "p"},
            }}
            for i in range(200)
        ]
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=edges,
        )
        assert result["ok"] is True
        assert result["data"]["created_count"] == 200

    def test_201_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        edges = [
            {"client_id": f"e{i:03d}", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            }}
            for i in range(201)
        ]
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=edges,
            )


class TestCreateEdgesBatchToolClientId:
    def test_required(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_empty_string_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_duplicate_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[
                    {"client_id": "dup", "edge": {
                        "from": {"nodeId": "edge-n1", "portId": "out"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                    {"client_id": "dup", "edge": {
                        "from": {"nodeId": "edge-n1", "portId": "out"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                ],
            )
        assert "duplicado" in str(exc.value)

    def test_not_persisted_as_id(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "my-ref", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            }}],
        )
        real_id = result["data"]["created"]["my-ref"]
        edge = db.get(Edge, real_id)
        assert edge is not None
        assert edge.id == real_id  # client_id no es el ID


class TestCreateEdgesBatchToolNodeValidation:
    def test_source_node_nonexistent(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "no-such-node", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_target_node_nonexistent(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "no-such-node", "portId": "in"},
                }}],
            )

    def test_node_from_other_board(self, TestSession, db, user, board):
        # Create a second board with no nodes, then try to use nodes from
        # the first board via create_edges_batch
        from app.models import Board as BoardModel, Studio as StudioModel
        import uuid
        studio = db.get(StudioModel, board.studio_id)
        b2_id = uuid.uuid4().hex[:16]
        b2 = BoardModel(id=b2_id, name="B2", studio_id=studio.id)
        db.add(b2)
        db.commit()
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=b2.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_self_edge_allowed(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "self", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n1", "portId": "out"},
            }}],
        )
        assert result["ok"] is True

    def test_all_ids_valid(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[
                {"client_id": "a", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }},
                {"client_id": "b", "edge": {
                    "from": {"nodeId": "edge-n2", "portId": "in"},
                    "to": {"nodeId": "edge-n1", "portId": "out"},
                }},
            ],
        )
        assert result["data"]["created_count"] == 2


class TestCreateEdgesBatchToolPortValidation:
    def test_valid_ports(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "e1", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
            }}],
        )
        assert result["ok"] is True

    def test_invalid_source_port_fails(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "nonexistent"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_invalid_target_port_fails(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "nonexistent"},
                }}],
            )

    def test_node_without_ports_skips_validation(self, TestSession, db, user, board):
        # Nodes without ports defined should skip port validation
        n1 = Node(id="no-port-1", board_id=board.id, title="NoPort1")
        n2 = Node(id="no-port-2", board_id=board.id, title="NoPort2")
        db.add_all([n1, n2])
        db.commit()
        db.refresh(board)
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        result = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "e1", "edge": {
                "from": {"nodeId": "no-port-1", "portId": "any-port"},
                "to": {"nodeId": "no-port-2", "portId": "any-port"},
            }}],
        )
        assert result["ok"] is True

    def test_invalid_edge_in_middle_reverts_all(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[
                    {"client_id": "a", "edge": {
                        "from": {"nodeId": "edge-n1", "portId": "out"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                    {"client_id": "bad", "edge": {
                        "from": {"nodeId": "edge-n1", "portId": "nonexistent"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                    {"client_id": "c", "edge": {
                        "from": {"nodeId": "edge-n1", "portId": "out"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                ],
            )
        db.expire_all()
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == 0
        assert db.get(Board, board.id).version == 1


class TestCreateEdgesBatchToolValidation:
    def test_extra_fields_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "extra_field": "nope",
                }}],
            )

    def test_extra_fields_in_item_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }, "extra": "nope"}],
            )

    def test_missing_from_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )

    def test_missing_to_rejected(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                }}],
            )

    def test_wrong_version_fails_without_creating_anything(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=99,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"
        db.expire_all()
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == 0
        assert db.get(Board, board.id).version == 1


class TestCreateEdgesBatchToolIntegrity:
    def test_failure_creates_nothing(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[
                    {"client_id": "a", "edge": {
                        "from": {"nodeId": "edge-n1", "portId": "out"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                    {"client_id": "bad", "edge": {
                        "from": {"nodeId": "no-such", "portId": "x"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                ],
            )
        db.expire_all()
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == 0
        assert db.get(Board, board.id).version == 1

    def test_does_not_affect_existing_edges(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        # Create an existing edge first
        existing_ctx = _make_ctx(user.id, scopes=["edges:create"])
        existing = call_tool(
            "create_edge",
            existing_ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edge={
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "existing",
            },
        )
        existing_id = existing["data"]["edge"]["id"]
        before_edges = db.query(Edge).filter(Edge.board_id == board.id).count()

        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError):
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=2,
                edges=[
                    {"client_id": "bad", "edge": {
                        "from": {"nodeId": "no-such", "portId": "x"},
                        "to": {"nodeId": "edge-n2", "portId": "in"},
                    }},
                ],
            )
        db.expire_all()
        assert db.query(Edge).filter(Edge.board_id == board.id).count() == before_edges
        assert db.get(Edge, existing_id) is not None


class TestCreateEdgesBatchToolVersioning:
    def test_old_version_fails(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=0,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"

    def test_future_version_fails(self, TestSession, db, user, board_with_two_nodes):
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=9,
                edges=[{"client_id": "e1", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                }}],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"


class TestCreateEdgesBatchToolConcurrency:
    def test_two_batches_same_version(self, TestSession, db, user, board_with_two_nodes):
        """Primero funciona, segundo obtiene VersionConflict."""
        board = board_with_two_nodes
        ctx = _make_ctx(user.id, scopes=["edges:create"])
        first = call_tool(
            "create_edges_batch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            edges=[{"client_id": "ganador", "edge": {
                "from": {"nodeId": "edge-n1", "portId": "out"},
                "to": {"nodeId": "edge-n2", "portId": "in"},
                "label": "Ganador",
            }}],
        )
        assert first["ok"] is True
        assert first["data"]["board_version"] == 2

        with pytest.raises(ValueError) as exc:
            call_tool(
                "create_edges_batch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                edges=[{"client_id": "perdedor", "edge": {
                    "from": {"nodeId": "edge-n1", "portId": "out"},
                    "to": {"nodeId": "edge-n2", "portId": "in"},
                    "label": "Perdedor",
                }}],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "VERSION_CONFLICT"

        db.expire_all()
        edges = db.query(Edge).filter(Edge.board_id == board.id).all()
        assert len(edges) == 1
        assert edges[0].label == "Ganador"
        assert db.get(Board, board.id).version == 2


class TestApplyBoardPatchTool:
    def test_tool_appears_once_in_registry(self):
        mcp = _build_mcp()
        tool_names = [tool.name for tool in mcp._tool_manager.list_tools()]
        assert tool_names.count("apply_board_patch") == 1

    def test_dry_run_create_node(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        result = call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Nuevo", "x": 100, "y": 200}},
            ],
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["dry_run"] is True
        assert data["valid"] is True
        assert data["current_version"] == 1
        assert data["predicted_version"] == 2
        assert data["operation_count"] == 1
        assert data["summary"]["nodes_created"] == 1
        assert "n1" in data["client_references"]
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 0
        assert db.get(Board, board.id).version == 1

    def test_dry_run_mixed_operations(self, TestSession, db, user, board):
        # Create a node first to be updated/moved
        n1 = Node(id="existing-node", board_id=board.id, title="Existente",
                  x=10, y=20, ports=[{"id": "out", "side": "right",
                                       "color": "#60A5FA", "label": ""}])
        n2 = Node(id="other-node", board_id=board.id, title="Otro", x=100, y=20)
        db.add_all([n1, n2])
        db.commit()
        db.refresh(board)

        from app.services.edges import create_edge as ce
        from app.schemas import EdgeSchema, PortRef
        ce(db, user.id, board.id, EdgeSchema(id="exist-edge",
            from_=PortRef(nodeId="existing-node", portId="out"),
            to=PortRef(nodeId="other-node", portId="p")),
            expected_version=1, board=board)
        db.expire_all()
        db.refresh(board)  # version is now 2

        ctx = _make_ctx(user.id, scopes=["nodes:create", "nodes:update", "edges:create", "edges:update"])
        result = call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=2,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "new-n",
                 "node": {"type": "card", "title": "N", "x": 0, "y": 0}},
                {"op": "update_node", "node_id": "existing-node",
                 "changes": {"title": "Actualizado"}},
                {"op": "move_node", "node_id": "other-node", "x": 500, "y": 300},
                {"op": "create_edge", "client_id": "new-e",
                 "edge": {
                     "from": {"nodeId": "existing-node", "portId": "out"},
                     "to": {"clientId": "new-n", "portId": "p"},
                 }},
                {"op": "update_edge", "edge_id": "exist-edge",
                 "changes": {"label": "modificado"}},
            ],
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["valid"] is True
        assert data["summary"] == {
            "nodes_created": 1, "nodes_updated": 1, "nodes_moved": 1,
            "edges_created": 1, "edges_updated": 1,
        }
        assert len(data["operations"]) == 5
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 2
        assert db.get(Board, board.id).version == 2

    def test_execute_simple_patch(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])
        result = call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=False,
            idempotency_key="patch-tool-001",
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Ejecutado", "x": 100, "y": 200}},
            ],
        )
        assert result["ok"] is True
        data = result["data"]
        assert data["dry_run"] is False
        assert data["applied"] is True
        assert data["previous_version"] == 1
        assert data["board_version"] == 2
        assert data["operation_count"] == 1
        assert data["summary"]["nodes_created"] == 1
        assert "n1" in data["created"]
        assert data["created"]["n1"]["resource_type"] == "node"
        assert data["created"]["n1"]["id"] is not None
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 1
        assert db.get(Board, board.id).version == 2

    def test_execute_requires_idempotency_key(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError, match="idempotency_key es obligatoria"):
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                dry_run=False,
                operations=[
                    {"op": "create_node", "client_id": "n1",
                     "node": {"type": "card", "title": "Ejecutado"}},
                ],
            )

    def test_dry_run_rejects_idempotency_key(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        with pytest.raises(ValueError, match="no está permitida"):
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                dry_run=True,
                idempotency_key="patch-tool-dryrun",
                operations=[
                    {"op": "create_node", "client_id": "n1",
                     "node": {"type": "card", "title": "Nope"}},
                ],
            )

    def test_replay_returns_same_response_and_does_not_duplicate(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])
        params = {
            "board_id": board.id,
            "expected_version": 1,
            "dry_run": False,
            "idempotency_key": "patch-tool-002",
            "operations": [
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Replay", "x": 50, "y": 60}},
            ],
        }
        first = call_tool("apply_board_patch", ctx, TestSession, **params)
        replay = call_tool("apply_board_patch", ctx, TestSession, **params)
        assert replay == first
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 1
        assert db.get(Board, board.id).version == 2

    def test_same_key_different_payload_returns_conflict(self, TestSession, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        db = TestSession()
        try:
            _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])
        finally:
            db.close()
        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=False,
            idempotency_key="patch-tool-003",
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Uno"}},
            ],
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=2,
                dry_run=False,
                idempotency_key="patch-tool-003",
                operations=[
                    {"op": "create_node", "client_id": "n1",
                     "node": {"type": "card", "title": "Dos"}},
                ],
            )
        payload = json.loads(str(exc.value))
        assert payload["code"] == "IDEMPOTENCY_CONFLICT"

    def test_in_progress_returns_structured_error(self, tmp_path, monkeypatch):
        import app.services.board_patches as board_patches_module
        import threading
        import time

        engine = create_engine(
            f"sqlite:///{tmp_path / 'patch-tool-in-progress.db'}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_fk(dbapi_conn, _):
            try:
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
            except Exception:
                pass

        Base.metadata.create_all(bind=engine)
        TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db = TestSession()
        user = User(
            id=uuid.uuid4().hex[:16],
            email="patchtool@test.com",
            name="Patch Tool",
            auth_provider="google",
        )
        studio = Studio(
            id=uuid.uuid4().hex[:16],
            name="Studio",
            color="azul",
            user_id=user.id,
        )
        board = Board(
            id=uuid.uuid4().hex[:16],
            name="Board",
            studio_id=studio.id,
            version=1,
        )
        db.add_all([user, studio, board])
        db.commit()
        board_id = board.id

        original_execute = board_patches_module.execute_board_patch

        def slow_execute(*args, **kwargs):
            time.sleep(0.05)
            return original_execute(*args, **kwargs)

        monkeypatch.setattr(board_patches_module, "execute_board_patch", slow_execute)

        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        try:
            _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])
        finally:
            db.close()
        barrier = threading.Barrier(2)
        results: list[dict] = []
        failures: list[dict] = []

        def worker():
            try:
                barrier.wait()
                results.append(
                    call_tool(
                        "apply_board_patch",
                        ctx,
                        TestSession,
                        board_id=board_id,
                        expected_version=1,
                        dry_run=False,
                        idempotency_key="patch-tool-004",
                        operations=[
                            {"op": "create_node", "client_id": "n1",
                             "node": {"type": "card", "title": "Lento"}},
                        ],
                    )
                )
            except ValueError as exc:
                failures.append(json.loads(str(exc)))

        thread_a = threading.Thread(target=worker)
        thread_b = threading.Thread(target=worker)
        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        assert len(results) == 1
        assert len(failures) == 1
        assert failures[0]["code"] == "IDEMPOTENCY_IN_PROGRESS"
        engine.dispose()

    def test_no_mutation_after_dry_run(self, TestSession, db, user, board):
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Nunca persistir"}},
            ],
        )
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 0
        assert db.get(Node, "n1") is None
        assert db.get(Board, board.id).version == 1

    def test_rate_limit_rejects_after_exhausting_quota(self, TestSession, db, user, board, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "2")
        mcp_rate_limit.clear_default_rate_limiter()
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])

        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Uno"}},
            ],
        )
        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n2",
                 "node": {"type": "card", "title": "Dos"}},
            ],
        )
        with pytest.raises(ValueError) as exc:
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                dry_run=True,
                operations=[
                    {"op": "create_node", "client_id": "n3",
                     "node": {"type": "card", "title": "Tres"}},
                ],
            )

        payload = json.loads(str(exc.value))
        assert payload["code"] == "RATE_LIMIT_EXCEEDED"
        assert payload["limit"] == 2
        assert payload["window_seconds"] == 60
        assert payload["retry_after_seconds"] == 30
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 0
        assert db.get(Board, board.id).version == 1

    def test_dry_run_consumes_and_audits_rate_limit(self, TestSession, db, user, board, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "1")
        mcp_rate_limit.clear_default_rate_limiter()
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])

        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Uno"}},
            ],
        )
        with pytest.raises(ValueError):
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                dry_run=True,
                operations=[
                    {"op": "create_node", "client_id": "n2",
                     "node": {"type": "card", "title": "Dos"}},
                ],
            )

        db.expire_all()
        audits = db.query(MCPAuditLog).order_by(MCPAuditLog.created_at.asc()).all()
        assert [item.status for item in audits] == ["success", "error"]
        assert audits[1].error_code == "RATE_LIMIT_EXCEEDED"
        assert audits[1].affected_count == 0
        assert audits[1].metadata_json == {
            "limit": 1,
            "window_seconds": 60,
            "retry_after_seconds": 60,
        }

    def test_execution_replay_and_conflict_each_consume_quota(self, TestSession, db, user, board, monkeypatch):
        clock = _FakeMonotonicClock()
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "3")
        mcp_rate_limit.configure_default_rate_limiter(
            settings=mcp_rate_limit.load_mcp_rate_limit_settings(),
            clock=clock,
        )
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])
        params = {
            "board_id": board.id,
            "expected_version": 1,
            "dry_run": False,
            "idempotency_key": "patch-tool-rate-001",
            "operations": [
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Uno"}},
            ],
        }

        call_tool("apply_board_patch", ctx, TestSession, **params)
        call_tool("apply_board_patch", ctx, TestSession, **params)
        with pytest.raises(ValueError) as exc:
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=2,
                dry_run=False,
                idempotency_key="patch-tool-rate-001",
                operations=[
                    {"op": "create_node", "client_id": "n1",
                     "node": {"type": "card", "title": "Dos"}},
                ],
            )

        assert json.loads(str(exc.value))["code"] == "IDEMPOTENCY_CONFLICT"
        with pytest.raises(ValueError) as rate_exc:
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=2,
                dry_run=False,
                idempotency_key="patch-tool-rate-002",
                operations=[
                    {"op": "create_node", "client_id": "n2",
                     "node": {"type": "card", "title": "Tres"}},
                ],
            )

        assert json.loads(str(rate_exc.value))["code"] == "RATE_LIMIT_EXCEEDED"
        db.expire_all()
        assert db.query(Node).filter(Node.board_id == board.id).count() == 1

    def test_rate_limit_happens_before_idempotency_reservation(self, TestSession, db, user, board, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "1")
        mcp_rate_limit.clear_default_rate_limiter()
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])

        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n0",
                 "node": {"type": "card", "title": "Consume"}},
            ],
        )

        with pytest.raises(ValueError, match="RATE_LIMIT_EXCEEDED"):
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                dry_run=False,
                idempotency_key="patch-tool-rate-limit-before-idem",
                operations=[
                    {"op": "create_node", "client_id": "n1",
                     "node": {"type": "card", "title": "No reserva"}},
                ],
            )

        db.expire_all()
        records = db.query(MCPIdempotencyRecord).all()
        assert records == []

    def test_rate_limit_refill_allows_new_request(self, TestSession, db, user, board, monkeypatch):
        clock = _FakeMonotonicClock()
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "1")
        mcp_rate_limit.configure_default_rate_limiter(
            settings=mcp_rate_limit.load_mcp_rate_limit_settings(),
            clock=clock,
        )
        ctx = _make_ctx(user.id, scopes=["nodes:create"])
        _persist_mcp_token(db, user, ctx.token_id, ["nodes:create"])

        call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "Uno"}},
            ],
        )
        with pytest.raises(ValueError):
            call_tool(
                "apply_board_patch",
                ctx,
                TestSession,
                board_id=board.id,
                expected_version=1,
                dry_run=True,
                operations=[
                    {"op": "create_node", "client_id": "n2",
                     "node": {"type": "card", "title": "Dos"}},
                ],
            )

        clock.advance(60)
        result = call_tool(
            "apply_board_patch",
            ctx,
            TestSession,
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": "n3",
                 "node": {"type": "card", "title": "Tres"}},
            ],
        )

        assert result["ok"] is True

    def test_scope_required(self, TestSession, db, user, board):
        only_read = _make_ctx(user.id, scopes=["nodes:read"])
        with pytest.raises(InsufficientScope):
            call_tool(
                "apply_board_patch",
                only_read,
                TestSession,
                board_id=board.id,
                expected_version=1,
                dry_run=True,
                operations=[
                    {"op": "create_node", "client_id": "n1",
                     "node": {"type": "card"}},
                ],
            )

    def test_no_context_fails(self, TestSession):
        with pytest.raises(RuntimeError):
            call_tool_without_context(
                "apply_board_patch",
                TestSession,
                board_id="x",
                expected_version=1,
                dry_run=True,
                operations=[
                    {"op": "create_node", "client_id": "n1", "node": {"type": "card"}},
                ],
            )
