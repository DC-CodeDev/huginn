"""Tool MCP: list_folders — solo lectura.

Devuelve las carpetas de un estudio, aplicando constraints.
"""
import logging

from sqlalchemy import select

from ... import models
from ... import database as _database
from ...mcp.auth import require_scope, enforce_studio_constraint
from ...services.authorization import get_owned_studio
from ..read_guard import ReadResult, execute_read_tool
from ..context import get_context

logger = logging.getLogger(__name__)

_MAX_FOLDERS = 500


def register(mcp) -> None:
    @mcp.tool(
        name="list_folders",
        description=(
            "Lista las carpetas de un estudio específico. "
            "Requiere studio_id. Cada carpeta incluye id, studio_id y name."
        ),
    )
    def list_folders(studio_id: str) -> dict:
        """Lista las carpetas de un estudio."""
        ctx = get_context()

        def operation() -> ReadResult:
            require_scope(ctx, "folders:read")

            with _database.SessionLocal() as db:
                get_owned_studio(db, ctx.user_id, studio_id)
                enforce_studio_constraint(ctx, studio_id)

                query = (
                    select(models.Folder)
                    .where(models.Folder.studio_id == studio_id)
                    .order_by(models.Folder.name)
                    .limit(_MAX_FOLDERS)
                )

                constraints = ctx.constraints or {}
                board_ids = constraints.get("board_ids")
                if board_ids is not None:
                    subq = select(models.Board.folder_id).where(
                        models.Board.id.in_(board_ids),
                        models.Board.folder_id.isnot(None),
                    ).distinct()
                    query = query.where(models.Folder.id.in_(subq))

                folders = db.scalars(query).all()
                response = {
                    "folders": [
                        {
                            "id": f.id,
                            "studio_id": f.studio_id,
                            "name": f.name,
                        }
                        for f in folders
                    ]
                }
                returned_count = len(folders)
                return ReadResult(
                    response=response,
                    resource_type="studio",
                    resource_id=studio_id,
                    returned_count=returned_count,
                    metadata={"returned_count": returned_count},
                )

        return execute_read_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="list_folders",
            capability_type="folder",
            audit_resource_type="studio",
            audit_resource_id=studio_id,
            operation=operation,
        )
