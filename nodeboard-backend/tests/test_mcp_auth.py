"""Tests de autenticación Bearer MCP — unitarios y HTTP.

Cubre:
  - parsing del header Authorization (unitario)
  - autenticación por hash (unitario)
  - actualización de last_used_at (unitario)
  - scope checking (unitario)
  - enforcement de constraints (unitario)
  - endpoint HTTP auth-check
  - aislamiento Bearer vs sesión web
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.main import app
from app.models import Board, MCPToken, Session as SessionModel, Studio, User
from app.mcp.auth import (
    MCP_LAST_USED_WRITE_INTERVAL,
    _now,
    authenticate_mcp_token,
    enforce_board_constraint,
    enforce_studio_constraint,
    extract_bearer_token,
    require_all_scopes,
    require_scope,
)
from app.mcp.context import MCPContext
from app.mcp.errors import (
    ConstraintViolation,
    ExpiredMCPToken,
    InsufficientScope,
    InvalidBearerToken,
    MissingBearerToken,
    RevokedMCPToken,
)
from app.schemas import MCPAuthCheck, MCPTokenConstraints, MCPTokenCreate, MCPTokenCreated, normalise_scopes


# ======================================================================
# Fixtures compartidos
# ======================================================================


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


@pytest.fixture()
def user(db) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email="test@example.com",
        name="Test User",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def other_user(db) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email="other@example.com",
        name="Other User",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def studio(db, user) -> Studio:
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


@pytest.fixture()
def other_studio(db, other_user) -> Studio:
    s = Studio(
        id=uuid.uuid4().hex[:16],
        name="Other Studio",
        color="verde",
        user_id=other_user.id,
    )
    db.add(s)
    db.commit()
    return s


@pytest.fixture()
def board(db, studio) -> Board:
    b = Board(
        id=uuid.uuid4().hex[:16],
        name="Test Board",
        studio_id=studio.id,
    )
    db.add(b)
    db.commit()
    return b


# ======================================================================
# Helpers para crear tokens de prueba
# ======================================================================


def _make_token(
    db: Session,
    user: User,
    scopes: list[str] | None = None,
    constraints: dict | None = None,
    *,
    expires_in_days: int = 90,
    revoked: bool = False,
) -> tuple[str, MCPToken, MCPContext]:
    """Crea un token MCP en BD y devuelve (raw_token, record, context).

    Si se pasa ``revoked=True``, el token se crea ya revocado.
    """
    import secrets

    secret = secrets.token_urlsafe(32)
    prefix = "huginn_mcp_"
    raw = f"{prefix}{secret}"
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    token_prefix = f"{prefix}{secret[:6]}"
    now = _now()

    if scopes is None:
        scopes = ["boards:read", "nodes:read"]

    record = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=user.id,
        name="Test Token",
        token_prefix=token_prefix,
        token_hash=token_hash,
        scopes=scopes,
        constraints=constraints,
        created_at=now,
        expires_at=now + timedelta(days=expires_in_days),
        last_used_at=None,
        revoked_at=now if revoked else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    ctx = MCPContext(
        user_id=record.user_id,
        token_id=record.id,
        scopes=frozenset(record.scopes) if record.scopes else frozenset(),
        constraints=dict(record.constraints) if record.constraints else None,
        token_prefix=record.token_prefix,
        expires_at=record.expires_at,
    )
    return raw, record, ctx


# ======================================================================
# Tests de parsing del header Authorization
# ======================================================================


class TestExtractBearerToken:
    def test_valid_header(self):
        token = extract_bearer_token("Bearer huginn_mcp_fake123")
        assert token == "huginn_mcp_fake123"

    def test_bearer_lowercase(self):
        token = extract_bearer_token("bearer huginn_mcp_fake123")
        assert token == "huginn_mcp_fake123"

    def test_bearer_mixed_case(self):
        token = extract_bearer_token("BEARER huginn_mcp_fake123")
        assert token == "huginn_mcp_fake123"

    def test_missing_header(self):
        with pytest.raises(MissingBearerToken):
            extract_bearer_token(None)

    def test_empty_string(self):
        with pytest.raises(MissingBearerToken):
            extract_bearer_token("")

    def test_basic_scheme(self):
        with pytest.raises(InvalidBearerToken):
            extract_bearer_token("Basic dXNlcjpwYXNz")

    def test_token_scheme(self):
        with pytest.raises(InvalidBearerToken):
            extract_bearer_token("Token xyz123")

    def test_bearer_without_token(self):
        with pytest.raises(InvalidBearerToken):
            extract_bearer_token("Bearer")

    def test_bearer_with_spaces(self):
        with pytest.raises(InvalidBearerToken):
            extract_bearer_token("Bearer huginn_mcp_abc huginn_mcp_def")

    def test_bearer_with_extra_components(self):
        with pytest.raises(InvalidBearerToken):
            extract_bearer_token("Bearer huginn_mcp_abc extra")

    def test_wrong_prefix(self):
        with pytest.raises(InvalidBearerToken):
            extract_bearer_token("Bearer invalid_prefix_abc")

    def test_excessively_long_header(self):
        long_token = "huginn_mcp_" + "x" * 1100
        with pytest.raises(InvalidBearerToken):
            extract_bearer_token(f"Bearer {long_token}")

    def test_token_not_in_error_message(self):
        """Confirmar que el mensaje de error no contiene el token."""
        try:
            extract_bearer_token("Basic dXNlcjpwYXNz")
        except InvalidBearerToken as e:
            assert "huginn_mcp_" not in str(e)
            assert "Basic" not in str(e)

    def test_strip_whitespace(self):
        token = extract_bearer_token("  Bearer   huginn_mcp_abc123  ")
        assert token == "huginn_mcp_abc123"


# ======================================================================
# Tests de autenticación por hash
# ======================================================================


class TestAuthenticateMCPToken:
    def test_valid_token_returns_context(self, db, user):
        raw, record, _ = _make_token(db, user)
        ctx = authenticate_mcp_token(db, raw)
        assert isinstance(ctx, MCPContext)
        assert ctx.token_id == record.id

    def test_context_has_correct_user_id(self, db, user):
        raw, record, _ = _make_token(db, user)
        ctx = authenticate_mcp_token(db, raw)
        assert ctx.user_id == user.id

    def test_context_has_correct_token_id(self, db, user):
        raw, record, _ = _make_token(db, user)
        ctx = authenticate_mcp_token(db, raw)
        assert ctx.token_id == record.id

    def test_context_has_correct_scopes(self, db, user):
        raw, record, _ = _make_token(db, user, scopes=["boards:read", "nodes:read"])
        ctx = authenticate_mcp_token(db, raw)
        assert ctx.scopes == frozenset({"boards:read", "nodes:read"})

    def test_context_has_correct_constraints(self, db, user, studio, board):
        constraints = {"studio_ids": [studio.id]}
        raw, record, _ = _make_token(db, user, constraints=constraints)
        ctx = authenticate_mcp_token(db, raw)
        assert ctx.constraints == constraints

    def test_context_no_token_complete(self, db, user):
        raw, record, _ = _make_token(db, user)
        ctx = authenticate_mcp_token(db, raw)
        assert not hasattr(ctx, "token_full")
        raw_in_repr = raw in repr(ctx)
        assert not raw_in_repr

    def test_context_no_token_hash(self, db, user):
        raw, record, _ = _make_token(db, user)
        ctx = authenticate_mcp_token(db, raw)
        assert not hasattr(ctx, "token_hash")

    def test_nonexistent_token_fails(self, db, user):
        with pytest.raises(InvalidBearerToken):
            authenticate_mcp_token(db, "huginn_mcp_nonexistent_token_abc123")

    def test_modified_token_fails(self, db, user):
        raw, record, _ = _make_token(db, user)
        modified = raw + "x"
        with pytest.raises(InvalidBearerToken):
            authenticate_mcp_token(db, modified)

    def test_revoked_token_fails(self, db, user):
        raw, record, _ = _make_token(db, user, revoked=True)
        with pytest.raises(RevokedMCPToken):
            authenticate_mcp_token(db, raw)

    def test_expired_token_fails(self, db, user):
        raw, record, _ = _make_token(db, user, expires_in_days=-1)
        with pytest.raises(ExpiredMCPToken):
            authenticate_mcp_token(db, raw)

    def test_expires_exactly_now_fails(self, db, user):
        """expires_at == now debe fallar (expires_at <= now)."""
        now = _now()
        import secrets

        secret = secrets.token_urlsafe(32)
        raw = f"huginn_mcp_{secret}"
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        record = MCPToken(
            id=uuid.uuid4().hex[:16],
            user_id=user.id,
            name="Expired now",
            token_prefix=f"huginn_mcp_{secret[:6]}",
            token_hash=token_hash,
            scopes=["boards:read"],
            constraints=None,
            created_at=now,
            expires_at=now,
        )
        db.add(record)
        db.commit()

        with pytest.raises(ExpiredMCPToken):
            authenticate_mcp_token(db, raw)

    def test_valid_future_token_works(self, db, user):
        raw, record, _ = _make_token(db, user, expires_in_days=365)
        ctx = authenticate_mcp_token(db, raw)
        assert ctx.token_id == record.id

    def test_deleted_user_fails(self, db, user):
        raw, record, _ = _make_token(db, user)
        db.delete(user)
        db.commit()
        with pytest.raises(InvalidBearerToken):
            authenticate_mcp_token(db, raw)

    def test_failed_auth_does_not_update_last_used(self, db, user):
        raw, record, _ = _make_token(db, user)
        assert record.last_used_at is None

        with pytest.raises(InvalidBearerToken):
            authenticate_mcp_token(db, "huginn_mcp_wrong_token")

        db.refresh(record)
        assert record.last_used_at is None

    def test_raw_token_not_persisted(self, db, user):
        raw, record, _ = _make_token(db, user)
        db.refresh(record)
        assert record.token_hash is not None
        assert record.token_hash != raw

    def test_search_by_hash_not_prefix(self, db, user):
        raw, record, _ = _make_token(db, user)
        ctx = authenticate_mcp_token(db, raw)
        assert ctx.token_id == record.id
        bad_raw = record.token_prefix + "different_suffix"
        with pytest.raises(InvalidBearerToken):
            authenticate_mcp_token(db, bad_raw)

    def test_token_resolves_only_its_user(self, db, user, other_user):
        raw_a, record_a, _ = _make_token(db, user)
        raw_b, record_b, _ = _make_token(db, other_user, scopes=["boards:read"])
        ctx_a = authenticate_mcp_token(db, raw_a)
        assert ctx_a.user_id == user.id
        ctx_b = authenticate_mcp_token(db, raw_b)
        assert ctx_b.user_id == other_user.id
        assert ctx_a.user_id != ctx_b.user_id


# ======================================================================
# Tests de last_used_at
# ======================================================================


class TestLastUsedAt:
    def test_first_use_sets_last_used(self, db, user):
        raw, record, _ = _make_token(db, user)
        assert record.last_used_at is None
        ctx = authenticate_mcp_token(db, raw, update_last_used=True)
        db.refresh(record)
        assert record.last_used_at is not None

    def test_use_within_5_minutes_does_not_write(self, db, user):
        raw, record, _ = _make_token(db, user)
        ctx = authenticate_mcp_token(db, raw, update_last_used=True)
        db.refresh(record)
        first = record.last_used_at
        ctx = authenticate_mcp_token(db, raw, update_last_used=True)
        db.refresh(record)
        assert record.last_used_at == first

    def test_use_after_5_minutes_updates(self, db, user):
        raw, record, _ = _make_token(db, user)
        with patch("app.mcp.auth._now") as mock_now:
            base = _now()
            mock_now.return_value = base
            ctx = authenticate_mcp_token(db, raw, update_last_used=True)
            db.refresh(record)
            first = record.last_used_at
            later = base + timedelta(minutes=6)
            mock_now.return_value = later
            ctx = authenticate_mcp_token(db, raw, update_last_used=True)
        db.refresh(record)
        assert record.last_used_at > first

    def test_update_last_used_false_does_not_modify(self, db, user):
        raw, record, _ = _make_token(db, user)
        assert record.last_used_at is None
        ctx = authenticate_mcp_token(db, raw, update_last_used=False)
        db.refresh(record)
        assert record.last_used_at is None

    def test_revoked_token_does_not_update(self, db, user):
        raw, record, _ = _make_token(db, user, revoked=True)
        assert record.revoked_at is not None
        original_used = record.last_used_at
        with pytest.raises(RevokedMCPToken):
            authenticate_mcp_token(db, raw, update_last_used=True)
        db.refresh(record)
        assert record.last_used_at == original_used

    def test_expired_token_does_not_update(self, db, user):
        raw, record, _ = _make_token(db, user, expires_in_days=-1)
        assert record.last_used_at is None
        with pytest.raises(ExpiredMCPToken):
            authenticate_mcp_token(db, raw, update_last_used=True)
        db.refresh(record)
        assert record.last_used_at is None

    def test_rollback_does_not_invalidate_context(self, db, user):
        raw, record, _ = _make_token(db, user)
        with patch.object(db, "commit", side_effect=Exception("DB error")):
            ctx = authenticate_mcp_token(db, raw, update_last_used=True)
            assert ctx.token_id == record.id
        db.refresh(record)
        assert record.last_used_at is None

    def test_does_not_modify_other_fields(self, db, user):
        raw, record, _ = _make_token(db, user, scopes=["boards:read"])
        original_scopes = list(record.scopes) if record.scopes else []
        original_hash = record.token_hash
        original_prefix = record.token_prefix
        ctx = authenticate_mcp_token(db, raw, update_last_used=True)
        db.refresh(record)
        assert record.token_hash == original_hash
        assert record.token_prefix == original_prefix
        assert list(record.scopes) == original_scopes
        assert record.revoked_at is None

    def test_does_not_modify_other_tokens(self, db, user):
        raw1, rec1, _ = _make_token(db, user, scopes=["boards:read"])
        raw2, rec2, _ = _make_token(db, user, scopes=["nodes:read"])
        ctx = authenticate_mcp_token(db, raw1, update_last_used=True)
        db.refresh(rec1)
        db.refresh(rec2)
        assert rec1.last_used_at is not None
        assert rec2.last_used_at is None


# ======================================================================
# Tests de scope checking
# ======================================================================


class TestRequireScope:
    def test_exact_scope_allows(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["boards:read"])
        require_scope(ctx, "boards:read")

    def test_missing_scope_raises(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["boards:read"])
        with pytest.raises(InsufficientScope):
            require_scope(ctx, "nodes:read")

    def test_boards_read_not_equivalent_to_nodes_read(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["boards:read"])
        with pytest.raises(InsufficientScope):
            require_scope(ctx, "nodes:read")

    def test_wildcard_not_accepted(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["*"])
        with pytest.raises(InsufficientScope):
            require_scope(ctx, "boards:read")

    def test_all_scopes_present(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["boards:read", "nodes:read", "studios:read"])
        require_all_scopes(ctx, ["boards:read", "nodes:read"])

    def test_one_of_multiple_missing(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["boards:read"])
        with pytest.raises(InsufficientScope):
            require_all_scopes(ctx, ["boards:read", "nodes:read"])

    def test_does_not_modify_context(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["boards:read"])
        original_repr = repr(ctx)
        require_scope(ctx, "boards:read")
        assert repr(ctx) == original_repr

    def test_error_message_not_sensitive(self, db, user):
        raw, record, ctx = _make_token(db, user, scopes=["boards:read"])
        try:
            require_scope(ctx, "nodes:read")
        except InsufficientScope as e:
            msg = str(e)
            assert ctx.user_id not in msg
            assert ctx.token_id not in msg
            assert "huginn_mcp_" not in msg


# ======================================================================
# Tests de enforcement de constraints
# ======================================================================


class TestEnforceStudioConstraint:
    def test_no_constraints_allows(self, db, user, studio):
        raw, record, ctx = _make_token(db, user)
        enforce_studio_constraint(ctx, studio.id)

    def test_studio_included_allows(self, db, user, studio):
        raw, record, ctx = _make_token(db, user, constraints={"studio_ids": [studio.id]})
        enforce_studio_constraint(ctx, studio.id)

    def test_studio_not_included_raises(self, db, user, studio):
        raw, record, ctx = _make_token(db, user, constraints={"studio_ids": ["some_other_studio"]})
        with pytest.raises(ConstraintViolation):
            enforce_studio_constraint(ctx, studio.id)

    def test_empty_studio_ids_allows_none(self, db, user, studio):
        raw, record, ctx = _make_token(db, user, constraints={"studio_ids": []})
        with pytest.raises(ConstraintViolation):
            enforce_studio_constraint(ctx, studio.id)


class TestEnforceBoardConstraint:
    def test_no_constraints_allows(self, db, user, studio, board):
        raw, record, ctx = _make_token(db, user)
        enforce_board_constraint(db, ctx, board.id)

    def test_board_included_allows(self, db, user, studio, board):
        raw, record, ctx = _make_token(db, user, constraints={"board_ids": [board.id]})
        enforce_board_constraint(db, ctx, board.id)

    def test_board_not_included_raises(self, db, user, studio, board):
        raw, record, ctx = _make_token(db, user, constraints={"board_ids": ["some_other_board"]})
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, board.id)

    def test_studio_included_board_included_allows(self, db, user, studio, board):
        raw, record, ctx = _make_token(db, user, constraints={"studio_ids": [studio.id], "board_ids": [board.id]})
        enforce_board_constraint(db, ctx, board.id)

    def test_board_included_studio_not_included_raises(self, db, user, studio, board):
        raw, record, ctx = _make_token(db, user, constraints={"studio_ids": ["other_studio"], "board_ids": [board.id]})
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, board.id)

    def test_studio_included_board_not_included_raises(self, db, user, studio, board):
        raw, record, ctx = _make_token(db, user, constraints={"studio_ids": [studio.id], "board_ids": ["other_board"]})
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, board.id)

    def test_empty_board_ids_allows_none(self, db, user, studio, board):
        raw, record, ctx = _make_token(db, user, constraints={"board_ids": []})
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, board.id)

    def test_other_user_board_not_allowed(self, db, user, other_user, other_studio):
        b = Board(id=uuid.uuid4().hex[:16], name="Other Board", studio_id=other_studio.id)
        db.add(b)
        db.commit()
        raw, record, ctx = _make_token(db, user)
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, b.id)

    def test_nonexistent_board_fails(self, db, user):
        raw, record, ctx = _make_token(db, user)
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, "nonexistent_board_id")

    def test_constraints_not_substitute_ownership(self, db, user, other_user, other_studio, board):
        raw, record, ctx = _make_token(db, other_user)
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, board.id)

    def test_invented_id_in_constraints_does_not_grant_access(self, db, user):
        raw, record, ctx = _make_token(db, user, constraints={"board_ids": ["invented_board"]})
        with pytest.raises(ConstraintViolation):
            enforce_board_constraint(db, ctx, "invented_board")

    def test_does_not_reveal_other_user_resources(self, db, user, other_user, other_studio):
        b = Board(id=uuid.uuid4().hex[:16], name="Other Board", studio_id=other_studio.id)
        db.add(b)
        db.commit()
        raw, record, ctx = _make_token(db, user)
        try:
            enforce_board_constraint(db, ctx, b.id)
        except ConstraintViolation as e:
            msg = str(e)
            assert b.id not in msg


# ======================================================================
# Tests HTTP del endpoint auth-check
#
# IMPORTANTE: Usan base sobre ARCHIVO TEMPORAL (no :memory:).
# El TestClient ejecuta el lifespan (Alembic), que provoca que el pool
# de conexiones de :memory: cree una base independiente por conexión,
# perdiendo los datos.
# ======================================================================
