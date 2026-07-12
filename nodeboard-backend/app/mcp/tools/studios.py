"""Tool MCP: list_studios — solo lectura.

Devuelve los estudios accesibles para el token, aplicando constraints
de scopes y constraints del token.
"""
import logging
from sqlalchemy import select

from ... import models
from ... import database as _database
from ...mcp.auth import require_scope
from ..read_guard import ReadResult, execute_read_tool
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

        def operation() -> ReadResult:
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
                        response = {"studios": []}
                        return ReadResult(
                            response=response,
                            resource_type="studio",
                            resource_id=None,
                            returned_count=0,
                            metadata={"returned_count": 0},
                        )
                    query = query.where(models.Studio.id.in_(studio_ids))
                elif board_ids is not None:
                    if len(board_ids) == 0:
                        response = {"studios": []}
                        return ReadResult(
                            response=response,
                            resource_type="studio",
                            resource_id=None,
                            returned_count=0,
                            metadata={"returned_count": 0},
                        )
                    subq = select(models.Board.studio_id).where(
                        models.Board.id.in_(board_ids)
                    ).distinct()
                    query = query.where(models.Studio.id.in_(subq))

                query = query.order_by(models.Studio.name).limit(_MAX_STUDIOS)
                studios = db.scalars(query).all()

                response = {
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
                returned_count = len(studios)
                return ReadResult(
                    response=response,
                    resource_type="studio",
                    resource_id=None,
                    returned_count=returned_count,
                    metadata={"returned_count": returned_count},
                )

        return execute_read_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="list_studios",
            capability_type="studio",
            audit_resource_type="studio",
            audit_resource_id=None,
            operation=operation,
        )
