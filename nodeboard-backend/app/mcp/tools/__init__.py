"""Tools MCP de solo lectura.

Cada sub-módulo expone una función ``register(mcp)`` que vincula sus
tools a la instancia ``FastMCP``.
"""

from mcp.server.fastmcp import FastMCP


def register_tools(mcp: FastMCP) -> None:
    """Registra todas las tools de solo lectura en el servidor *mcp*."""
    # Importaciones diferidas para evitar ciclos
    from . import studios, folders, boards, nodes

    studios.register(mcp)
    folders.register(mcp)
    boards.register(mcp)
    nodes.register(mcp)
