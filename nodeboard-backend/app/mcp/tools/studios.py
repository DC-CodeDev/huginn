"""Tool MCP: list_studios — solo lectura.

Devuelve los estudios accesibles para el token, aplicando constraints
de scopes y constraints del token.
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import models
from ... import database as _database
from ...mcp.auth import require_scope, enforce_studio_constraint
from ...mcp.errors import InsufficientScope
from ..context import get_context

logger = logging.getLogger(__name__)

_MAX_STUDIOS = 100


def register(mcp) -> None:
    @mcp.tool(
        name="list_studios",
        description=(
            "Lista los estudios accesibles para el token actual. "
            "Cada estudio incluye id, name y created_at. "
            "Solo devuelve estudios propios del usuario autenticado. "
            "Orden estable por nombre."
        ),
    )
    def list_studios() -> dict:
        """Lista los estudios del usuario autenticado."""
        ctx = get_context()
        require_scope(ctx, "studios:read")

        with _database.SessionLocal() as db:
            constraints = ctx.constraints or {}
            studio_ids = constraints.get("studio_ids")
            board_ids = constraints.get("board_ids")

            query = select(models.Studio).where(
                models.Studio.user_id == ctx.user_id
            )

            if studio_ids is not None:
                if len(studio_ids) == 0:
                    return {"studios": []}
                query = query.where(models.Studio.id.in_(studio_ids))
            elif board_ids is not None:
                # Derivar studios de los board_ids permitidos
                if len(board_ids) == 0:
                    return {"studios": []}
                subq = (
                    select(models.Board.studio_id)
                    .where(models.Board.id.in_(board_ids))
                    .distinct()
                    .subquery()
                )
                query = query.where(models.Studio.id.in_(subq))

            query = query.order_by(models.Studio.name).limit(_MAX_STUDIOS)
            studios = db.scalars(query).all()

            return {
                "studios": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "created_at": (
                            s.created_at.isoformat() if s.created_at else None
                        ),
                    }
                    for s in studios
                ]
            }
