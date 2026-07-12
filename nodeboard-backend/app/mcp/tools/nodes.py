"""Tools MCP de nodes.

Incluye lectura individual y escritura controlada para crear nodos
respetando ownership, constraints y optimistic locking.
"""
import logging
import os
from typing import Any, Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ... import schemas
from ... import database as _database
from ...mcp.mutation_guard import MutationResult, execute_mutating_tool
from ...mcp.auth import require_scope, enforce_board_constraint
from ...mcp.node_validation import MCPNodeInput, validate_update_changes
from ...mcp.read_guard import ReadResult, execute_read_tool
from ...mcp.write_helpers import (
    build_success,
    require_board_scope,
    require_node_scope,
    resolve_expected_version,
)
from ...services.authorization import get_owned_node
from ...services.errors import OperationLimitExceeded, ResourceNotFound
from ...services.nodes import create_node as create_node_service, create_nodes_batch as create_nodes_batch_service, update_node as update_node_service, move_node as move_node_service
from ..context import get_context

# Límite configurable para batch de nodes
MCP_MAX_NODES_PER_BATCH: int = int(os.getenv("MCP_MAX_NODES_PER_BATCH", "100"))

logger = logging.getLogger(__name__)


class MCPCreateNodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_id: str
    expected_version: int
    node: MCPNodeInput


class MCPMoveNodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    x: Annotated[float, Field(allow_inf_nan=False)]
    y: Annotated[float, Field(allow_inf_nan=False)]
    expected_version: int

    @field_validator("x", "y", mode="before")
    @classmethod
    def _reject_bool(cls, v: object) -> object:
        if isinstance(v, bool):
            raise ValueError(f"Coordenada booleana no permitida")
        return v


class MCPUpdateNodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    expected_version: int
    changes: dict[str, Any]


class BatchNodeItem(BaseModel):
    """Un elemento del batch de creación de nodos."""
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(..., min_length=1, max_length=128)
    node: MCPNodeInput


class MCPCreateNodesBatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_id: str
    expected_version: int
    nodes: list[BatchNodeItem] = Field(..., min_length=1, max_length=1_000_000)

    @field_validator("nodes")
    @classmethod
    def _validate_nodes_list(cls, v: list[BatchNodeItem]) -> list[BatchNodeItem]:
        if len(v) < 1:
            raise ValueError("La lista de nodos no puede estar vacía")
        return v


def _node_to_output(node: schemas.NodeSchema, board_id: str) -> dict[str, object]:
    payload = node.model_dump(by_alias=True)
    payload["board_id"] = board_id
    return payload


def register(mcp) -> None:
    def _execute_create_node(
        ctx,
        payload: MCPCreateNodePayload,
        node_payload: schemas.NodeSchema,
    ) -> MutationResult:
        with _database.SessionLocal() as db:
            board = require_board_scope(db, ctx, payload.board_id, "nodes:create")
            previous_version = resolve_expected_version(
                board, payload.expected_version
            )
            created = create_node_service(
                db,
                ctx.user_id,
                board.id,
                node_payload,
                payload.expected_version,
                board=board,
            )
            board_id = board.id
            board_version = board.version
            node_output = _node_to_output(created, board_id)

        return MutationResult(
            response=build_success(
                data={
                    "node": node_output,
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="node",
            resource_id=created.id,
            affected_count=1,
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "create_node",
                "changed_field_count": 1,
            },
        )

    def _execute_update_node(ctx, payload: MCPUpdateNodePayload) -> MutationResult:
        with _database.SessionLocal() as db:
            node, board = require_node_scope(
                db,
                ctx,
                payload.node_id,
                "nodes:update",
            )
            previous_version = resolve_expected_version(
                board, payload.expected_version
            )
            update_payload, changed_fields = validate_update_changes(
                node.type,
                payload.changes,
            )
            updated = update_node_service(
                db,
                ctx.user_id,
                payload.node_id,
                update_payload,
                payload.expected_version,
                node=node,
                board=board,
            )
            board_id = board.id
            board_version = board.version
            node_output = _node_to_output(updated, board_id)

        return MutationResult(
            response=build_success(
                data={
                    "node": node_output,
                    "changed_fields": changed_fields,
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="node",
            resource_id=updated.id,
            affected_count=1,
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "update_node",
                "changed_field_count": len(changed_fields),
            },
        )

    def _execute_move_node(ctx, payload: MCPMoveNodePayload) -> MutationResult:
        with _database.SessionLocal() as db:
            node_obj, board_obj = require_node_scope(
                db,
                ctx,
                payload.node_id,
                "nodes:update",
            )
            previous_version = resolve_expected_version(
                board_obj, payload.expected_version
            )
            updated, prev_pos_svc, new_pos = move_node_service(
                db,
                ctx.user_id,
                payload.node_id,
                payload.x,
                payload.y,
                payload.expected_version,
                node=node_obj,
                board=board_obj,
            )
            board_id = board_obj.id
            board_version = board_obj.version
            node_output = _node_to_output(updated, board_id)

        return MutationResult(
            response=build_success(
                data={
                    "node": node_output,
                    "previous_position": prev_pos_svc,
                    "position": new_pos,
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="node",
            resource_id=updated.id,
            affected_count=1,
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "move_node",
                "changed_field_count": 2,
            },
        )

    def _execute_create_nodes_batch(
        ctx,
        payload: MCPCreateNodesBatchPayload,
        node_payloads: list[schemas.NodeSchema],
    ) -> MutationResult:
        with _database.SessionLocal() as db:
            board = require_board_scope(db, ctx, payload.board_id, "nodes:create")
            previous_version = resolve_expected_version(
                board, payload.expected_version
            )
            result = create_nodes_batch_service(
                db,
                ctx.user_id,
                board.id,
                node_payloads,
                payload.expected_version,
                board=board,
            )

            nodes_out = []
            for i, s in enumerate(result["nodes"]):
                nodes_out.append({
                    "client_id": payload.nodes[i].client_id,
                    "node": _node_to_output(s, board.id),
                })

            created = {
                payload.nodes[i].client_id: nid
                for i, nid in result["client_map"].items()
            }
            board_id = board.id
            board_version = board.version

        return MutationResult(
            response=build_success(
                data={
                    "nodes": nodes_out,
                    "created": created,
                    "created_count": len(nodes_out),
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="board",
            resource_id=board_id,
            affected_count=len(nodes_out),
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "create_nodes_batch",
                "created_count": len(nodes_out),
                "batch_size": len(payload.nodes),
            },
        )

    @mcp.tool(
        name="create_node",
        description=(
            "Crea un nodo dentro de un board autorizado. "
            "Acepta board_id, expected_version y node. "
            "Los tipos soportados son card y timeline. "
            "Requiere scope nodes:create. "
            "Respeta ownership, constraints y optimistic locking."
        ),
    )
    def create_node(
        board_id: str,
        expected_version: int,
        node: MCPNodeInput,
    ) -> dict:
        """Crea un nodo reutilizando el servicio de dominio."""
        try:
            payload = MCPCreateNodePayload(
                board_id=board_id,
                expected_version=expected_version,
                node=node,
            )
            node_payload = schemas.NodeSchema(
                id=None,
                **payload.node.model_dump(),
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="create_node",
            category="write",
            capability_type="node",
            audit_resource_type="board",
            audit_resource_id=payload.board_id,
            operation=lambda: _execute_create_node(ctx, payload, node_payload),
        )

    @mcp.tool(
        name="update_node",
        description=(
            "Actualiza parcialmente un nodo existente autorizado. "
            "Acepta node_id, expected_version y changes. "
            "Solo modifica contenido y propiedades semánticas; no permite x ni y. "
            "Requiere scope nodes:update. "
            "Respeta ownership, constraints y optimistic locking."
        ),
    )
    def update_node(
        node_id: str,
        expected_version: int,
        changes: dict[str, Any],
    ) -> dict:
        """Actualiza parcialmente un nodo reutilizando el servicio de dominio."""
        try:
            payload = MCPUpdateNodePayload(
                node_id=node_id,
                expected_version=expected_version,
                changes=changes,
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="update_node",
            category="write",
            capability_type="node",
            audit_resource_type="node",
            audit_resource_id=payload.node_id,
            operation=lambda: _execute_update_node(ctx, payload),
        )

    @mcp.tool(
        name="move_node",
        description=(
            "Mueve un nodo existente a una nueva posición. "
            "Solo modifica las coordenadas x e y. "
            "Requiere node_id, x, y y expected_version. "
            "Requiere scope nodes:update. "
            "Respeta ownership, constraints y optimistic locking."
        ),
    )
    def move_node(
        node_id: str,
        x: float,
        y: float,
        expected_version: int,
    ) -> dict:
        """Mueve un nodo a una nueva posición."""
        try:
            payload = MCPMoveNodePayload(
                node_id=node_id,
                x=x,
                y=y,
                expected_version=expected_version,
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="move_node",
            category="write",
            capability_type="node",
            audit_resource_type="node",
            audit_resource_id=payload.node_id,
            operation=lambda: _execute_move_node(ctx, payload),
        )

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

        def operation() -> ReadResult:
            require_scope(ctx, "nodes:read")

            with _database.SessionLocal() as db:
                node = get_owned_node(db, ctx.user_id, node_id)
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

                return ReadResult(
                    response=d,
                    resource_type="node",
                    resource_id=node.id,
                    returned_count=1,
                    metadata={
                        "returned_count": 1,
                        "include_images": include_images,
                    },
                )

        return execute_read_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="get_node",
            capability_type="node",
            audit_resource_type="node",
            audit_resource_id=node_id,
            operation=operation,
        )

    @mcp.tool(
        name="create_nodes_batch",
        description=(
            "Crea múltiples nodos dentro de un mismo board en una única transacción. "
            "Acepta board_id, expected_version y una lista de nodes con client_id. "
            "Los tipos soportados son card y timeline. "
            "Máximo {} nodos por batch. "
            "Requiere scope nodes:create. "
            "Respeta ownership, constraints y optimistic locking. "
            "Todos los nodos se crean en un único board, "
            "la versión incrementa una sola vez y "
            "un fallo revierte la operación completa."
        ).format(MCP_MAX_NODES_PER_BATCH),
    )
    def create_nodes_batch(
        board_id: str,
        expected_version: int,
        nodes: list[BatchNodeItem],
    ) -> dict:
        """Crea múltiples nodos atómicamente."""
        try:
            payload = MCPCreateNodesBatchPayload(
                board_id=board_id,
                expected_version=expected_version,
                nodes=nodes,
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        # Validar límite
        if len(payload.nodes) > MCP_MAX_NODES_PER_BATCH:
            raise ValueError(
                f"El batch supera el límite máximo de {MCP_MAX_NODES_PER_BATCH} nodos. "
                f"Recibidos: {len(payload.nodes)}"
            )

        # Validar unicidad de client_id
        client_ids = [item.client_id for item in payload.nodes]
        if len(client_ids) != len(set(client_ids)):
            seen = set()
            dupes = {cid for cid in client_ids if cid in seen or seen.add(cid)}
            raise ValueError(
                f"client_id duplicado en el batch: {', '.join(sorted(dupes))}"
            )

        # Convertir todos los nodos a NodeSchema
        node_payloads: list[schemas.NodeSchema] = []
        for item in payload.nodes:
            node_payloads.append(
                schemas.NodeSchema(
                    id=None,
                    **item.node.model_dump(),
                )
            )

        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="create_nodes_batch",
            category="batch",
            capability_type="batch_nodes",
            audit_resource_type="board",
            audit_resource_id=payload.board_id,
            operation=lambda: _execute_create_nodes_batch(ctx, payload, node_payloads),
        )
