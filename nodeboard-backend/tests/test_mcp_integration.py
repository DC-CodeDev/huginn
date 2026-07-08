"""Tests de integración MCP — transporte Streamable HTTP real.

Usa el cliente oficial del SDK MCP para conectar al servidor
a través de httpx con ASGI transport, verificando que el
protocolo MCP funciona correctamente de extremo a extremo.

Cada test construye su propia app FastAPI con MCP montado y
sobrescribe SessionLocal para usar la BD de prueba.
"""
import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Board, MCPToken, Node, Studio, User
from app.mcp.auth import _now
from app.mcp.server import get_mcp_asgi, reset as mcp_reset


def _create_token(db, user, scopes=None, constraints=None):
    import secrets
    secret = secrets.token_urlsafe(32)
    raw = f"huginn_mcp_{secret}"
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    token_prefix = f"huginn_mcp_{secret[:6]}"
    now = _now()
    if scopes is None:
        scopes = ["studios:read", "folders:read", "boards:read", "nodes:read"]
    record = MCPToken(
        id=uuid.uuid4().hex[:16], user_id=user.id, name="Integration Token",
        token_prefix=token_prefix, token_hash=token_hash,
        scopes=scopes, constraints=constraints,
        created_at=now, expires_at=now + timedelta(days=90),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return raw, record


@asynccontextmanager
async def mcp_app():
    """Crea una FastAPI con MCP montado y lifespan activo."""
    from app.mcp.server import mcp_lifespan
    mcp_reset()
    app = FastAPI()
    @app.get("/api/health")
    def health():
        return {"status": "ok"}
    app.mount("/mcp", get_mcp_asgi())
    async with mcp_lifespan():
        yield app


@pytest.fixture()
def fs_db(tmp_path):
    import os
    db_path = str(tmp_path / "test_mcp_int.db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session, TestSession
    finally:
        session.close()
        try:
            os.unlink(db_path)
        except OSError:
            pass


@pytest.fixture()
def fs_user(fs_db):
    session, _ = fs_db
    u = User(id=uuid.uuid4().hex[:16], email="int@test.com", name="Integration", auth_provider="google")
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture()
def fs_studio(fs_db, fs_user):
    session, _ = fs_db
    s = Studio(id=uuid.uuid4().hex[:16], name="Int Studio", color="azul", user_id=fs_user.id)
    session.add(s)
    session.commit()
    session.refresh(s)
    return s


@pytest.fixture()
def fs_board(fs_db, fs_user, fs_studio):
    session, _ = fs_db
    b = Board(id=uuid.uuid4().hex[:16], name="Int Board", studio_id=fs_studio.id)
    session.add(b)
    session.commit()
    return b


class TestMCPProtocol:
    @pytest.mark.asyncio
    async def test_initialize_and_list_tools(self, fs_db, fs_user):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user)
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    async with streamable_http_client(
                        "http://test/mcp/", http_client=client,
                    ) as (read, write, _):
                        async with ClientSession(read, write) as session_:
                            await session_.initialize()
                            result = await session_.list_tools()
                            tool_names = [t.name for t in result.tools]
        assert "list_studios" in tool_names
        assert "list_folders" in tool_names
        assert "list_boards" in tool_names
        assert "get_board_summary" in tool_names
        assert "get_board" in tool_names
        assert "get_node" in tool_names
        assert len(tool_names) == 6

    @pytest.mark.asyncio
    async def test_call_list_studios(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json
        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user)
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    async with streamable_http_client(
                        "http://test/mcp/", http_client=client,
                    ) as (read, write, _):
                        async with ClientSession(read, write) as session_:
                            await session_.initialize()
                            result = await session_.call_tool("list_studios", {})
        assert result.isError is not True
        data = json.loads(result.content[0].text)
        assert len(data["studios"]) == 1
        assert data["studios"][0]["name"] == "Int Studio"

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, fs_db):
        session, TestSession = fs_db
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.post("/mcp/", json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, fs_db):
        session, TestSession = fs_db
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": "Bearer huginn_mcp_invalid"},
                ) as client:
                    resp = await client.post("/mcp/", json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, fs_db, fs_user):
        import secrets
        session, TestSession = fs_db
        secret = secrets.token_urlsafe(32)
        raw = f"huginn_mcp_{secret}"
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        now = _now()
        record = MCPToken(
            id=uuid.uuid4().hex[:16], user_id=fs_user.id, name="Expired",
            token_prefix=f"huginn_mcp_{secret[:6]}", token_hash=token_hash,
            scopes=["boards:read"], created_at=now - timedelta(days=200),
            expires_at=now - timedelta(days=1),
        )
        session.add(record)
        session.commit()
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    resp = await client.post("/mcp/", json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_revoked_token_returns_401(self, fs_db, fs_user):
        import secrets
        session, TestSession = fs_db
        secret = secrets.token_urlsafe(32)
        raw = f"huginn_mcp_{secret}"
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        now = _now()
        record = MCPToken(
            id=uuid.uuid4().hex[:16], user_id=fs_user.id, name="Revoked",
            token_prefix=f"huginn_mcp_{secret[:6]}", token_hash=token_hash,
            scopes=["boards:read"], created_at=now, expires_at=now + timedelta(days=90),
            revoked_at=now,
        )
        session.add(record)
        session.commit()
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    resp = await client.post("/mcp/", json={"jsonrpc": "2.0", "method": "initialize", "id": 1})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_last_used_at_updated(self, fs_db, fs_user):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        session, TestSession = fs_db
        raw, record = _create_token(session, fs_user)
        assert record.last_used_at is None
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    async with streamable_http_client(
                        "http://test/mcp/", http_client=client,
                    ) as (read, write, _):
                        async with ClientSession(read, write) as session_:
                            await session_.initialize()
                            await session_.list_tools()
        session.refresh(record)
        assert record.last_used_at is not None

    @pytest.mark.asyncio
    async def test_response_does_not_contain_token_or_hash(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user)
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    async with streamable_http_client(
                        "http://test/mcp/", http_client=client,
                    ) as (read, write, _):
                        async with ClientSession(read, write) as session_:
                            await session_.initialize()
                            result = await session_.call_tool("list_studios", {})
        text = str(result.content)
        assert raw not in text
        assert "token_hash" not in text

    @pytest.mark.asyncio
    async def test_nonexistent_tool_returns_error(self, fs_db, fs_user):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user)
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    async with streamable_http_client(
                        "http://test/mcp/", http_client=client,
                    ) as (read, write, _):
                        async with ClientSession(read, write) as session_:
                            await session_.initialize()
                            result = await session_.call_tool("nonexistent_tool", {})
                            # MCP returns tool error (isError=True) instead of raising
                            assert result.isError is True


class TestConcurrentAccess:
    @pytest.mark.asyncio
    async def test_concurrent_users_isolated(self, fs_db):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json
        session, TestSession = fs_db
        u1 = User(id=uuid.uuid4().hex[:16], email="user1@test.com", name="User1", auth_provider="google")
        u2 = User(id=uuid.uuid4().hex[:16], email="user2@test.com", name="User2", auth_provider="google")
        session.add(u1)
        session.add(u2)
        session.commit()
        s1 = Studio(id=uuid.uuid4().hex[:16], name="Studio One", color="azul", user_id=u1.id)
        s2 = Studio(id=uuid.uuid4().hex[:16], name="Studio Two", color="verde", user_id=u2.id)
        session.add(s1)
        session.add(s2)
        session.commit()
        t1_raw, _ = _create_token(session, u1)
        t2_raw, _ = _create_token(session, u2)
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async def call_list_studios(raw_token: str) -> list:
                    async with httpx.AsyncClient(
                        transport=ASGITransport(app=app),
                        base_url="http://test",
                        headers={"Authorization": f"Bearer {raw_token}"},
                    ) as client:
                        async with streamable_http_client(
                            "http://test/mcp/", http_client=client,
                        ) as (read, write, _):
                            async with ClientSession(read, write) as session_:
                                await session_.initialize()
                                result = await session_.call_tool("list_studios", {})
                                return json.loads(result.content[0].text)["studios"]
                results = await asyncio.gather(
                    call_list_studios(t1_raw),
                    call_list_studios(t2_raw),
                )
        assert len(results[0]) == 1
        assert results[0][0]["name"] == "Studio One"
        assert len(results[1]) == 1
        assert results[1][0]["name"] == "Studio Two"


class TestMountOrder:
    @pytest.mark.asyncio
    async def test_get_mcp_returns_401_not_html(self, fs_db):
        session, TestSession = fs_db
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.get("/mcp/", headers={"Accept": "application/json"})
        assert resp.status_code == 401
        assert "json" in (resp.headers.get("content-type", "") or "")

    @pytest.mark.asyncio
    async def test_health_still_works(self, fs_db):
        session, TestSession = fs_db
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestNoWriteTools:
    @pytest.mark.asyncio
    async def test_no_write_tools(self, fs_db, fs_user):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user)
        import app.database as db_module
        with patch.object(db_module, 'SessionLocal', TestSession):
            async with mcp_app() as app:
                async with httpx.AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"Authorization": f"Bearer {raw}"},
                ) as client:
                    async with streamable_http_client(
                        "http://test/mcp/", http_client=client,
                    ) as (read, write, _):
                        async with ClientSession(read, write) as session_:
                            await session_.initialize()
                            result = await session_.list_tools()
        tool_names = [t.name for t in result.tools]
        write_terms = {"create", "update", "delete", "save", "move", "write", "patch", "edit"}
        for name in tool_names:
            for term in write_terms:
                assert term not in name, f"Found write tool: {name}"
