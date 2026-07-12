"""Tool MCP de escritura para aristas: create_edge y update_edge.

Crea y actualiza conexiones entre nodos existentes dentro del mismo board,
validando ownership, constraints, puertos y optimistic locking.
"""

import os

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ... import database as _database
from ... import schemas
from ...mcp.mutation_guard import MutationResult, execute_mutating_tool
from ...mcp.write_helpers import (
    build_success,
    require_board_scope,
    require_edge_scope,
    resolve_expected_version,
)
from ...services.edges import create_edge as create_edge_service
from ...services.edges import create_edges_batch as create_edges_batch_service
from ...services.edges import update_edge as update_edge_service
from ...services.errors import OperationLimitExceeded
from ..context import get_context

# Límite configurable para batch de edges
MCP_MAX_EDGES_PER_BATCH: int = int(os.getenv("MCP_MAX_EDGES_PER_BATCH", "200"))


class MCPEdgeInput(BaseModel):
    """Payload del edge que recibe la tool — sin id (se genera server-side)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: schemas.PortRef = Field(alias="from")
    to: schemas.PortRef
    curved: bool = True
    label: str = ""


class MCPCreateEdgePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_id: str
    expected_version: int
    edge: MCPEdgeInput


class MCPEdgeChanges(BaseModel):
    """Cambios parciales permitidos para update_edge.

    Solo label y curved son editables.  No se permite cambiar extremos.
    """
    model_config = ConfigDict(extra="forbid")

    curved: bool | None = None
    label: str | None = None

    @field_validator("curved", mode="before")
    @classmethod
    def _reject_non_bool_curved(cls, v: object) -> object:
        if v is not None and not isinstance(v, bool):
            raise ValueError("curved debe ser un booleano")
        return v


class BatchEdgeItem(BaseModel):
    """Un elemento del batch de creación de edges."""
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(..., min_length=1, max_length=128)
    edge: MCPEdgeInput


class MCPCreateEdgesBatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_id: str
    expected_version: int
    edges: list[BatchEdgeItem] = Field(..., min_length=1, max_length=1_000_000)


class MCPUpdateEdgePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    expected_version: int
    changes: MCPEdgeChanges


def _edge_output(edge: schemas.EdgeSchema, board_id: str) -> dict[str, object]:
    """Convierte un EdgeSchema a dict plano con board_id incluido."""
    d = edge.model_dump(by_alias=True)
    d["board_id"] = board_id
    return d


def _changed_fields(changes: MCPEdgeChanges) -> list[str]:
    """Retorna la lista de campos presentes en *changes*."""
    return [
        field_name
        for field_name in type(changes).model_fields
        if field_name in changes.model_fields_set
    ]


def register(mcp) -> None:
    def _execute_create_edge(
        ctx,
        payload: MCPCreateEdgePayload,
        edge_schema: schemas.EdgeSchema,
    ) -> MutationResult:
        with _database.SessionLocal() as db:
            board = require_board_scope(
                db, ctx, payload.board_id, "edges:create",
            )
            previous_version = resolve_expected_version(
                board, payload.expected_version,
            )
            created = create_edge_service(
                db,
                ctx.user_id,
                board.id,
                edge_schema,
                payload.expected_version,
                board=board,
            )
            board_id = board.id
            board_version = board.version
            edge_output = _edge_output(created, board_id)

        return MutationResult(
            response=build_success(
                data={
                    "edge": edge_output,
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="edge",
            resource_id=created.id,
            affected_count=1,
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "create_edge",
                "changed_field_count": 1,
            },
        )

    def _execute_update_edge(ctx, payload: MCPUpdateEdgePayload) -> MutationResult:
        with _database.SessionLocal() as db:
            edge_obj, board_obj = require_edge_scope(
                db, ctx, payload.edge_id, "edges:update",
            )
            previous_version = resolve_expected_version(
                board_obj, payload.expected_version,
            )
            update_payload = schemas.EdgeUpdate(
                **payload.changes.model_dump(exclude_unset=True),
            )
            updated = update_edge_service(
                db,
                ctx.user_id,
                payload.edge_id,
                update_payload,
                payload.expected_version,
                edge=edge_obj,
                board=board_obj,
            )
            board_id = board_obj.id
            board_version = board_obj.version
            edge_output = _edge_output(updated, board_id)

        changed_fields = _changed_fields(payload.changes)
        return MutationResult(
            response=build_success(
                data={
                    "edge": edge_output,
                    "changed_fields": changed_fields,
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="edge",
            resource_id=updated.id,
            affected_count=1,
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "update_edge",
                "changed_field_count": len(changed_fields),
            },
        )

    def _execute_create_edges_batch(
        ctx,
        payload: MCPCreateEdgesBatchPayload,
        edge_payloads: list[schemas.EdgeSchema],
    ) -> MutationResult:
        with _database.SessionLocal() as db:
            board = require_board_scope(
                db, ctx, payload.board_id, "edges:create",
            )
            previous_version = resolve_expected_version(
                board, payload.expected_version,
            )
            result = create_edges_batch_service(
                db,
                ctx.user_id,
                board.id,
                edge_payloads,
                payload.expected_version,
                board=board,
            )

            edges_out = []
            for i, s in enumerate(result["edges"]):
                edges_out.append({
                    "client_id": payload.edges[i].client_id,
                    "edge": _edge_output(s, board.id),
                })

            created = {
                payload.edges[i].client_id: eid
                for i, eid in result["client_map"].items()
            }
            board_id = board.id
            board_version = board.version

        return MutationResult(
            response=build_success(
                data={
                    "edges": edges_out,
                    "created": created,
                    "created_count": len(edges_out),
                    "previous_version": previous_version,
                    "board_version": board_version,
                }
            ),
            resource_type="board",
            resource_id=board_id,
            affected_count=len(edges_out),
            version_before=previous_version,
            version_after=board_version,
            metadata={
                "operation_kind": "create_edges_batch",
                "created_count": len(edges_out),
                "batch_size": len(payload.edges),
            },
        )

    @mcp.tool(
        name="create_edge",
        description=(
            "Crea una arista entre dos nodos existentes dentro del mismo board. "
            "Acepta board_id, expected_version y edge (con from, to, curved, label). "
            "Requiere scope edges:create. "
            "Valida que ambos nodos y puertos existan. "
            "Respeta ownership, constraints y optimistic locking."
        ),
    )
    def create_edge(
        board_id: str,
        expected_version: int,
        edge: dict,
    ) -> dict:
        """Crea una arista reutilizando el servicio de dominio."""
        payload = MCPCreateEdgePayload(
            board_id=board_id,
            expected_version=expected_version,
            edge=edge,
        )

        # Servicio espera EdgeSchema con id=None para generar server-side
        edge_schema = schemas.EdgeSchema(
            id=None,
            from_=payload.edge.from_,
            to=payload.edge.to,
            curved=payload.edge.curved,
            label=payload.edge.label,
        )

        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="create_edge",
            category="write",
            capability_type="edge",
            audit_resource_type="board",
            audit_resource_id=payload.board_id,
            operation=lambda: _execute_create_edge(ctx, payload, edge_schema),
        )

    @mcp.tool(
        name="update_edge",
        description=(
            "Actualiza parcialmente una arista existente autorizada. "
            "Acepta edge_id, expected_version y changes (label, curved). "
            "No permite modificar los extremos (from, to). "
            "Requiere scope edges:update. "
            "Respeta ownership, constraints y optimistic locking."
        ),
    )
    def update_edge(
        edge_id: str,
        expected_version: int,
        changes: dict,
    ) -> dict:
        """Actualiza parcialmente una arista."""
        payload = MCPUpdateEdgePayload(
            edge_id=edge_id,
            expected_version=expected_version,
            changes=changes,
        )

        if not payload.changes.model_fields_set:
            raise ValueError("Debe especificar al menos un cambio")

        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="update_edge",
            category="write",
            capability_type="edge",
            audit_resource_type="edge",
            audit_resource_id=payload.edge_id,
            operation=lambda: _execute_update_edge(ctx, payload),
        )

    @mcp.tool(
        name="create_edges_batch",
        description=(
            "Crea múltiples aristas dentro de un mismo board en una única transacción. "
            "Acepta board_id, expected_version y una lista de edges con client_id. "
            "Cada edge referencia nodos existentes por su ID real y puertos. "
            "Máximo {} edges por batch. "
            "Requiere scope edges:create. "
            "Respeta ownership, constraints y optimistic locking. "
            "Un fallo revierte la operación completa."
        ).format(MCP_MAX_EDGES_PER_BATCH),
    )
    def create_edges_batch(
        board_id: str,
        expected_version: int,
        edges: list[BatchEdgeItem],
    ) -> dict:
        """Crea múltiples aristas atómicamente."""
        payload = MCPCreateEdgesBatchPayload(
            board_id=board_id,
            expected_version=expected_version,
            edges=edges,
        )

        # Validar límite
        if len(payload.edges) > MCP_MAX_EDGES_PER_BATCH:
            raise ValueError(
                f"El batch supera el límite máximo de {MCP_MAX_EDGES_PER_BATCH} edges. "
                f"Recibidos: {len(payload.edges)}"
            )

        # Validar unicidad de client_id
        client_ids = [item.client_id for item in payload.edges]
        if len(client_ids) != len(set(client_ids)):
            seen = set()
            dupes = {cid for cid in client_ids if cid in seen or seen.add(cid)}
            raise ValueError(
                f"client_id duplicado en el batch: {', '.join(sorted(dupes))}"
            )

        # Convertir todos los edges a EdgeSchema
        edge_payloads: list[schemas.EdgeSchema] = []
        for item in payload.edges:
            edge_payloads.append(
                schemas.EdgeSchema(
                    id=None,
                    from_=item.edge.from_,
                    to=item.edge.to,
                    curved=item.edge.curved,
                    label=item.edge.label,
                )
            )

        ctx = get_context()
        return execute_mutating_tool(
            _database.SessionLocal,
            ctx=ctx,
            tool_name="create_edges_batch",
            category="batch",
            capability_type="batch_edges",
            audit_resource_type="board",
            audit_resource_id=payload.board_id,
            operation=lambda: _execute_create_edges_batch(ctx, payload, edge_payloads),
        )
