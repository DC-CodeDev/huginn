"""Tool MCP: get_node — solo lectura.

Devuelve un nodo individual por ID, con verificación de ownership
y constraints del board y studio asociados.
"""
import logging

from sqlalchemy import select

from ... import models
from ... import database as _database
from ...mcp.auth import require_scope, enforce_board_constraint
from ...services.authorization import get_owned_node, get_owned_board
from ...services.errors import ResourceNotFound
from ..context import get_context

logger = logging.getLogger(__name__)


def register(mcp) -> None:
    @mcp.tool(
        name="get_node",
        description=(
            "Obtiene un nodo individual por su ID. "
            "Incluye title, type, posición, puertos, bloques, stages y tags. "
            "Por defecto omite los datos base64 de imágenes. "
            "Requiere node_id. Scope necesario: nodes:read."
        ),
    )
    def get_node(node_id: str, include_images: bool = False) -> dict:
        """Obtiene un nodo individual."""
        ctx = get_context()
        require_scope(ctx, "nodes:read")

        with _database.SessionLocal() as db:
            try:
                node = get_owned_node(db, ctx.user_id, node_id)
            except ResourceNotFound:
                raise ValueError(f"Nodo no encontrado: {node_id}")

            enforce_board_constraint(db, ctx, node.board_id)

            d = {
                "node": {
                    "id": node.id,
                    "board_id": node.board_id,
                    "type": node.type,
                    "title": node.title,
                    "x": node.x,
                    "y": node.y,
                    "w": node.w,
                    "ports": node.ports if node.ports else [],
                    "tags": node.tags if node.tags else [],
                }
            }

            if node.type == "card" and node.blocks:
                if include_images:
                    d["node"]["blocks"] = node.blocks
                else:
                    from .boards import _omit_image_src
                    d["node"]["blocks"] = [_omit_image_src(b) for b in node.blocks]
            else:
                d["node"]["blocks"] = node.blocks if node.blocks else []

            if node.type == "timeline" and node.stages:
                d["node"]["stages"] = node.stages
            else:
                d["node"]["stages"] = node.stages if node.stages else []

            return d
