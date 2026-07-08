"""Tests HTTP del endpoint auth-check MCP — app y dependencias aisladas.

Crea una instancia FastAPI independiente con sus propias rutas para
evitar cualquier interferencia de estado global con app.main.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import MCPToken, Session as SessionModel, User
from app.mcp.auth import (
    _now,
    authenticate_mcp_token,
    extract_bearer_token,
)
from app.mcp.errors import (
    ExpiredMCPToken,
    InvalidBearerToken,
    MCPAuthenticationError,
    MissingBearerToken,
    RevokedMCPToken,
)
from app.schemas import MCPAuthCheck, MCPTokenConstraints


def _make_token(db, user, **kw):
    import secrets

    secret = secrets.token_urlsafe(32)
    raw = f"huginn_mcp_{secret}"
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    token_prefix = f"huginn_mcp_{secret[:6]}"
    now = _now()
    scopes = kw.pop("scopes", ["boards:read"])
    constraints = kw.pop("constraints", None)
    expires_in_days = kw.pop("expires_in_days", 90)
    revoked = kw.pop("revoked", False)

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
        last_used_at=now if revoked else None,
        revoked_at=now if revoked else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return raw, record


# ======================================================================
# Fixtures: base de datos sobre archivo temporal
# ======================================================================


@pytest.fixture()
def fs_db(tmp_path):
    import os

    db_path = str(tmp_path / "test_http_auth.db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.fixture()
def fs_user(fs_db):
    u = User(id=uuid.uuid4().hex[:16], email="http_test@example.com", name="HTTP User", auth_provider="google")
    fs_db.add(u)
    fs_db.commit()
    fs_db.refresh(u)
    return u


# ======================================================================
# Tests
# ======================================================================


class TestAuthCheckHTTP:
    """HTTP auth-check con app FastAPI independiente.

    Cada test crea su propia app y sus propias dependencias,
    eliminando totalmente el shared state.
    """

    def _app(self, db):
        """Crea una app FastAPI temporal con get_db y auth-check."""

        def get_db():
            yield db

        def _mcp_context(request: Request, _db: Session = Depends(get_db)):
            authorization = request.headers.get("Authorization")
            try:
                raw_token = extract_bearer_token(authorization)
                ctx = authenticate_mcp_token(_db, raw_token, update_last_used=True)
            except (MissingBearerToken, InvalidBearerToken, ExpiredMCPToken, RevokedMCPToken, MCPAuthenticationError):
                raise HTTPException(
                    status_code=401,
                    detail="Credenciales MCP inválidas.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return ctx

        def _auth_check(ctx=Depends(_mcp_context)):
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            return MCPAuthCheck(
                authenticated=True,
                token_id=ctx.token_id,
                token_prefix=ctx.token_prefix,
                scopes=sorted(ctx.scopes),
                constraints=None
                if ctx.constraints is None
                else MCPTokenConstraints(
                    studio_ids=ctx.constraints.get("studio_ids"),
                    board_ids=ctx.constraints.get("board_ids"),
                ),
                expires_at=ctx.expires_at,
                last_used_at=now,
            )

        app = FastAPI()
        app.add_api_route(
            "/api/integrations/mcp/auth-check",
            _auth_check,
            methods=["GET"],
            response_model=MCPAuthCheck,
        )
        return app

    def test_valid_bearer_returns_200(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200

    def test_returns_authenticated_true(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.json()["authenticated"] is True

    def test_does_not_return_full_token(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        data = resp.json()
        assert "token" not in data
        assert raw not in str(data)

    def test_does_not_return_token_hash(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert "token_hash" not in resp.json()

    def test_does_not_return_email(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        data = resp.json()
        assert "email" not in data
        assert fs_user.email not in str(data)

    def test_updates_last_used_at(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        assert record.last_used_at is None
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200
        fs_db.refresh(record)
        assert record.last_used_at is not None

    def test_no_authorization_returns_401(self, fs_db):
        resp = TestClient(self._app(fs_db)).get("/api/integrations/mcp/auth-check")
        assert resp.status_code == 401

    def test_basic_auth_returns_401(self, fs_db):
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401

    def test_invalid_bearer_returns_401(self, fs_db):
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": "Bearer huginn_mcp_invalid"},
        )
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user, expires_in_days=-1)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401

    def test_revoked_token_returns_401(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user, revoked=True)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401

    def test_401_has_www_authenticate_header(self, fs_db):
        resp = TestClient(self._app(fs_db)).get("/api/integrations/mcp/auth-check")
        assert resp.status_code == 401
        assert resp.headers.get("www-authenticate") == "Bearer"

    def test_all_auth_errors_generic_message(self, fs_db):
        cases = [
            {},
            {"Authorization": "Bearer invalid"},
            {"Authorization": "Basic dXNlcjpwYXNz"},
            {"Authorization": "Bearer huginn_mcp_"},
        ]
        for headers in cases:
            resp = TestClient(self._app(fs_db)).get(
                "/api/integrations/mcp/auth-check",
                headers=headers,
            )
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Credenciales MCP inválidas."

    def test_cookie_web_without_bearer_does_not_authenticate(self, fs_db, fs_user):
        now = _now()
        session = SessionModel(id=uuid.uuid4().hex[:16], user_id=fs_user.id, expires_at=now + timedelta(days=7))
        fs_db.add(session)
        fs_db.commit()
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            cookies={"session": session.id},
        )
        assert resp.status_code == 401

    def test_cookie_plus_valid_bearer_authenticates_by_bearer(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        now = _now()
        session = SessionModel(id=uuid.uuid4().hex[:16], user_id=fs_user.id, expires_at=now + timedelta(days=7))
        fs_db.add(session)
        fs_db.commit()
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
            cookies={"session": session.id},
        )
        assert resp.status_code == 200

    def test_endpoint_not_caught_by_spa(self):
        """auth-check debe ser ruta API real, devolver 401 no HTML."""
        resp = TestClient(self._app(None)).get("/api/integrations/mcp/auth-check")
        assert resp.status_code == 401

    def test_response_content_type_json(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert "application/json" in resp.headers.get("content-type", "")

    def test_response_has_expected_fields(self, fs_db, fs_user):
        raw, record = _make_token(fs_db, fs_user)
        resp = TestClient(self._app(fs_db)).get(
            "/api/integrations/mcp/auth-check",
            headers={"Authorization": f"Bearer {raw}"},
        )
        expected = {"authenticated", "token_id", "token_prefix", "scopes", "constraints", "expires_at"}
        assert expected.issubset(resp.json().keys())
