"""Tests unitarios para helpers MCP de escritura."""

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.mcp.auth import _now
from app.mcp.context import MCPContext
from app.mcp.errors import ConstraintViolation, InsufficientScope
from app.mcp.write_helpers import (
    build_success,
    load_board,
    load_node_with_board,
    map_domain_error,
    require_board_scope,
    require_node_scope,
    require_scope,
    reraise_domain_errors,
    resolve_expected_version,
)
from app.models import Board, Node, Studio, User
from app.services.errors import (
    ForbiddenResource,
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStateUncertain,
    RateLimitExceeded,
    ResourceNotFound,
    ValidationFailure,
    VersionConflict,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


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
def board(db, studio) -> Board:
    board = Board(
        id=uuid.uuid4().hex[:16],
        name="Board",
        studio_id=studio.id,
        version=7,
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


@pytest.fixture()
def other_board(db, other_studio) -> Board:
    board = Board(
        id=uuid.uuid4().hex[:16],
        name="Other Board",
        studio_id=other_studio.id,
        version=3,
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


@pytest.fixture()
def node(db, board) -> Node:
    node = Node(
        id=uuid.uuid4().hex[:16],
        board_id=board.id,
        title="Node",
        ports=[],
        blocks=[],
        stages=[],
        tags=[],
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


@pytest.fixture()
def other_node(db, other_board) -> Node:
    node = Node(
        id=uuid.uuid4().hex[:16],
        board_id=other_board.id,
        title="Other Node",
        ports=[],
        blocks=[],
        stages=[],
        tags=[],
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def _ctx(
    user_id: str,
    scopes: list[str] | None = None,
    constraints: dict[str, list[str]] | None = None,
) -> MCPContext:
    now = _now()
    return MCPContext(
        user_id=user_id,
        token_id=uuid.uuid4().hex[:16],
        scopes=frozenset(scopes or ["boards:write"]),
        constraints=constraints,
        token_prefix="huginn_mcp_test",
        expires_at=now + timedelta(days=30),
    )


class TestRequireScope:
    def test_require_scope_allows(self, user):
        ctx = _ctx(user.id, scopes=["boards:write"])
        returned = require_scope(ctx, "boards:write")
        assert returned is ctx

    def test_require_scope_missing_authentication(self):
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            require_scope(None, "boards:write")

    def test_require_scope_insufficient(self, user):
        ctx = _ctx(user.id, scopes=["boards:read"])
        with pytest.raises(InsufficientScope):
            require_scope(ctx, "boards:write")


class TestRequireBoardScope:
    def test_require_board_scope_loads_board(self, db, user, board):
        ctx = _ctx(user.id, scopes=["boards:write"])
        loaded = require_board_scope(db, ctx, board.id, "boards:write")
        assert loaded.id == board.id

    def test_require_board_scope_rejects_constraint(self, db, user, board):
        ctx = _ctx(
            user.id,
            scopes=["boards:write"],
            constraints={"board_ids": []},
        )
        with pytest.raises(ConstraintViolation):
            require_board_scope(db, ctx, board.id, "boards:write")

    def test_load_board_other_user_fails_as_not_found(self, db, user, other_board):
        ctx = _ctx(user.id, scopes=["boards:write"])
        with pytest.raises(ResourceNotFound):
            load_board(db, ctx, other_board.id)


class TestRequireNodeScope:
    def test_require_node_scope_loads_node_and_board(self, db, user, board, node):
        ctx = _ctx(user.id, scopes=["nodes:update"])
        loaded_node, loaded_board = require_node_scope(
            db, ctx, node.id, "nodes:update"
        )
        assert loaded_node.id == node.id
        assert loaded_board.id == board.id

    def test_require_node_scope_missing_authentication(self, db, node):
        with pytest.raises(RuntimeError, match="No hay contexto MCP disponible"):
            require_node_scope(db, None, node.id, "nodes:update")

    def test_require_node_scope_insufficient_scope(self, db, user, node):
        ctx = _ctx(user.id, scopes=["nodes:read"])
        with pytest.raises(InsufficientScope):
            require_node_scope(db, ctx, node.id, "nodes:update")

    def test_require_node_scope_rejects_constraint(self, db, user, node):
        ctx = _ctx(
            user.id,
            scopes=["nodes:update"],
            constraints={"board_ids": []},
        )
        with pytest.raises(ConstraintViolation):
            require_node_scope(db, ctx, node.id, "nodes:update")

    def test_load_node_with_board_other_user_fails_as_not_found(self, db, user, other_node):
        ctx = _ctx(user.id, scopes=["nodes:update"])
        with pytest.raises(ResourceNotFound):
            load_node_with_board(db, ctx, other_node.id)


class TestResolveExpectedVersion:
    def test_expected_version_omitted_uses_current(self, board):
        assert resolve_expected_version(board, None) == board.version

    def test_expected_version_correct(self, board):
        assert resolve_expected_version(board, board.version) == board.version

    def test_expected_version_incorrect(self, board):
        with pytest.raises(VersionConflict) as exc:
            resolve_expected_version(board, board.version + 1)
        assert exc.value.expected_version == board.version + 1
        assert exc.value.current_version == board.version


class TestMapDomainError:
    def test_resource_not_found_maps_uniformly(self):
        error = map_domain_error(ResourceNotFound("Board", "b1", "Tablero no encontrado"))
        assert isinstance(error, ValueError)
        assert str(error) == "Tablero no encontrado"

    def test_forbidden_resource_maps_uniformly(self):
        error = map_domain_error(ForbiddenResource("Board", "b1", "Acceso denegado"))
        assert isinstance(error, ValueError)
        assert str(error) == "Acceso denegado"

    def test_validation_failure_maps_uniformly(self):
        error = map_domain_error(ValidationFailure("Payload inválido"))
        assert isinstance(error, ValueError)
        assert str(error) == "Payload inválido"

    def test_version_conflict_maps_uniformly(self):
        error = map_domain_error(
            VersionConflict("b1", expected_version=3, current_version=5)
        )
        assert isinstance(error, ValueError)
        payload = json.loads(str(error))
        assert payload["code"] == "VERSION_CONFLICT"
        assert payload["expected_version"] == 3
        assert payload["current_version"] == 5

    def test_idempotency_conflict_maps_uniformly(self):
        error = map_domain_error(
            IdempotencyConflict(
                tool_name="apply_board_patch",
                idempotency_key="idem-key-01",
            )
        )
        payload = json.loads(str(error))
        assert payload["code"] == "IDEMPOTENCY_CONFLICT"
        assert payload["idempotency_key"] == "idem-key-01"

    def test_idempotency_in_progress_maps_uniformly(self):
        error = map_domain_error(
            IdempotencyInProgress(
                tool_name="apply_board_patch",
                idempotency_key="idem-key-02",
            )
        )
        payload = json.loads(str(error))
        assert payload["code"] == "IDEMPOTENCY_IN_PROGRESS"
        assert payload["idempotency_key"] == "idem-key-02"

    def test_idempotency_state_uncertain_maps_uniformly(self):
        error = map_domain_error(
            IdempotencyStateUncertain(
                tool_name="apply_board_patch",
                idempotency_key="idem-key-uncertain",
            )
        )
        payload = json.loads(str(error))
        assert payload["code"] == "IDEMPOTENCY_STATE_UNCERTAIN"
        assert payload["idempotency_key"] == "idem-key-uncertain"

    def test_rate_limit_exceeded_maps_uniformly(self):
        error = map_domain_error(
            RateLimitExceeded(
                tool_name="apply_board_patch",
                limit=10,
                window_seconds=60,
                retry_after_seconds=12,
            )
        )
        payload = json.loads(str(error))
        assert payload["code"] == "RATE_LIMIT_EXCEEDED"
        assert payload["retry_after_seconds"] == 12
        assert payload["limit"] == 10
        assert payload["window_seconds"] == 60


class TestBuildSuccess:
    def test_build_success_uses_homogeneous_shape(self):
        result = build_success(board_id="b1", version=8)
        assert result == {"ok": True, "board_id": "b1", "version": 8}


class TestReraiseDomainErrors:
    def test_reraises_supported_domain_error(self):
        with pytest.raises(ValueError, match="Tablero no encontrado"):
            with reraise_domain_errors():
                raise ResourceNotFound("Board", "b1", "Tablero no encontrado")

    def test_unexpected_error_is_not_captured(self):
        with pytest.raises(RuntimeError, match="boom"):
            with reraise_domain_errors():
                raise RuntimeError("boom")

    def test_reraises_idempotency_conflict(self):
        with pytest.raises(ValueError, match="IDEMPOTENCY_CONFLICT"):
            with reraise_domain_errors():
                raise IdempotencyConflict(
                    tool_name="apply_board_patch",
                    idempotency_key="idem-key-03",
                )

    def test_reraises_rate_limit_exceeded(self):
        with pytest.raises(ValueError, match="RATE_LIMIT_EXCEEDED"):
            with reraise_domain_errors():
                raise RateLimitExceeded(
                    tool_name="apply_board_patch",
                    limit=10,
                    window_seconds=60,
                    retry_after_seconds=7,
                )
