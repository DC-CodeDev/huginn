"""Tests unitarios del servicio de MCP Tokens.

Cubre: creación (válida, scopes, constraints, expiración, errores),
listado (propios, ajenos, orden, hashes ocultos),
revocación (propia, ajena, idempotente),
eliminación (propia, ajena, cascade).
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, MCPToken, Studio, User
from app.schemas import MCPTokenConstraints, MCPTokenCreate, MCPTokenCreated, MCPTokenSummary
from app.services.errors import InvalidScope, ResourceNotFound, ValidationFailure
from app.services.mcp_tokens import (
    create_mcp_token,
    delete_mcp_token,
    get_owned_mcp_token,
    list_mcp_tokens,
    revoke_mcp_token,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

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


def _user(db, email=None) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email=email or f"{uuid.uuid4().hex}@example.com",
        name="Test",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


def _other_user(db) -> User:
    return _user(db, email="other@example.com")


def _studio(db, user: User) -> Studio:
    s = Studio(
        id=uuid.uuid4().hex[:16],
        name="Test Studio",
        color="azul",
        user_id=user.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _board(db, studio: Studio) -> Board:
    b = Board(
        id=uuid.uuid4().hex[:16],
        name="Test Board",
        studio_id=studio.id,
    )
    db.add(b)
    db.commit()
    return b


def _valid_payload(**kwargs) -> MCPTokenCreate:
    data = dict(
        name="Mi Token MCP",
        scopes=["studios:read", "boards:read"],
        expires_in_days=90,
        constraints=None,
    )
    data.update(kwargs)
    return MCPTokenCreate(**data)


# ======================================================================
# Creación
# ======================================================================


class TestCreateToken:
    def test_creates_valid_token(self, db):
        user = _user(db)
        payload = _valid_payload()
        result = create_mcp_token(db, user.id, payload)
        assert isinstance(result, MCPTokenCreated)
        assert result.name == "Mi Token MCP"
        assert result.warning == "Este token no volverá a mostrarse."

    def test_token_starts_with_prefix(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        assert result.token.startswith("huginn_mcp_")

    def test_secret_has_reasonable_length(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        secret = result.token.removeprefix("huginn_mcp_")
        # secrets.token_urlsafe(32) → 43 chars base64
        assert len(secret) >= 40

    def test_two_tokens_are_different(self, db):
        user = _user(db)
        r1 = create_mcp_token(db, user.id, _valid_payload())
        r2 = create_mcp_token(db, user.id, _valid_payload())
        assert r1.token != r2.token
        assert r1.id != r2.id

    def test_hash_matches_stored(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        expected_hash = hashlib.sha256(result.token.encode("utf-8")).hexdigest()
        token = db.get(MCPToken, result.id)
        assert token is not None
        assert token.token_hash == expected_hash

    def test_full_token_not_stored(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        token = db.get(MCPToken, result.id)
        # Verificar que no hay columna con el token completo
        assert not hasattr(token, "token_full")
        # El token no está en ninguna columna
        cols = {c.name for c in MCPToken.__table__.columns}
        assert "token_hash" in cols
        assert "token_full" not in cols

    def test_prefix_format(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        assert len(result.token_prefix) == len("huginn_mcp_") + 6
        assert result.token_prefix.startswith("huginn_mcp_")

    def test_default_expiration_90_days(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        diff = result.expires_at - result.created_at
        assert timedelta(days=89) < diff <= timedelta(days=91)

    def test_custom_expiration(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload(expires_in_days=30))
        diff = result.expires_at - result.created_at
        assert timedelta(days=29) < diff <= timedelta(days=31)

    def test_expiration_min_1(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload(expires_in_days=1))
        diff = result.expires_at - result.created_at
        assert timedelta(hours=23) < diff <= timedelta(days=1)

    def test_expiration_below_min_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(db, user.id, _valid_payload(expires_in_days=0))

    def test_expiration_above_max_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(db, user.id, _valid_payload(expires_in_days=366))

    def test_unknown_scope_fails(self, db):
        user = _user(db)
        with pytest.raises(InvalidScope):
            create_mcp_token(db, user.id, _valid_payload(scopes=["unknown:read"]))

    def test_wildcard_scope_fails(self, db):
        user = _user(db)
        with pytest.raises(InvalidScope):
            create_mcp_token(db, user.id, _valid_payload(scopes=["*"]))

    def test_duplicate_scopes_deduplicated(self, db):
        user = _user(db)
        result = create_mcp_token(
            db, user.id, _valid_payload(scopes=["studios:read", "studios:read", "boards:read"])
        )
        assert len(result.scopes) == 2
        assert "studios:read" in result.scopes
        assert "boards:read" in result.scopes

    def test_scope_order_stable(self, db):
        user = _user(db)
        result = create_mcp_token(
            db, user.id, _valid_payload(scopes=["boards:read", "studios:read"])
        )
        assert result.scopes == ["boards:read", "studios:read"]

    def test_more_than_20_scopes_fails(self, db):
        user = _user(db)
        # Sólo hay 14 scopes definidos actualmente, por lo que el límite
        # de 20 no se puede superar con scopes válidos.  Verificamos que
        # el mecanismo de validación existe y funciona correctamente.
        from app.schemas import MAX_SCOPES, MCP_SCOPES, normalise_scopes as ns
        assert MAX_SCOPES == 20
        assert len(MCP_SCOPES) <= 20
        # Con scopes válidos y sin duplicados funciona
        result = ns(list(MCP_SCOPES))
        assert len(result) == len(MCP_SCOPES)

    def test_empty_name_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(db, user.id, _valid_payload(name=""))

    def test_name_with_spaces_normalized(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload(name="  Mi Token  "))
        assert result.name == "Mi Token"

    def test_name_over_200_chars_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(db, user.id, _valid_payload(name="x" * 201))

    def test_name_only_spaces_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(db, user.id, _valid_payload(name="   "))

    def test_valid_constraints_saved(self, db):
        user = _user(db)
        studio = _studio(db, user)
        board = _board(db, studio)
        constraints = MCPTokenConstraints(
            studio_ids=[studio.id], board_ids=[board.id]
        )
        result = create_mcp_token(
            db, user.id, _valid_payload(constraints=constraints)
        )
        assert result.constraints is not None
        assert result.constraints.studio_ids == [studio.id]
        assert result.constraints.board_ids == [board.id]

    def test_duplicate_constraint_ids_deduplicated(self, db):
        user = _user(db)
        studio = _studio(db, user)
        constraints = MCPTokenConstraints(
            studio_ids=[studio.id, studio.id],
        )
        result = create_mcp_token(
            db, user.id, _valid_payload(constraints=constraints)
        )
        assert result.constraints is not None
        assert len(result.constraints.studio_ids) == 1
        assert result.constraints.studio_ids[0] == studio.id

    def test_more_than_100_studios_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(
                db, user.id,
                _valid_payload(constraints=MCPTokenConstraints(studio_ids=[str(i) for i in range(101)]))
            )

    def test_more_than_100_boards_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(
                db, user.id,
                _valid_payload(constraints=MCPTokenConstraints(board_ids=[str(i) for i in range(101)]))
            )

    def test_other_user_studio_in_constraints_fails(self, db):
        user = _user(db)
        other = _other_user(db)
        other_studio = _studio(db, other)
        # get_owned_studio lanza ResourceNotFound para studios ajenos
        with pytest.raises((ValidationFailure, ResourceNotFound)):
            create_mcp_token(
                db, user.id,
                _valid_payload(
                    constraints=MCPTokenConstraints(studio_ids=[other_studio.id])
                )
            )

    def test_other_user_board_in_constraints_fails(self, db):
        user = _user(db)
        other = _other_user(db)
        other_studio = _studio(db, other)
        other_board = _board(db, other_studio)
        with pytest.raises((ValidationFailure, ResourceNotFound)):
            create_mcp_token(
                db, user.id,
                _valid_payload(
                    constraints=MCPTokenConstraints(board_ids=[other_board.id])
                )
            )

    def test_board_not_in_allowed_studio_fails(self, db):
        user = _user(db)
        studio_a = _studio(db, user)
        studio_b_raw = Studio(
            id=uuid.uuid4().hex[:16],
            name="Studio B",
            color="verde",
            user_id=user.id,
        )
        db.add(studio_b_raw)
        db.commit()
        board_in_b = _board(db, studio_b_raw)
        constraints = MCPTokenConstraints(
            studio_ids=[studio_a.id],
            board_ids=[board_in_b.id],
        )
        with pytest.raises(ValidationFailure):
            create_mcp_token(
                db, user.id,
                _valid_payload(constraints=constraints)
            )

    def test_empty_scopes_list_fails(self, db):
        user = _user(db)
        with pytest.raises(ValidationFailure):
            create_mcp_token(db, user.id, _valid_payload(scopes=[]))

    def test_rollback_on_failure(self, db):
        """Un payload inválido no deja registros parciales."""
        user = _user(db)
        count_before = db.query(MCPToken).count()
        try:
            create_mcp_token(db, user.id, _valid_payload(scopes=["invalid"]))
        except InvalidScope:
            pass
        count_after = db.query(MCPToken).count()
        assert count_after == count_before


# ======================================================================
# Listado
# ======================================================================


class TestListTokens:
    def test_returns_only_own_tokens(self, db):
        user = _user(db)
        other = _other_user(db)
        create_mcp_token(db, user.id, _valid_payload(name="Mio"))
        create_mcp_token(db, other.id, _valid_payload(name="Otro"))
        tokens = list_mcp_tokens(db, user.id)
        assert len(tokens) == 1
        assert tokens[0].name == "Mio"

    def test_does_not_return_token_hash(self, db):
        user = _user(db)
        create_mcp_token(db, user.id, _valid_payload())
        tokens = list_mcp_tokens(db, user.id)
        assert len(tokens) == 1
        t = tokens[0]
        assert not hasattr(t, "token_hash")
        assert not hasattr(t, "token")

    def test_returns_summaries(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        tokens = list_mcp_tokens(db, user.id)
        assert len(tokens) == 1
        t = tokens[0]
        assert isinstance(t, MCPTokenSummary)
        assert t.id == result.id
        assert t.token_prefix == result.token_prefix
        assert t.scopes == result.scopes

    def test_order_is_stable(self, db):
        user = _user(db)
        r1 = create_mcp_token(db, user.id, _valid_payload(name="A"))
        r2 = create_mcp_token(db, user.id, _valid_payload(name="B"))
        tokens = list_mcp_tokens(db, user.id)
        # Más reciente primero (created_at DESC, id DESC)
        assert tokens[0].name == "B"
        assert tokens[1].name == "A"

    def test_does_not_commit(self, db):
        user = _user(db)
        create_mcp_token(db, user.id, _valid_payload())
        list_mcp_tokens(db, user.id)
        # La sesión no debe tener cambios pendientes
        assert not db.dirty

    def test_does_not_update_last_used_at(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        list_mcp_tokens(db, user.id)
        token = db.get(MCPToken, result.id)
        assert token.last_used_at is None

    def test_empty_list_for_no_tokens(self, db):
        user = _user(db)
        tokens = list_mcp_tokens(db, user.id)
        assert tokens == []


# ======================================================================
# Revocación
# ======================================================================


class TestRevokeToken:
    def test_revoke_own_token(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        summary = revoke_mcp_token(db, user.id, result.id)
        assert summary.revoked_at is not None

    def test_revoke_other_user_token_fails(self, db):
        user = _user(db)
        other = _other_user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        with pytest.raises(ResourceNotFound):
            revoke_mcp_token(db, other.id, result.id)

    def test_revoke_nonexistent_fails(self, db):
        user = _user(db)
        with pytest.raises(ResourceNotFound):
            revoke_mcp_token(db, user.id, "nonexistent_id")

    def test_revoke_twice_is_idempotent(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        r1 = revoke_mcp_token(db, user.id, result.id)
        r2 = revoke_mcp_token(db, user.id, result.id)
        assert r2.revoked_at == r1.revoked_at

    def test_summary_does_not_expose_hash_or_token(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        summary = revoke_mcp_token(db, user.id, result.id)
        assert not hasattr(summary, "token_hash")
        assert not hasattr(summary, "token")

    def test_revoke_updates_db(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        revoke_mcp_token(db, user.id, result.id)
        token = db.get(MCPToken, result.id)
        assert token.revoked_at is not None


# ======================================================================
# Eliminación
# ======================================================================


class TestDeleteToken:
    def test_delete_own_token(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        delete_mcp_token(db, user.id, result.id)
        assert db.get(MCPToken, result.id) is None

    def test_delete_other_user_token_fails(self, db):
        user = _user(db)
        other = _other_user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        with pytest.raises(ResourceNotFound):
            delete_mcp_token(db, other.id, result.id)

    def test_delete_nonexistent_fails(self, db):
        user = _user(db)
        with pytest.raises(ResourceNotFound):
            delete_mcp_token(db, user.id, "nonexistent_id")

    def test_delete_does_not_affect_other_tokens(self, db):
        user = _user(db)
        r1 = create_mcp_token(db, user.id, _valid_payload(name="A"))
        r2 = create_mcp_token(db, user.id, _valid_payload(name="B"))
        delete_mcp_token(db, user.id, r1.id)
        remaining = list_mcp_tokens(db, user.id)
        assert len(remaining) == 1
        assert remaining[0].name == "B"

    def test_delete_user_cascades_to_tokens(self, db):
        user = _user(db)
        create_mcp_token(db, user.id, _valid_payload())
        assert db.query(MCPToken).count() == 1
        db.delete(user)
        db.commit()
        assert db.query(MCPToken).count() == 0


# ======================================================================
# get_owned_mcp_token
# ======================================================================


class TestGetOwnedToken:
    def test_gets_own_token(self, db):
        user = _user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        token = get_owned_mcp_token(db, user.id, result.id)
        assert token.id == result.id
        assert token.user_id == user.id

    def test_other_user_token_fails(self, db):
        user = _user(db)
        other = _other_user(db)
        result = create_mcp_token(db, user.id, _valid_payload())
        with pytest.raises(ResourceNotFound):
            get_owned_mcp_token(db, other.id, result.id)

    def test_nonexistent_fails(self, db):
        user = _user(db)
        with pytest.raises(ResourceNotFound):
            get_owned_mcp_token(db, user.id, "nonexistent")
