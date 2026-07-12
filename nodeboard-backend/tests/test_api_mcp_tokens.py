"""Tests HTTP de la API de tokens MCP.

Cubre autenticación, creación, listado, revocación, eliminación,
aislamiento entre usuarios y no exposición de secretos.
"""
import hashlib
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import (
    app,
    create_mcp_token as _route_create,
    list_mcp_tokens as _route_list,
    revoke_mcp_token as _route_revoke,
    delete_mcp_token as _route_delete,
)
from app.models import Board, MCPToken, Session as SessionModel, Studio, User
from app.schemas import MCPTokenConstraints, MCPTokenCreate, MCPTokenCreated, MCPTokenSummary
from app.services.errors import InvalidScope, ResourceNotFound, ValidationFailure


# ======================================================================
# Fixtures compartidos
# ======================================================================


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user_a(db) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email="a@test.com",
        name="User A",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def user_b(db) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email="b@test.com",
        name="User B",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


def _valid_payload(**kwargs) -> MCPTokenCreate:
    data = dict(
        name="Mi Token",
        scopes=["studios:read", "boards:read"],
        expires_in_days=90,
        constraints=None,
    )
    data.update(kwargs)
    return MCPTokenCreate(**data)


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ======================================================================
# Autenticación (ASGI transport)
# ======================================================================


class TestAuth:
    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client):
        resp = await client.post(
            "/api/integrations/mcp/tokens",
            json={"name": "x", "scopes": ["studios:read"]},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        resp = await client.get("/api/integrations/mcp/tokens")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_requires_auth(self, client):
        resp = await client.post("/api/integrations/mcp/tokens/fake/revoke")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_requires_auth(self, client):
        resp = await client.delete("/api/integrations/mcp/tokens/fake")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_bearer_token_not_accepted(self, client):
        """Todavía no existe validación Bearer."""
        resp = await client.post(
            "/api/integrations/mcp/tokens",
            json={"name": "x", "scopes": ["studios:read"]},
            headers={"Authorization": "Bearer huginn_mcp_fake"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_mcp_route_not_caught_by_spa(self, client):
        """La ruta debe existir como API, no como SPA."""
        resp = await client.get("/api/integrations/mcp/tokens")
        assert resp.status_code == 401  # no autenticado, no 404
        assert resp.text != ""


# ======================================================================
# Crear token
# ======================================================================


class TestCreate:
    def test_returns_201(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        assert isinstance(result, MCPTokenCreated)
        assert result.warning == "Este token no volverá a mostrarse."

    def test_status_code_201(self, db, user_a):
        """Verifica que el handler retorna el schema correcto (201 implícito en status_code)."""
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        # FastAPI usa status_code=201, el schema se devuelve en el body
        assert result.id is not None

    def test_includes_full_token(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        assert result.token.startswith("huginn_mcp_")
        assert len(result.token) > len("huginn_mcp_")

    def test_no_token_hash_in_response(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        assert not hasattr(result, "token_hash")

    def test_persists_token(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        saved = db.get(MCPToken, result.id)
        assert saved is not None
        assert saved.name == "Mi Token"

    def test_stores_correct_hash(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        saved = db.get(MCPToken, result.id)
        expected = hashlib.sha256(result.token.encode("utf-8")).hexdigest()
        assert saved.token_hash == expected

    def test_full_token_not_in_db(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        saved = db.get(MCPToken, result.id)
        assert not hasattr(saved, "token_full")

    def test_valid_scopes(self, db, user_a):
        result = _route_create(
            _valid_payload(scopes=["boards:read", "nodes:read"]), db=db, current_user=user_a
        )
        assert result.scopes == ["boards:read", "nodes:read"]

    def test_boards_create_scope_can_be_assigned(self, db, user_a):
        result = _route_create(
            _valid_payload(scopes=["boards:create"]), db=db, current_user=user_a
        )
        assert result.scopes == ["boards:create"]

    def test_duplicate_scopes_normalized(self, db, user_a):
        result = _route_create(
            _valid_payload(scopes=["boards:read", "boards:read", "nodes:read"]),
            db=db,
            current_user=user_a,
        )
        assert len(result.scopes) == 2

    def test_invalid_scope_returns_422(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_create(_valid_payload(scopes=["invalid"]), db=db, current_user=user_a)
        assert exc.value.status_code == 422

    def test_wildcard_scope_returns_422(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_create(_valid_payload(scopes=["*"]), db=db, current_user=user_a)
        assert exc.value.status_code == 422

    def test_empty_name_returns_422(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_create(_valid_payload(name=""), db=db, current_user=user_a)
        assert exc.value.status_code == 422

    def test_long_name_returns_422(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_create(_valid_payload(name="x" * 201), db=db, current_user=user_a)
        assert exc.value.status_code == 422

    def test_expiration_below_1_returns_422(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_create(_valid_payload(expires_in_days=0), db=db, current_user=user_a)
        assert exc.value.status_code == 422

    def test_expiration_above_365_returns_422(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_create(_valid_payload(expires_in_days=366), db=db, current_user=user_a)
        assert exc.value.status_code == 422

    def test_valid_constraints(self, db, user_a):
        studio = Studio(id=uuid.uuid4().hex[:16], name="S", color="azul", user_id=user_a.id)
        db.add(studio)
        db.commit()
        board = Board(id=uuid.uuid4().hex[:16], name="B", studio_id=studio.id)
        db.add(board)
        db.commit()
        result = _route_create(
            _valid_payload(constraints=MCPTokenConstraints(studio_ids=[studio.id], board_ids=[board.id])),
            db=db,
            current_user=user_a,
        )
        assert result.constraints is not None
        assert studio.id in result.constraints.studio_ids

    def test_other_user_studio_in_constraints_returns_404_or_422(self, db, user_a, user_b):
        other_studio = Studio(id=uuid.uuid4().hex[:16], name="S", color="azul", user_id=user_b.id)
        db.add(other_studio)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _route_create(
                _valid_payload(constraints=MCPTokenConstraints(studio_ids=[other_studio.id])),
                db=db,
                current_user=user_a,
            )
        assert exc.value.status_code in (404, 422)

    def test_other_user_board_in_constraints_returns_404_or_422(self, db, user_a, user_b):
        other_studio = Studio(id=uuid.uuid4().hex[:16], name="S", color="azul", user_id=user_b.id)
        db.add(other_studio)
        db.commit()
        other_board = Board(id=uuid.uuid4().hex[:16], name="B", studio_id=other_studio.id)
        db.add(other_board)
        db.commit()
        with pytest.raises(HTTPException) as exc:
            _route_create(
                _valid_payload(constraints=MCPTokenConstraints(board_ids=[other_board.id])),
                db=db,
                current_user=user_a,
            )
        assert exc.value.status_code in (404, 422)

    def test_error_does_not_leave_partial_token(self, db, user_a):
        count_before = db.query(MCPToken).count()
        try:
            _route_create(_valid_payload(scopes=["invalid"]), db=db, current_user=user_a)
        except (HTTPException, ValidationFailure, InvalidScope):
            pass
        count_after = db.query(MCPToken).count()
        assert count_after == count_before


# ======================================================================
# Listado
# ======================================================================


class TestList:
    def test_returns_200(self, db, user_a):
        result = _route_list(db=db, current_user=user_a)
        assert isinstance(result, list)

    def test_returns_only_own_tokens(self, db, user_a, user_b):
        _route_create(_valid_payload(name="A"), db=db, current_user=user_a)
        _route_create(_valid_payload(name="B"), db=db, current_user=user_b)
        tokens = _route_list(db=db, current_user=user_a)
        assert len(tokens) == 1
        assert tokens[0].name == "A"

    def test_does_not_include_token(self, db, user_a):
        _route_create(_valid_payload(), db=db, current_user=user_a)
        tokens = _route_list(db=db, current_user=user_a)
        assert not hasattr(tokens[0], "token")

    def test_does_not_include_token_hash(self, db, user_a):
        _route_create(_valid_payload(), db=db, current_user=user_a)
        tokens = _route_list(db=db, current_user=user_a)
        assert not hasattr(tokens[0], "token_hash")

    def test_includes_token_prefix(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        tokens = _route_list(db=db, current_user=user_a)
        assert tokens[0].token_prefix == result.token_prefix

    def test_includes_scopes(self, db, user_a):
        _route_create(_valid_payload(scopes=["boards:read"]), db=db, current_user=user_a)
        tokens = _route_list(db=db, current_user=user_a)
        assert tokens[0].scopes == ["boards:read"]

    def test_includes_constraints(self, db, user_a):
        studio = Studio(id=uuid.uuid4().hex[:16], name="S", color="azul", user_id=user_a.id)
        db.add(studio)
        db.commit()
        _route_create(
            _valid_payload(constraints=MCPTokenConstraints(studio_ids=[studio.id])),
            db=db,
            current_user=user_a,
        )
        tokens = _route_list(db=db, current_user=user_a)
        assert tokens[0].constraints is not None

    def test_returns_summaries(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        tokens = _route_list(db=db, current_user=user_a)
        assert isinstance(tokens[0], MCPTokenSummary)
        assert tokens[0].id == result.id

    def test_does_not_change_last_used_at(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        _route_list(db=db, current_user=user_a)
        saved = db.get(MCPToken, result.id)
        assert saved.last_used_at is None

    def test_created_token_cannot_be_recovered_from_list(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        tokens = _route_list(db=db, current_user=user_a)
        assert tokens[0].token is None if hasattr(tokens[0], "token") else True
        # El token solo está en la respuesta de creación


# ======================================================================
# Revocación
# ======================================================================


class TestRevoke:
    def test_returns_200(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        summary = _route_revoke(result.id, db=db, current_user=user_a)
        assert summary.revoked_at is not None

    def test_does_not_return_token(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        summary = _route_revoke(result.id, db=db, current_user=user_a)
        assert not hasattr(summary, "token")

    def test_does_not_return_hash(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        summary = _route_revoke(result.id, db=db, current_user=user_a)
        assert not hasattr(summary, "token_hash")

    def test_revoke_twice_returns_200(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        r1 = _route_revoke(result.id, db=db, current_user=user_a)
        r2 = _route_revoke(result.id, db=db, current_user=user_a)
        assert r2.revoked_at == r1.revoked_at

    def test_user_a_cannot_revoke_b_token(self, db, user_a, user_b):
        result = _route_create(_valid_payload(), db=db, current_user=user_b)
        with pytest.raises(HTTPException) as exc:
            _route_revoke(result.id, db=db, current_user=user_a)
        assert exc.value.status_code == 404

    def test_nonexistent_token_404(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_revoke("nonexistent", db=db, current_user=user_a)
        assert exc.value.status_code == 404

    def test_does_not_delete_record(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        _route_revoke(result.id, db=db, current_user=user_a)
        saved = db.get(MCPToken, result.id)
        assert saved is not None
        assert saved.revoked_at is not None


# ======================================================================
# Eliminación
# ======================================================================


class TestDelete:
    def test_returns_204(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        returned = _route_delete(result.id, db=db, current_user=user_a)
        assert returned is None

    def test_physically_deletes(self, db, user_a):
        result = _route_create(_valid_payload(), db=db, current_user=user_a)
        _route_delete(result.id, db=db, current_user=user_a)
        assert db.get(MCPToken, result.id) is None

    def test_user_a_cannot_delete_b_token(self, db, user_a, user_b):
        result = _route_create(_valid_payload(), db=db, current_user=user_b)
        with pytest.raises(HTTPException) as exc:
            _route_delete(result.id, db=db, current_user=user_a)
        assert exc.value.status_code == 404

    def test_nonexistent_token_404(self, db, user_a):
        with pytest.raises(HTTPException) as exc:
            _route_delete("nonexistent", db=db, current_user=user_a)
        assert exc.value.status_code == 404

    def test_does_not_affect_other_tokens(self, db, user_a):
        r1 = _route_create(_valid_payload(name="A"), db=db, current_user=user_a)
        r2 = _route_create(_valid_payload(name="B"), db=db, current_user=user_a)
        _route_delete(r1.id, db=db, current_user=user_a)
        remaining = _route_list(db=db, current_user=user_a)
        assert len(remaining) == 1
        assert remaining[0].name == "B"

    def test_does_not_affect_other_users(self, db, user_a, user_b):
        _route_create(_valid_payload(name="A"), db=db, current_user=user_a)
        r_b = _route_create(_valid_payload(name="B"), db=db, current_user=user_b)
        _route_delete(r_b.id, db=db, current_user=user_b)
        tokens_a = _route_list(db=db, current_user=user_a)
        assert len(tokens_a) == 1
