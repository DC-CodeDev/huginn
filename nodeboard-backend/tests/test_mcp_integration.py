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
from app.services import mcp_rate_limit


def _create_token(db, user, scopes=None, constraints=None):
    import secrets
    secret = secrets.token_urlsafe(32)
    raw = f"huginn_mcp_{secret}"
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    token_prefix = f"huginn_mcp_{secret[:6]}"
    now = _now()
    if scopes is None:
        scopes = [
            "studios:read",
            "folders:read",
            "boards:read",
            "boards:create",
            "nodes:read",
        ]
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


class _FakeMonotonicClock:
    def __init__(self, start: float = 0.0):
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@asynccontextmanager
async def mcp_app():
    """Crea una FastAPI con MCP montado y lifespan activo."""
    from app.mcp.server import mcp_lifespan
    mcp_reset()
    app = FastAPI()
    @app.get("/api/health")
    async def health():
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
        assert "create_board" in tool_names
        assert "rename_board" in tool_names
        assert "create_node" in tool_names
        assert "update_node" in tool_names
        assert "create_edge" in tool_names
        assert "update_edge" in tool_names
        assert "get_node" in tool_names
        assert "create_nodes_batch" in tool_names
        assert "create_edges_batch" in tool_names
        assert "apply_board_patch" in tool_names
        assert len(tool_names) == 16

    @pytest.mark.asyncio
    async def test_call_create_board(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user, scopes=["boards:create"])
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
                            result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Creado por MCP"},
                            )
        assert result.isError is not True
        data = json.loads(result.content[0].text)
        assert data["ok"] is True
        assert data["data"]["board"]["name"] == "Creado por MCP"

    @pytest.mark.asyncio
    async def test_call_rename_board(self, fs_db, fs_user, fs_board):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user, scopes=["boards:update"])
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
                            result = await session_.call_tool(
                                "rename_board",
                                {
                                    "board_id": fs_board.id,
                                    "name": "Renombrado por MCP",
                                    "expected_version": 1,
                                },
                            )
        assert result.isError is not True
        data = json.loads(result.content[0].text)
        assert data["ok"] is True
        assert data["data"]["board"]["name"] == "Renombrado por MCP"
        assert data["data"]["board_version"] == 2

    @pytest.mark.asyncio
    async def test_call_create_node_and_read_it_back(self, fs_db, fs_user, fs_board):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user, scopes=["nodes:create", "nodes:read"])
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
                            created = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 1,
                                    "node": {
                                        "type": "card",
                                        "title": "Nodo MCP",
                                        "x": 10,
                                        "y": 20,
                                        "ports": [],
                                        "blocks": [],
                                        "tags": [],
                                    },
                                },
                            )
                            created_data = json.loads(created.content[0].text)
                            node_id = created_data["data"]["node"]["id"]
                            read_back = await session_.call_tool(
                                "get_node",
                                {"node_id": node_id},
                            )
        assert created.isError is not True
        created_data = json.loads(created.content[0].text)
        assert created_data["ok"] is True
        assert created_data["data"]["node"]["title"] == "Nodo MCP"
        assert created_data["data"]["board_version"] == 2
        assert read_back.isError is not True
        read_data = json.loads(read_back.content[0].text)
        assert read_data["node"]["id"] == node_id
        assert read_data["node"]["board_id"] == fs_board.id

    @pytest.mark.asyncio
    async def test_call_update_node_and_read_it_back(self, fs_db, fs_user, fs_board):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user, scopes=["nodes:create", "nodes:update", "nodes:read"])
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
                            created = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 1,
                                    "node": {
                                        "type": "card",
                                        "title": "Nodo inicial",
                                        "x": 10,
                                        "y": 20,
                                        "ports": [],
                                        "blocks": [],
                                        "tags": ["a"],
                                    },
                                },
                            )
                            created_data = json.loads(created.content[0].text)
                            node_id = created_data["data"]["node"]["id"]
                            updated = await session_.call_tool(
                                "update_node",
                                {
                                    "node_id": node_id,
                                    "expected_version": 2,
                                    "changes": {
                                        "title": "Nodo actualizado",
                                        "tags": ["b"],
                                    },
                                },
                            )
                            read_back = await session_.call_tool(
                                "get_node",
                                {"node_id": node_id},
                            )
        assert updated.isError is not True
        update_data = json.loads(updated.content[0].text)
        assert update_data["ok"] is True
        assert update_data["data"]["node"]["title"] == "Nodo actualizado"
        assert update_data["data"]["node"]["x"] == 10
        assert update_data["data"]["node"]["y"] == 20
        assert update_data["data"]["node"]["type"] == "card"
        assert update_data["data"]["changed_fields"] == ["title", "tags"]
        assert update_data["data"]["previous_version"] == 2
        assert update_data["data"]["board_version"] == 3
        assert read_back.isError is not True
        read_data = json.loads(read_back.content[0].text)
        assert read_data["node"]["title"] == "Nodo actualizado"
        assert read_data["node"]["x"] == 10
        assert read_data["node"]["y"] == 20
        assert read_data["node"]["type"] == "card"

    @pytest.mark.asyncio
    async def test_call_move_node_and_read_it_back(self, fs_db, fs_user, fs_board):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["nodes:create", "nodes:update", "nodes:read"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            created = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 1,
                                    "node": {
                                        "type": "card",
                                        "title": "Nodo movable",
                                        "x": 10,
                                        "y": 20,
                                        "ports": [],
                                        "blocks": [],
                                        "tags": ["a"],
                                    },
                                },
                            )
                            created_data = json.loads(created.content[0].text)
                            node_id = created_data["data"]["node"]["id"]
                            moved = await session_.call_tool(
                                "move_node",
                                {
                                    "node_id": node_id,
                                    "x": 480,
                                    "y": -120,
                                    "expected_version": 2,
                                },
                            )
                            read_back = await session_.call_tool(
                                "get_node",
                                {"node_id": node_id},
                            )
        assert moved.isError is not True
        move_data = json.loads(moved.content[0].text)
        assert move_data["ok"] is True
        assert move_data["data"]["node"]["x"] == 480
        assert move_data["data"]["node"]["y"] == -120
        assert move_data["data"]["node"]["title"] == "Nodo movable"
        assert move_data["data"]["node"]["type"] == "card"
        assert move_data["data"]["previous_position"] == {"x": 10, "y": 20}
        assert move_data["data"]["position"] == {"x": 480, "y": -120}
        assert move_data["data"]["previous_version"] == 2
        assert move_data["data"]["board_version"] == 3
        assert read_back.isError is not True
        read_data = json.loads(read_back.content[0].text)
        assert read_data["node"]["x"] == 480
        assert read_data["node"]["y"] == -120
        assert read_data["node"]["title"] == "Nodo movable"
        assert read_data["node"]["type"] == "card"

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
    async def test_call_create_edge_and_read_it_back(self, fs_db, fs_user, fs_board):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["nodes:create", "edges:create", "nodes:read"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            # Create two nodes with ports
                            created_a = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 1,
                                    "node": {
                                        "type": "card",
                                        "title": "Source",
                                        "x": 0, "y": 0,
                                        "ports": [{"id": "out", "side": "right", "color": "#60A5FA", "label": ""}],
                                        "blocks": [], "tags": [],
                                    },
                                },
                            )
                            data_a = json.loads(created_a.content[0].text)
                            node_a_id = data_a["data"]["node"]["id"]
                            created_b = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 2,
                                    "node": {
                                        "type": "card",
                                        "title": "Target",
                                        "x": 200, "y": 0,
                                        "ports": [{"id": "in", "side": "left", "color": "#4ADE80", "label": ""}],
                                        "blocks": [], "tags": [],
                                    },
                                },
                            )
                            data_b = json.loads(created_b.content[0].text)
                            node_b_id = data_b["data"]["node"]["id"]
                            # Create edge between them
                            created_edge = await session_.call_tool(
                                "create_edge",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 3,
                                    "edge": {
                                        "from": {"nodeId": node_a_id, "portId": "out"},
                                        "to": {"nodeId": node_b_id, "portId": "in"},
                                        "label": "conecta",
                                    },
                                },
                            )
                            # Read via get_node to verify no corruption
                            read_a = await session_.call_tool(
                                "get_node",
                                {"node_id": node_a_id},
                            )
        assert created_edge.isError is not True
        edge_data = json.loads(created_edge.content[0].text)
        assert edge_data["ok"] is True
        assert edge_data["data"]["edge"]["from"]["nodeId"] == node_a_id
        assert edge_data["data"]["edge"]["to"]["nodeId"] == node_b_id
        assert edge_data["data"]["edge"]["label"] == "conecta"
        assert edge_data["data"]["previous_version"] == 3
        assert edge_data["data"]["board_version"] == 4
        # Verify node content preserved
        read_a_data = json.loads(read_a.content[0].text)
        assert read_a_data["node"]["title"] == "Source"

    @pytest.mark.asyncio
    async def test_call_update_edge_and_verify(self, fs_db, fs_user, fs_board):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["nodes:create", "edges:create", "edges:update", "nodes:read"],
        )
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
                            created_a = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 1,
                                    "node": {
                                        "type": "card",
                                        "title": "Src",
                                        "x": 0, "y": 0,
                                        "ports": [{"id": "out", "side": "right", "color": "#60A5FA", "label": ""}],
                                        "blocks": [], "tags": [],
                                    },
                                },
                            )
                            data_a = json.loads(created_a.content[0].text)
                            node_a_id = data_a["data"]["node"]["id"]
                            created_b = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 2,
                                    "node": {
                                        "type": "card",
                                        "title": "Dst",
                                        "x": 200, "y": 0,
                                        "ports": [{"id": "in", "side": "left", "color": "#4ADE80", "label": ""}],
                                        "blocks": [], "tags": [],
                                    },
                                },
                            )
                            data_b = json.loads(created_b.content[0].text)
                            node_b_id = data_b["data"]["node"]["id"]
                            created_edge = await session_.call_tool(
                                "create_edge",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 3,
                                    "edge": {
                                        "from": {"nodeId": node_a_id, "portId": "out"},
                                        "to": {"nodeId": node_b_id, "portId": "in"},
                                        "label": "original",
                                    },
                                },
                            )
                            edge_data = json.loads(created_edge.content[0].text)
                            edge_id = edge_data["data"]["edge"]["id"]
                            updated = await session_.call_tool(
                                "update_edge",
                                {
                                    "edge_id": edge_id,
                                    "expected_version": 4,
                                    "changes": {"label": "updated", "curved": False},
                                },
                            )
        assert updated.isError is not True
        update_data = json.loads(updated.content[0].text)
        assert update_data["ok"] is True
        assert update_data["data"]["edge"]["label"] == "updated"
        assert update_data["data"]["edge"]["curved"] is False
        assert update_data["data"]["edge"]["from"]["nodeId"] == node_a_id
        assert update_data["data"]["edge"]["to"]["nodeId"] == node_b_id
        assert update_data["data"]["changed_fields"] == ["curved", "label"]
        assert update_data["data"]["previous_version"] == 4
        assert update_data["data"]["board_version"] == 5

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


class TestWriteToolInventory:
    @pytest.mark.asyncio
    async def test_only_create_rename_create_node_and_update_node_are_exposed_for_writes(self, fs_db, fs_user):
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
        write_names = [
            name for name in tool_names
            if any(term in name for term in {"create", "rename", "update", "delete", "save", "move", "write", "patch", "edit"})
        ]
        assert write_names == ["create_board", "rename_board", "create_node", "update_node", "move_node", "create_nodes_batch", "create_edge", "update_edge", "create_edges_batch", "apply_board_patch"]


class TestCreateNodesBatchIntegration:
    @pytest.mark.asyncio
    async def test_create_batch_and_read_back(self, fs_db, fs_user, fs_board):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["nodes:create", "nodes:read"],
        )
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
                            created = await session_.call_tool(
                                "create_nodes_batch",
                                {
                                    "board_id": fs_board.id,
                                    "expected_version": 1,
                                    "nodes": [
                                        {"client_id": "nodo-a", "node": {
                                            "type": "card", "title": "Nodo A",
                                            "x": 100, "y": 200,
                                            "ports": [], "blocks": [], "tags": [],
                                        }},
                                        {"client_id": "nodo-b", "node": {
                                            "type": "timeline", "title": "Nodo B",
                                            "x": 400, "y": 200,
                                            "ports": [], "stages": [], "tags": [],
                                        }},
                                    ],
                                },
                            )
                            # Verify via get_node for each
                            created_data = json.loads(created.content[0].text)
                            node_a_id = created_data["data"]["created"]["nodo-a"]
                            node_b_id = created_data["data"]["created"]["nodo-b"]
                            read_a = await session_.call_tool(
                                "get_node", {"node_id": node_a_id},
                            )
                            read_b = await session_.call_tool(
                                "get_node", {"node_id": node_b_id},
                            )
        assert created.isError is not True
        data = json.loads(created.content[0].text)
        assert data["ok"] is True
        assert data["data"]["created_count"] == 2
        assert data["data"]["previous_version"] == 1
        assert data["data"]["board_version"] == 2
        assert "nodo-a" in data["data"]["created"]
        assert "nodo-b" in data["data"]["created"]
        assert data["data"]["created"]["nodo-a"] != "nodo-a"

        # Verify nodes via get_node
        assert read_a.isError is not True
        read_a_data = json.loads(read_a.content[0].text)
        assert read_a_data["node"]["title"] == "Nodo A"

        assert read_b.isError is not True
        read_b_data = json.loads(read_b.content[0].text)
        assert read_b_data["node"]["title"] == "Nodo B"
        assert read_b_data["node"]["type"] == "timeline"


class TestCreateEdgesBatchIntegration:
    @pytest.mark.asyncio
    async def test_create_nodes_batch_then_edges_batch(self, fs_db, fs_user, fs_studio):
        """Flujo completo: create_board → create_nodes_batch → create_edges_batch."""
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create", "nodes:read",
                     "edges:create"],
        )
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

                            # 1. Create board
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Batch test board"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]

                            # 2. Create nodes batch with ports
                            nodes_result = await session_.call_tool(
                                "create_nodes_batch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "nodes": [
                                        {"client_id": "source", "node": {
                                            "type": "card", "title": "Source",
                                            "x": 0, "y": 0,
                                            "ports": [{"id": "out", "side": "right",
                                                        "color": "#60A5FA", "label": ""}],
                                            "blocks": [], "tags": [],
                                        }},
                                        {"client_id": "target", "node": {
                                            "type": "card", "title": "Target",
                                            "x": 300, "y": 0,
                                            "ports": [{"id": "in", "side": "left",
                                                        "color": "#4ADE80", "label": ""}],
                                            "blocks": [], "tags": [],
                                        }},
                                    ],
                                },
                            )
                            nodes_data = json.loads(nodes_result.content[0].text)
                            source_id = nodes_data["data"]["created"]["source"]
                            target_id = nodes_data["data"]["created"]["target"]
                            nodes_version = nodes_data["data"]["board_version"]

                            # 3. Create edges batch using real node IDs
                            edges_result = await session_.call_tool(
                                "create_edges_batch",
                                {
                                    "board_id": board_id,
                                    "expected_version": nodes_version,
                                    "edges": [
                                        {"client_id": "main-edge", "edge": {
                                            "from": {"nodeId": source_id, "portId": "out"},
                                            "to": {"nodeId": target_id, "portId": "in"},
                                            "label": "conecta",
                                        }},
                                    ],
                                },
                            )

        assert board_result.isError is not True
        assert nodes_result.isError is not True
        assert edges_result.isError is not True

        edges_data = json.loads(edges_result.content[0].text)
        assert edges_data["ok"] is True
        assert edges_data["data"]["created_count"] == 1
        assert edges_data["data"]["created"]["main-edge"] is not None
        assert edges_data["data"]["previous_version"] == nodes_version
        assert edges_data["data"]["board_version"] == nodes_version + 1

        # Verify the edge references the correct node IDs
        edge_out = edges_data["data"]["edges"][0]
        assert edge_out["client_id"] == "main-edge"
        assert edge_out["edge"]["from"]["nodeId"] == source_id
        assert edge_out["edge"]["to"]["nodeId"] == target_id
        assert edge_out["edge"]["label"] == "conecta"


class TestApplyBoardPatchIntegration:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_mutate(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Patch test"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]

                            patch_result = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "dry_run": True,
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node",
                                         "node": {"type": "card", "title": "Patch node",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )

        assert patch_result.isError is not True
        patch_data = json.loads(patch_result.content[0].text)
        assert patch_data["ok"] is True
        assert patch_data["data"]["dry_run"] is True
        assert patch_data["data"]["valid"] is True
        assert patch_data["data"]["operation_count"] == 1
        assert patch_data["data"]["summary"]["nodes_created"] == 1
        assert patch_data["data"]["current_version"] == 1
        assert patch_data["data"]["predicted_version"] == 2

        # Verify no mutation via direct DB check
        verify_session = TestSession()
        try:
            board = verify_session.get(models_module.Board, board_id)
            audits = verify_session.query(models_module.MCPAuditLog).all()
            assert board is not None
            assert board.version == 1
            assert len(board.nodes) == 0
            assert len(audits) == 2
            assert [item.tool_name for item in audits] == ["create_board", "apply_board_patch"]
            assert audits[1].status == "success"
            assert audits[1].metadata_json["dry_run"] is True
            assert audits[1].version_before == 1
            assert audits[1].version_after == 1
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_execute_simple_patch(self, fs_db, fs_user, fs_studio):
        """dry_run=false ejecuta y persiste el patch."""
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Patch exec"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]

                            exec_result = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "dry_run": False,
                                    "idempotency_key": "mcp-patch-001",
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node",
                                         "node": {"type": "card", "title": "Exec node",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )

        assert exec_result.isError is not True
        exec_data = json.loads(exec_result.content[0].text)
        assert exec_data["ok"] is True
        assert exec_data["data"]["dry_run"] is False
        assert exec_data["data"]["applied"] is True
        assert exec_data["data"]["operation_count"] == 1
        assert exec_data["data"]["summary"]["nodes_created"] == 1
        assert exec_data["data"]["previous_version"] == 1
        assert exec_data["data"]["board_version"] == 2
        assert "new-node" in exec_data["data"]["created"]
        assert exec_data["data"]["created"]["new-node"]["resource_type"] == "node"
        assert exec_data["data"]["created"]["new-node"]["id"] is not None

        # Verify node was persisted
        verify_session = TestSession()
        try:
            board = verify_session.get(models_module.Board, board_id)
            audits = verify_session.query(models_module.MCPAuditLog).all()
            assert board is not None
            assert board.version == 2
            assert len(board.nodes) == 1
            created_node = board.nodes[0]
            assert created_node.title == "Exec node"
            assert created_node.x == 100
            assert created_node.y == 200
            assert len(audits) == 2
            assert [item.tool_name for item in audits] == ["create_board", "apply_board_patch"]
            assert audits[1].status == "success"
            assert audits[1].request_id is not None
            assert audits[1].token_id is not None
            assert audits[1].idempotency_key_prefix == "mcp-patc…"
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_execute_patch_replay_returns_same_response(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Patch replay"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]
                            params = {
                                "board_id": board_id,
                                "expected_version": 1,
                                "dry_run": False,
                                "idempotency_key": "mcp-patch-002",
                                "operations": [
                                    {"op": "create_node", "client_id": "new-node",
                                     "node": {"type": "card", "title": "Replay node",
                                              "x": 100, "y": 200}},
                                ],
                            }

                            first = await session_.call_tool("apply_board_patch", params)

                            verify_session = TestSession()
                            try:
                                board = verify_session.get(models_module.Board, board_id)
                                board.version = 3
                                verify_session.add(
                                    models_module.Node(
                                        id=uuid.uuid4().hex[:16],
                                        board_id=board_id,
                                        title="Otro cambio",
                                        ports=[],
                                        blocks=[],
                                        stages=[],
                                        tags=[],
                                    )
                                )
                                verify_session.commit()
                            finally:
                                verify_session.close()

                            replay = await session_.call_tool("apply_board_patch", params)

        assert first.isError is not True
        assert replay.isError is not True
        first_data = json.loads(first.content[0].text)
        replay_data = json.loads(replay.content[0].text)
        assert replay_data == first_data

        verify_session = TestSession()
        try:
            board = verify_session.get(models_module.Board, board_id)
            audits = verify_session.query(models_module.MCPAuditLog).order_by(
                models_module.MCPAuditLog.created_at.asc(),
                models_module.MCPAuditLog.id.asc(),
            ).all()
            assert board.version == 3
            assert len(board.nodes) == 2
            assert len(audits) == 3
            assert [item.tool_name for item in audits] == ["create_board", "apply_board_patch", "apply_board_patch"]
            assert audits[1].status == "success"
            assert audits[2].status == "replay"
            assert audits[1].request_id != audits[2].request_id
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_execute_patch_same_key_different_payload_conflicts(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Patch conflict"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]

                            await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "dry_run": False,
                                    "idempotency_key": "mcp-patch-003",
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node",
                                         "node": {"type": "card", "title": "Uno",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )

                            conflict = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 2,
                                    "dry_run": False,
                                    "idempotency_key": "mcp-patch-003",
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node",
                                         "node": {"type": "card", "title": "Dos",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )

        assert conflict.isError is True
        payload = json.loads(conflict.content[0].text.split(": ", 1)[1])
        assert payload["code"] == "IDEMPOTENCY_CONFLICT"

        verify_session = TestSession()
        try:
            audits = verify_session.query(models_module.MCPAuditLog).order_by(
                models_module.MCPAuditLog.created_at.asc(),
                models_module.MCPAuditLog.id.asc(),
            ).all()
            assert len(audits) == 3
            assert [item.tool_name for item in audits] == ["create_board", "apply_board_patch", "apply_board_patch"]
            assert [item.status for item in audits] == ["success", "success", "error"]
            assert audits[1].token_id == audits[2].token_id
            assert audits[1].resource_id == audits[2].resource_id == board_id
            assert audits[1].request_id != audits[2].request_id
            serialised = json.dumps([item.metadata_json for item in audits], ensure_ascii=False)
            assert "Authorization" not in serialised
            assert "token_hash" not in serialised
            assert "blocks" not in serialised
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_apply_board_patch_rate_limit_blocks_without_mutation_or_idempotency(self, fs_db, fs_user, fs_studio, monkeypatch):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "1")
        clock = _FakeMonotonicClock()
        mcp_rate_limit.configure_default_rate_limiter(
            settings=mcp_rate_limit.load_mcp_rate_limit_settings(),
            clock=clock,
        )

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Patch rate limit"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]

                            first = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "dry_run": False,
                                    "idempotency_key": "mcp-rate-limit-001",
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node",
                                         "node": {"type": "card", "title": "Exec node",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )
                            second = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 2,
                                    "dry_run": False,
                                    "idempotency_key": "mcp-rate-limit-002",
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node-2",
                                         "node": {"type": "card", "title": "Blocked node",
                                                  "x": 120, "y": 220}},
                                    ],
                                },
                            )

        assert first.isError is not True
        assert second.isError is True
        payload = json.loads(second.content[0].text.split(": ", 1)[1])
        assert payload["code"] == "RATE_LIMIT_EXCEEDED"
        assert payload["limit"] == 1
        assert payload["window_seconds"] == 60
        assert payload["retry_after_seconds"] == 60

        verify_session = TestSession()
        try:
            board = verify_session.get(models_module.Board, board_id)
            records = verify_session.query(models_module.MCPIdempotencyRecord).order_by(
                models_module.MCPIdempotencyRecord.created_at.asc(),
                models_module.MCPIdempotencyRecord.id.asc(),
            ).all()
            audits = verify_session.query(models_module.MCPAuditLog).order_by(
                models_module.MCPAuditLog.created_at.asc(),
                models_module.MCPAuditLog.id.asc(),
            ).all()
            assert board.version == 2
            assert len(board.nodes) == 1
            assert len(records) == 1
            assert records[0].idempotency_key == "mcp-rate-limit-001"
            assert [item.tool_name for item in audits] == ["create_board", "apply_board_patch", "apply_board_patch"]
            assert [item.status for item in audits] == ["success", "success", "error"]
            assert audits[2].error_code == "RATE_LIMIT_EXCEEDED"
            assert audits[2].affected_count == 0
            assert audits[2].metadata_json == {
                "limit": 1,
                "window_seconds": 60,
                "retry_after_seconds": 60,
            }
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_apply_board_patch_rate_limit_refill_allows_next_request(self, fs_db, fs_user, fs_studio, monkeypatch):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "1")
        clock = _FakeMonotonicClock()
        mcp_rate_limit.configure_default_rate_limiter(
            settings=mcp_rate_limit.load_mcp_rate_limit_settings(),
            clock=clock,
        )

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create"],
        )
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
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Patch refill"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]

                            first = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "dry_run": True,
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node",
                                         "node": {"type": "card", "title": "Dry run",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )
                            blocked = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "dry_run": True,
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node-2",
                                         "node": {"type": "card", "title": "Blocked",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )
                            clock.advance(60)
                            third = await session_.call_tool(
                                "apply_board_patch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "dry_run": True,
                                    "operations": [
                                        {"op": "create_node", "client_id": "new-node-3",
                                         "node": {"type": "card", "title": "Allowed again",
                                                  "x": 100, "y": 200}},
                                    ],
                                },
                            )

        assert first.isError is not True
        assert blocked.isError is True
        assert third.isError is not True

    @pytest.mark.asyncio
    async def test_mutating_tools_are_audited_once_per_request(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        session, TestSession = fs_db
        raw, _ = _create_token(
            session,
            fs_user,
            scopes=[
                "boards:create",
                "boards:update",
                "nodes:create",
                "nodes:update",
                "edges:create",
                "edges:update",
            ],
        )
        import app.database as db_module
        import app.models as models_module
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
                            create_board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Wrapper audit board"},
                            )
                            create_board_data = json.loads(create_board_result.content[0].text)
                            created_board_id = create_board_data["data"]["board"]["id"]

                            await session_.call_tool(
                                "rename_board",
                                {
                                    "board_id": created_board_id,
                                    "name": "Wrapper audit board renamed",
                                    "expected_version": 1,
                                },
                            )
                            board_id = created_board_id

                            create_node_result = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": board_id,
                                    "expected_version": 2,
                                    "node": {"type": "card", "title": "Node one", "x": 10, "y": 20},
                                },
                            )
                            create_node_data = json.loads(create_node_result.content[0].text)
                            node_id = create_node_data["data"]["node"]["id"]

                            await session_.call_tool(
                                "update_node",
                                {
                                    "node_id": node_id,
                                    "expected_version": 3,
                                    "changes": {"title": "Node updated", "tags": ["x"]},
                                },
                            )
                            await session_.call_tool(
                                "move_node",
                                {
                                    "node_id": node_id,
                                    "expected_version": 4,
                                    "x": 50,
                                    "y": 60,
                                },
                            )
                            batch_nodes = await session_.call_tool(
                                "create_nodes_batch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 5,
                                    "nodes": [
                                        {"client_id": "s", "node": {"type": "card", "title": "Source", "x": 0, "y": 0, "ports": [{"id": "out", "side": "right", "color": "#60A5FA", "label": ""}]}},
                                        {"client_id": "t", "node": {"type": "card", "title": "Target", "x": 80, "y": 0, "ports": [{"id": "in", "side": "left", "color": "#4ADE80", "label": ""}]}},
                                    ],
                                },
                            )
                            batch_nodes_data = json.loads(batch_nodes.content[0].text)
                            source_id = batch_nodes_data["data"]["created"]["s"]
                            target_id = batch_nodes_data["data"]["created"]["t"]

                            create_edge_result = await session_.call_tool(
                                "create_edge",
                                {
                                    "board_id": board_id,
                                    "expected_version": 6,
                                    "edge": {
                                        "from": {"nodeId": source_id, "portId": "out"},
                                        "to": {"nodeId": target_id, "portId": "in"},
                                    },
                                },
                            )
                            create_edge_data = json.loads(create_edge_result.content[0].text)
                            edge_id = create_edge_data["data"]["edge"]["id"]

                            await session_.call_tool(
                                "update_edge",
                                {
                                    "edge_id": edge_id,
                                    "expected_version": 7,
                                    "changes": {"label": "done", "curved": False},
                                },
                            )
                            await session_.call_tool(
                                "create_edges_batch",
                                {
                                    "board_id": board_id,
                                    "expected_version": 8,
                                    "edges": [
                                        {
                                            "client_id": "e2",
                                            "edge": {
                                                "from": {"nodeId": source_id, "portId": "out"},
                                                "to": {"nodeId": node_id, "portId": ""},
                                            },
                                        }
                                    ],
                                },
                            )

        verify_session = TestSession()
        try:
            audits = verify_session.query(models_module.MCPAuditLog).order_by(
                models_module.MCPAuditLog.created_at.asc(),
                models_module.MCPAuditLog.id.asc(),
            ).all()
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
            assert all(item.request_id is not None for item in audits)
            assert all(item.token_id is not None for item in audits)
            serialised = json.dumps([item.metadata_json for item in audits], ensure_ascii=False)
            for forbidden in ("title", "blocks", "stages", "tags", "label", "\"x\"", "\"y\"", "ports"):
                assert forbidden not in serialised
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_write_tool_rate_limit_is_audited_in_real_mcp_flow(self, fs_db, fs_user, fs_studio, monkeypatch):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        monkeypatch.setenv("MCP_RATE_LIMIT_WRITE_PER_MINUTE", "1")
        mcp_rate_limit.clear_default_rate_limiter()

        session, TestSession = fs_db
        raw, _ = _create_token(
            session, fs_user,
            scopes=["boards:create", "nodes:create"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            board_result = await session_.call_tool(
                                "create_board",
                                {"studio_id": fs_studio.id, "name": "Write RL board"},
                            )
                            board_data = json.loads(board_result.content[0].text)
                            board_id = board_data["data"]["board"]["id"]

                            first = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": board_id,
                                    "expected_version": 1,
                                    "node": {"type": "card", "title": "One"},
                                },
                            )
                            second = await session_.call_tool(
                                "create_node",
                                {
                                    "board_id": board_id,
                                    "expected_version": 2,
                                    "node": {"type": "card", "title": "Two"},
                                },
                            )

        assert first.isError is not True
        assert second.isError is True
        payload = json.loads(second.content[0].text.split(": ", 1)[1])
        assert payload["code"] == "RATE_LIMIT_EXCEEDED"

        verify_session = TestSession()
        try:
            audits = verify_session.query(models_module.MCPAuditLog).order_by(
                models_module.MCPAuditLog.created_at.asc(),
                models_module.MCPAuditLog.id.asc(),
            ).all()
            assert [item.tool_name for item in audits] == ["create_board", "create_node", "create_node"]
            assert [item.status for item in audits] == ["success", "success", "error"]
            assert audits[2].error_code == "RATE_LIMIT_EXCEEDED"
            assert audits[2].metadata_json == {
                "limit": 1,
                "window_seconds": 60,
                "retry_after_seconds": 60,
            }
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_read_tools_are_audited_in_real_mcp_flow(self, fs_db, fs_user, fs_studio):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json
        import app.models as models_module

        session, TestSession = fs_db
        folder = models_module.Folder(
            id=uuid.uuid4().hex[:16],
            name="Read Folder",
            studio_id=fs_studio.id,
        )
        session.add(folder)
        session.commit()

        root_board = Board(
            id=uuid.uuid4().hex[:16],
            name="Read Root Board",
            studio_id=fs_studio.id,
        )
        session.add(root_board)
        session.commit()
        session.refresh(root_board)

        node = Node(
            id=uuid.uuid4().hex[:16],
            board_id=root_board.id,
            type="card",
            title="Sensitive Title",
            blocks=[
                {
                    "type": "image",
                    "id": "img-1",
                    "src": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==",
                }
            ],
            ports=[],
            stages=[],
            tags=["secret-tag"],
        )
        session.add(node)
        session.commit()

        raw, token_record = _create_token(
            session,
            fs_user,
            scopes=["studios:read", "folders:read", "boards:read", "nodes:read"],
        )
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
                            await session_.call_tool("list_studios", {})
                            await session_.call_tool("list_folders", {"studio_id": fs_studio.id})
                            await session_.call_tool("list_boards", {"studio_id": fs_studio.id})
                            await session_.call_tool("get_board_summary", {"board_id": root_board.id})
                            await session_.call_tool(
                                "get_board",
                                {"board_id": root_board.id, "include_images": True},
                            )
                            await session_.call_tool(
                                "get_node",
                                {"node_id": node.id, "include_images": True},
                            )

        verify_session = TestSession()
        try:
            audits = verify_session.query(models_module.MCPAuditLog).order_by(
                models_module.MCPAuditLog.created_at.asc(),
                models_module.MCPAuditLog.id.asc(),
            ).all()
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
            assert len({item.request_id for item in audits}) == 6
            assert {item.token_id for item in audits} == {token_record.id}
            serialised = json.dumps([item.metadata_json for item in audits], ensure_ascii=False)
            for forbidden in (
                "Sensitive Title",
                "secret-tag",
                "Read Root Board",
                "Read Folder",
                "data:image",
                "blocks",
                "stages",
                "tags",
                "title",
            ):
                assert forbidden not in serialised
        finally:
            verify_session.close()

    @pytest.mark.asyncio
    async def test_read_tool_rate_limit_is_audited_in_real_mcp_flow(self, fs_db, fs_user, monkeypatch):

        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import json

        monkeypatch.setenv("MCP_RATE_LIMIT_READ_PER_MINUTE", "1")
        mcp_rate_limit.clear_default_rate_limiter()

        session, TestSession = fs_db
        raw, _ = _create_token(
            session,
            fs_user,
            scopes=["studios:read"],
        )
        import app.database as db_module
        import app.models as models_module
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
                            first = await session_.call_tool("list_studios", {})
                            second = await session_.call_tool("list_studios", {})

        assert first.isError is not True
        assert second.isError is True
        payload = json.loads(second.content[0].text.split(": ", 1)[1])
        assert payload["code"] == "RATE_LIMIT_EXCEEDED"

        verify_session = TestSession()
        try:
            audits = verify_session.query(models_module.MCPAuditLog).order_by(
                models_module.MCPAuditLog.created_at.asc(),
                models_module.MCPAuditLog.id.asc(),
            ).all()
            assert [item.tool_name for item in audits] == ["list_studios", "list_studios"]
            assert [item.status for item in audits] == ["success", "error"]
            assert audits[1].error_code == "RATE_LIMIT_EXCEEDED"
            assert audits[1].metadata_json == {
                "limit": 1,
                "window_seconds": 60,
                "retry_after_seconds": 60,
            }
        finally:
            verify_session.close()


class TestProductionMiddlewareChain:
    """POST /mcp/ sin token → 401 en <2 s; con token → 16 tools en <5 s.

    Atraviesa la cadena completa de producción:
    ResponseHeadersMiddleware → CORSMiddleware → FastAPI Router →
    Mount(/mcp) → MCPAuthMiddleware → Starlette sub-app →
    StreamableHTTP → servidor MCP.
    """

    @asynccontextmanager
    async def _prod_app(self, TestSession):
        from fastapi.middleware.cors import CORSMiddleware as _CORS
        from app.mcp.server import reset as _reset, get_mcp_asgi, mcp_lifespan
        from app.main import ResponseHeadersMiddleware
        import app.database as db_module

        _reset()
        test_app = FastAPI()
        test_app.add_middleware(
            _CORS,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=True,
        )
        test_app.add_middleware(ResponseHeadersMiddleware)
        test_app.mount("/mcp", get_mcp_asgi())

        with patch.object(db_module, "SessionLocal", TestSession):
            async with mcp_lifespan():
                yield test_app

    @pytest.mark.asyncio
    async def test_no_token_post_returns_401_in_under_2s(self, fs_db):
        import time

        _, TestSession = fs_db
        async with self._prod_app(TestSession) as app:
            start = time.monotonic()
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/mcp/",
                    json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
                )
            elapsed = time.monotonic() - start

        assert resp.status_code == 401
        assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_valid_token_initialize_and_16_tools_in_under_5s(self, fs_db, fs_user):
        from mcp.client.streamable_http import streamable_http_client
        from mcp import ClientSession
        import time

        session, TestSession = fs_db
        raw, _ = _create_token(session, fs_user)

        async with self._prod_app(TestSession) as app:
            start = time.monotonic()
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {raw}"},
            ) as client:
                async with streamable_http_client(
                    "http://test/mcp/", http_client=client,
                ) as (read, write, _get_session):
                    async with ClientSession(read, write) as mcp_session:
                        await mcp_session.initialize()
                        result = await mcp_session.list_tools()
            elapsed = time.monotonic() - start

        assert elapsed < 5.0
        assert len(result.tools) == 16
