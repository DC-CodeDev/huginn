"""Tools MCP para boards.
"""
import logging
from sqlalchemy import func, select

from ... import models
from ... import schemas
from ... import database as _database
from ...mcp.mutation_guard import MutationResult, execute_mutating_tool
from ...mcp.auth import enforce_studio_constraint, enforce_board_constraint
from ...mcp.errors import ConstraintViolation
from ...mcp.read_guard import ReadResult, execute_read_tool
from ...mcp.write_helpers import (
    build_success,
    require_board_scope,
    require_scope,
    resolve_expected_version,
)
from ...services.boards import (
    create_board as create_board_service,
    rename_board as rename_board_service,
)
from ...services.authorization import get_owned_studio, get_owned_board
from ..context import get_context

logger = logging.getLogger(__name__)

_MAX_NODES = 1000
_MAX_EDGES = 2000
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB


def _board_write_output(board: models.Board) -> dict[str, object]:
    return {
        "id": board.id,
        "name": board.name,
        "studio_id": board.studio_id,
        "folder_id": board.folder_id,
        "version": board.version,
        "created_at": (
            board.created_at.isoformat() if board.created_at else None
        ),
        "updated_at": (
            board.updated_at.isoformat() if board.updated_at else None
        ),
    }


def register(mcp) -> None:
    def _execute_create_board(ctx, payload: schemas.BoardCreate) -> MutationResult:
        require_scope(ctx, "boards:create")
        enforce_studio_constraint(ctx, payload.studio_id)

        constraints = ctx.constraints or {}
        if constraints.get("board_ids") is not None:
            raise ConstraintViolation(
                "El token no puede crear boards nuevos con la restriccion actual."
            )

        with _database.SessionLocal() as db:
            created = create_board_service(db, ctx.user_id, payload)
            board = get_owned_board(db, ctx.user_id, created.id)
            board_output = _board_write_output(board)
            board_id = board.id
            board_version = board.version

        return MutationResult(
            response=build_success(data={"board": board_output}),
            resource_type="board",
            resource_id=board_id,
            affected_count=1,
            version_before=None,
            version_after=board_version,
            metadata={
                "operation_kind": "create_board",
                "changed_field_count": 1,
            },
        )

    def _execute_rename_board(
        ctx,
        board_id: str,
        payload: schemas.BoardRename,
    ) -> MutationResult:
        with _database.SessionLocal() as db:
            board = require_board_scope(db, ctx, board_id, "boards:update")
            previous_version = resolve_expected_version(
                board, payload.expected_version
            )
            rename_board_service(
                db,
                ctx.user_id,
                board.id,
                payload,
                board=board,
            )
            board_output = _board_write_output(board)
            board_id_resolved = board.id
            board_version = board.version

        return MutationResult(
            response=build_success(
                data={
                    "board": board_output,
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="board",
            resource_id=board_id_resolved,
            affected_count=1,
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "rename_board",
                "changed_field_count": 1,
            },
        )

    # ------------------------------------------------------------------
    # create_board
    # ------------------------------------------------------------------
    @mcp.tool(
        name="create_board",
        description=(
            "Crea un board vacio dentro de un studio autorizado. "
            "Acepta studio_id y name; folder_id es opcional. "
            "Requiere scope boards:create. "
            "Respeta ownership y constraints del token."
        ),
    )
    def create_board(
        studio_id: str,
        name: str = "Tablero sin nombre",
        folder_id: str | None = None,
    ) -> dict:
        """Crea un board vacio reutilizando el servicio de dominio."""
        payload = schemas.BoardCreate(
            studio_id=studio_id,
            name=name,
            folder_id=folder_id,
        )
        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="create_board",
            category="write",
            capability_type="board",
            audit_resource_type="board",
            audit_resource_id=None,
            operation=lambda: _execute_create_board(ctx, payload),
        )

    # ------------------------------------------------------------------
    # rename_board
    # ------------------------------------------------------------------
    @mcp.tool(
        name="rename_board",
        description=(
            "Renombra un board existente autorizado. "
            "Acepta board_id, name y expected_version. "
            "Requiere scope boards:update. "
            "Respeta ownership, constraints y optimistic locking."
        ),
    )
    def rename_board(
        board_id: str,
        name: str,
        expected_version: int,
    ) -> dict:
        """Renombra un board reutilizando el servicio de dominio."""
        payload = schemas.BoardRename(
            name=name,
            expected_version=expected_version,
        )
        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="rename_board",
            category="write",
            capability_type="board",
            audit_resource_type="board",
            audit_resource_id=board_id,
            operation=lambda: _execute_rename_board(ctx, board_id, payload),
        )

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
        if limit < 1 or limit > 100:
            raise ValueError("limit debe estar entre 1 y 100")
        if offset < 0:
            raise ValueError("offset debe ser >= 0")

        ctx = get_context()

        def operation() -> ReadResult:
            require_scope(ctx, "boards:read")

            with _database.SessionLocal() as db:
                get_owned_studio(db, ctx.user_id, studio_id)
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

                response = {
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
                returned_count = len(boards)
                return ReadResult(
                    response=response,
                    resource_type="folder" if folder_id is not None else "studio",
                    resource_id=folder_id or studio_id,
                    returned_count=returned_count,
                    metadata={
                        "returned_count": returned_count,
                        "limit": limit,
                    },
                )

        return execute_read_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="list_boards",
            capability_type="board",
            audit_resource_type="folder" if folder_id is not None else "studio",
            audit_resource_id=folder_id or studio_id,
            operation=operation,
        )

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

        def operation() -> ReadResult:
            require_scope(ctx, "boards:read")

            with _database.SessionLocal() as db:
                board = get_owned_board(db, ctx.user_id, board_id)
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

                response = {
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
                return ReadResult(
                    response=response,
                    resource_type="board",
                    resource_id=board.id,
                    returned_count=1,
                    metadata={"returned_count": 1},
                )

        return execute_read_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="get_board_summary",
            capability_type="board",
            audit_resource_type="board",
            audit_resource_id=board_id,
            operation=operation,
        )

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

        def operation() -> ReadResult:
            require_scope(ctx, "boards:read")

            with _database.SessionLocal() as db:
                board = get_owned_board(db, ctx.user_id, board_id)
                enforce_board_constraint(db, ctx, board_id)

                raw_nodes = db.scalars(
                    select(models.Node)
                    .where(models.Node.board_id == board.id)
                    .limit(_MAX_NODES + 1)
                ).all()
                raw_edges = db.scalars(
                    select(models.Edge)
                    .where(models.Edge.board_id == board.id)
                    .limit(_MAX_EDGES + 1)
                ).all()
                nodes = raw_nodes[:_MAX_NODES]
                edges = raw_edges[:_MAX_EDGES]
                response_truncated = (
                    len(raw_nodes) > _MAX_NODES or len(raw_edges) > _MAX_EDGES
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

                result_json = _json_dumps(result)
                if len(result_json) > _MAX_RESPONSE_BYTES:
                    raise ValueError(
                        f"La respuesta excede el límite de {_MAX_RESPONSE_BYTES} bytes. "
                        "Intente con include_images=false."
                    )

                return ReadResult(
                    response=result,
                    resource_type="board",
                    resource_id=board.id,
                    returned_count=1,
                    metadata={
                        "returned_count": 1,
                        "include_images": include_images,
                        "response_truncated": response_truncated,
                    },
                )

        return execute_read_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="get_board",
            capability_type="board",
            audit_resource_type="board",
            audit_resource_id=board_id,
            operation=operation,
        )


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
