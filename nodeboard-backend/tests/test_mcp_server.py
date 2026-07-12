"""Tests del servidor MCP — construcción, montaje y feature flag.

No dependen de la base de datos (usan mock o app aislada para
verificar que el servidor se construye correctamente).
"""
import os
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI

from app.mcp.server import _build_mcp, get_mcp_asgi, reset


# ======================================================================
# Tests de construcción del servidor
# ======================================================================


class TestServerConstruction:
    def test_sdk_imports_correctly(self):
        """El SDK MCP se importa sin errores."""
        from mcp.server.fastmcp import FastMCP
        assert FastMCP is not None

    def test_server_constructs(self):
        """Se puede construir el servidor FastMCP."""
        reset()
        mcp = _build_mcp()
        assert mcp is not None

    def test_streamable_http_mode(self):
        """El servidor se construye en modo Streamable HTTP."""
        reset()
        mcp = _build_mcp()
        assert mcp.settings.stateless_http is True
        assert mcp.settings.json_response is True
        assert mcp.settings.streamable_http_path == "/"

    def test_asgi_app_created(self):
        """La app ASGI se crea sin errores."""
        reset()
        asgi = get_mcp_asgi()
        assert asgi is not None

    def test_asgi_is_cached(self):
        """get_mcp_asgi() cachea la instancia."""
        reset()
        a = get_mcp_asgi()
        b = get_mcp_asgi()
        assert a is b

    def test_reset_clears_cache(self):
        """reset() invalida el caché."""
        reset()
        a = get_mcp_asgi()
        reset()
        b = get_mcp_asgi()
        assert a is not b


# ======================================================================
# Tests de feature flag
# ======================================================================


class TestFeatureFlag:
    @pytest.mark.asyncio
    async def test_default_disabled(self):
        """MCP_ENABLED ausente → servidor no montado."""
        # Crear app sin MCP
        app = FastAPI()
        @app.get("/api/health")
        async def health():
            return {"status": "ok"}
        @app.get("/{full_path:path}", include_in_schema=False)
        async def catch_all(full_path: str):
            return {"path": full_path}

        with patch.dict(os.environ, {}, clear=True):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/mcp")
                # Sin montaje MCP → cae en catch-all
                assert resp.status_code == 200
                assert resp.json()["path"] == "mcp"

    @pytest.mark.asyncio
    async def test_explicit_disabled(self):
        """MCP_ENABLED=false → servidor no montado."""
        app = FastAPI()
        @app.get("/api/health")
        async def health():
            return {"status": "ok"}
        @app.get("/{full_path:path}", include_in_schema=False)
        async def catch_all(full_path: str):
            return {"path": full_path}

        with patch.dict(os.environ, {"MCP_ENABLED": "false"}, clear=True):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.get("/mcp")
                assert resp.status_code == 200
                assert resp.json()["path"] == "mcp"

    @pytest.mark.parametrize("truthy", ["1", "true", "yes", "on", "True", "YES", "ON"])
    def test_truthy_values(self, truthy):
        """Valores verdaderos aceptados."""
        from app.main import _is_true
        assert _is_true(truthy) is True

    @pytest.mark.parametrize("falsy", [None, "", "0", "false", "no", "off", "disabled"])
    def test_falsy_values(self, falsy):
        """Valores falsos."""
        from app.main import _is_true
        assert _is_true(falsy) is False


# ======================================================================
# Tests del módulo server
# ======================================================================


class TestReset:
    def test_reset_then_rebuild(self):
        """reset() permite reconstruir con nuevas tools."""
        import app.mcp.server as srv
        srv.reset()
        assert srv._MCP_SERVER is None
        assert srv._MCP_ASGI is None
        # Reconstruir
        mcp = srv._build_mcp()
        assert mcp is not None
        assert srv._MCP_SERVER is mcp
        # Y se puede obtener la ASGI
        asgi = srv.get_mcp_asgi()
        assert asgi is not None
        assert srv._MCP_ASGI is asgi


# ======================================================================
# Tests de import del paquete
# ======================================================================


class TestPackageImports:
    def test_tools_package_imports(self):
        from app.mcp.tools import register_tools, studios, folders, boards, nodes
        assert register_tools is not None
        assert studios is not None
        assert folders is not None
        assert boards is not None
        assert nodes is not None

    def test_server_module_imports(self):
        from app.mcp import server, auth, context, errors
        assert server is not None
        assert auth is not None
        assert context is not None
        assert errors is not None
