"""Tools MCP: list_boards, get_board_summary, get_board — solo lectura.
"""
import logging
from sqlalchemy import func, select

from ... import models
from ... import database as _database
from ...mcp.auth import require_scope, enforce_studio_constraint, enforce_board_constraint
from ...services.authorization import get_owned_studio, get_owned_board
from ...services.errors import ResourceNotFound
from ..context import get_context

logger = logging.getLogger(__name__)

_MAX_NODES = 1000
_MAX_EDGES = 2000
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


def register(mcp) -> None:
    # ------------------------------------------------------------------
    # list_boards
    # ------------------------------------------------------------------
    @mcp.tool(
        name="list_boards",
        description=(
            "Lista los tableros de un estudio. "
            "Requiere studio_id. Opcionalmente filtra por folder_id. "
            "Soporta paginación con limit (1-100) y offset (>=0). "
            "Cada board incluye id, studio_id, folder_id, name, version, created_at y updated_at. "
            "No incluye nodos ni edges."
        ),
    )
    def list_boards(
        studio_id: str,
        folder_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Lista los boards de un estudio."""
        ctx = get_context()
        require_scope(ctx, "boards:read")

        if limit < 1 or limit > 100:
            raise ValueError("limit debe estar entre 1 y 100")
        if offset < 0:
            raise ValueError("offset debe ser >= 0")

        with _database.SessionLocal() as db:
            try:
                studio = get_owned_studio(db, ctx.user_id, studio_id)
            except ResourceNotFound:
                raise ValueError(f"Estudio no encontrado: {studio_id}")

            enforce_studio_constraint(ctx, studio_id)

            query = select(models.Board).where(
                models.Board.studio_id == studio_id
            )

            constraints = ctx.constraints or {}
            board_ids = constraints.get("board_ids")
            if board_ids is not None:
                query = query.where(models.Board.id.in_(board_ids))

            if folder_id is not None:
                query = query.where(models.Board.folder_id == folder_id)
            else:
                query = query.where(models.Board.folder_id.is_(None))

            query = query.order_by(models.Board.updated_at.desc())
            query = query.offset(offset).limit(limit)
            boards = db.scalars(query).all()

            return {
                "boards": [
                    {
                        "id": b.id,
                        "studio_id": b.studio_id,
                        "folder_id": b.folder_id,
                        "name": b.name,
                        "version": b.version,
                        "created_at": (
                            b.created_at.isoformat() if b.created_at else None
                        ),
                        "updated_at": (
                            b.updated_at.isoformat() if b.updated_at else None
                        ),
                    }
                    for b in boards
                ],
                "limit": limit,
                "offset": offset,
                "returned": len(boards),
            }

    # ------------------------------------------------------------------
    # get_board_summary
    # ------------------------------------------------------------------
    @mcp.tool(
        name="get_board_summary",
        description=(
            "Obtiene un resumen de un tablero: nombre, versión, conteo de nodos y edges. "
            "No incluye el contenido completo de nodos ni edges. "
            "Requiere board_id."
        ),
    )
    def get_board_summary(board_id: str) -> dict:
        """Obtiene resumen de un board."""
        ctx = get_context()
        require_scope(ctx, "boards:read")

        with _database.SessionLocal() as db:
            try:
                board = get_owned_board(db, ctx.user_id, board_id)
            except ResourceNotFound:
                raise ValueError(f"Board no encontrado: {board_id}")

            enforce_board_constraint(db, ctx, board_id)

            node_count = (
                db.scalar(
                    select(func.count())
                    .select_from(models.Node)
                    .where(models.Node.board_id == board.id)
                )
                or 0
            )
            edge_count = (
                db.scalar(
                    select(func.count())
                    .select_from(models.Edge)
                    .where(models.Edge.board_id == board.id)
                )
                or 0
            )

            return {
                "id": board.id,
                "studio_id": board.studio_id,
                "folder_id": board.folder_id,
                "name": board.name,
                "version": board.version,
                "node_count": node_count,
                "edge_count": edge_count,
                "created_at": (
                    board.created_at.isoformat() if board.created_at else None
                ),
                "updated_at": (
                    board.updated_at.isoformat() if board.updated_at else None
                ),
            }

    # ------------------------------------------------------------------
    # get_board
    # ------------------------------------------------------------------
    @mcp.tool(
        name="get_board",
        description=(
            "Obtiene el estado completo de un board accesible para el token. "
            "Incluye nodos y edges. Por defecto omite los datos base64 de imágenes. "
            "Usar include_images=true solo cuando sea necesario. "
            "Requiere board_id."
        ),
    )
    def get_board(board_id: str, include_images: bool = False) -> dict:
        """Obtiene estado completo de un board."""
        ctx = get_context()
        require_scope(ctx, "boards:read")

        with _database.SessionLocal() as db:
            try:
                board = get_owned_board(db, ctx.user_id, board_id)
            except ResourceNotFound:
                raise ValueError(f"Board no encontrado: {board_id}")

            enforce_board_constraint(db, ctx, board_id)

            # Cargar nodos y edges
            nodes = (
                db.scalars(
                    select(models.Node)
                    .where(models.Node.board_id == board.id)
                    .limit(_MAX_NODES)
                ).all()
            )
            edges = (
                db.scalars(
                    select(models.Edge)
                    .where(models.Edge.board_id == board.id)
                    .limit(_MAX_EDGES)
                ).all()
            )

            node_list = []
            for n in nodes:
                node_dict = _node_to_output(n, include_images)
                node_list.append(node_dict)

            edge_list = []
            for e in edges:
                edge_list.append(
                    {
                        "id": e.id,
                        "from": {"nodeId": e.from_node, "portId": e.from_port},
                        "to": {"nodeId": e.to_node, "portId": e.to_port},
                        "curved": e.curved,
                        "label": e.label,
                    }
                )

            result = {
                "id": board.id,
                "name": board.name,
                "version": board.version,
                "nodes": node_list,
                "edges": edge_list,
            }

            # Verificar límite de tamaño (solo cuando include_images activa datos grandes)
            result_json = _json_dumps(result)
            if len(result_json) > _MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"La respuesta excede el límite de {_MAX_RESPONSE_BYTES} bytes. "
                    "Intente con include_images=false."
                )

            return result


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------


def _node_to_output(node: models.Node, include_images: bool) -> dict:
    """Convierte un nodo ORM a dict de salida, omitiendo imágenes si corresponde."""
    d = {
        "id": node.id,
        "type": node.type,
        "title": node.title,
        "x": node.x,
        "y": node.y,
        "w": node.w,
        "ports": node.ports if node.ports else [],
        "tags": node.tags if node.tags else [],
    }

    if node.type == "card" and node.blocks:
        if include_images:
            d["blocks"] = node.blocks
        else:
            d["blocks"] = [_omit_image_src(b) for b in node.blocks]
    else:
        d["blocks"] = node.blocks if node.blocks else []

    if node.type == "timeline" and node.stages:
        d["stages"] = node.stages
    else:
        d["stages"] = node.stages if node.stages else []

    return d


def _omit_image_src(block: dict) -> dict:
    """Reemplaza el src base64 de un ImageBlock por metadata segura."""
    if not isinstance(block, dict) or block.get("type") != "image":
        return block

    src = block.get("src", "") or ""
    if not src.startswith("data:"):
        return {
            "type": "image",
            "id": block.get("id", ""),
            "image_omitted": True,
            "mime_type": None,
            "size_bytes": 0,
        }

    try:
        header, data = src.split(",", 1)
        mime_type = header.split(";")[0][5:]  # Remove "data:" prefix
        size_bytes = len(data)  # Approximate (base64 encoded length)
        return {
            "type": "image",
            "id": block.get("id", ""),
            "image_omitted": True,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
        }
    except (ValueError, IndexError):
        return {
            "type": "image",
            "id": block.get("id", ""),
            "image_omitted": True,
            "mime_type": None,
            "size_bytes": 0,
        }


def _json_dumps(obj: dict) -> str:
    """Serializa a JSON, importando json localmente."""
    import json
    return json.dumps(obj, default=str)
