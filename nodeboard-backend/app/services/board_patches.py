"""Planificador, validador y ejecutor de patches de board.

``apply_board_patch`` permite agrupar múltiples operaciones sobre
nodes y edges en una única transacción.  Soporta dry-run (validación
sin escritura) y ejecución real (transaccional y atómica).

Operaciones soportadas:
- create_node
- update_node
- move_node
- create_edge
- update_edge
"""

from __future__ import annotations

import logging
import os
import sys
import time
import uuid
from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models, schemas
from ..mcp.node_validation import (
    MCPCardNodeChanges,
    MCPNodeInput,
    MCPTimelineNodeChanges,
    validate_update_changes,
)
from ..mcp.errors import ConstraintViolation, InsufficientScope
from ..services.authorization import get_owned_board
from ..services.edges import _build_edge_model, _validate_edge_endpoints
from ..services.errors import (
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStateUncertain,
    OperationLimitExceeded,
    RateLimitExceeded,
    ResourceNotFound,
    ValidationFailure,
    VersionConflict,
)
from ..services.mcp_idempotency import (
    begin_idempotent_operation,
    complete_idempotent_operation,
    fail_idempotent_operation,
    validate_idempotency_key,
)
from ..services.mcp_audit import (
    MCP_AUDIT_STATUS_ERROR,
    MCP_AUDIT_STATUS_REPLAY,
    MCP_AUDIT_STATUS_STATE_UNCERTAIN,
    MCP_AUDIT_STATUS_SUCCESS,
    create_audit_entry,
)
from ..services.nodes import _build_node_model, _new_id

MCP_MAX_PATCH_OPERATIONS: int = int(os.getenv("MCP_MAX_PATCH_OPERATIONS", "100"))
APPLY_BOARD_PATCH_TOOL_NAME = "apply_board_patch"
IDEMPOTENCY_ERROR_CODE = "IDEMPOTENCY_STATE_UNCERTAIN"
logger = logging.getLogger(__name__)


def _build_apply_board_patch_audit_metadata(
    *,
    operation_count: int,
    summary: dict[str, int],
    dry_run: bool,
    original_affected_count: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "operation_count": operation_count,
        "summary": summary,
        "dry_run": dry_run,
    }
    if original_affected_count is not None:
        metadata["original_affected_count"] = original_affected_count
    return metadata


def _audit_error_code(error: BaseException) -> str:
    if isinstance(error, ValidationFailure):
        return "VALIDATION_FAILURE"
    if isinstance(error, ResourceNotFound):
        return "RESOURCE_NOT_FOUND"
    if isinstance(error, VersionConflict):
        return "VERSION_CONFLICT"
    if isinstance(error, OperationLimitExceeded):
        return "OPERATION_LIMIT_EXCEEDED"
    if isinstance(error, IdempotencyConflict):
        return "IDEMPOTENCY_CONFLICT"
    if isinstance(error, IdempotencyInProgress):
        return "IDEMPOTENCY_IN_PROGRESS"
    if isinstance(error, IdempotencyStateUncertain):
        return "IDEMPOTENCY_STATE_UNCERTAIN"
    if isinstance(error, RateLimitExceeded):
        return "RATE_LIMIT_EXCEEDED"
    if isinstance(error, (ConstraintViolation, InsufficientScope)):
        return "FORBIDDEN_RESOURCE"
    return "INTERNAL_ERROR"


def _persist_audit_entry(
    session_factory: Callable[[], Session],
    *,
    user_id: str | None,
    token_id: str | None,
    client_name: str | None,
    tool_name: str,
    request_id: str | None,
    resource_type: str,
    resource_id: str | None,
    status: str,
    error_code: str | None = None,
    affected_count: int = 0,
    version_before: int | None = None,
    version_after: int | None = None,
    duration_ms: int = 0,
    is_replay: bool = False,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        with session_factory() as audit_db:
            create_audit_entry(
                audit_db,
                user_id=user_id,
                token_id=token_id,
                client_name=client_name,
                tool_name=tool_name,
                request_id=request_id,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status,
                error_code=error_code,
                affected_count=affected_count,
                version_before=version_before,
                version_after=version_after,
                duration_ms=duration_ms,
                is_replay=is_replay,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
    except Exception:
        logger.exception(
            "mcp audit persistence failed tool=%s request_id=%s status=%s resource_type=%s resource_id=%s",
            tool_name,
            request_id,
            status,
            resource_type,
            resource_id,
        )


# ------------------------------------------------------------------
# Endpoint de edge: nodeId o clientId (excluyentes)
# ------------------------------------------------------------------


class EdgeEndpointNodeRef(BaseModel):
    """Endpoint que referencia un node existente por su ID real."""
    model_config = ConfigDict(extra="forbid")

    nodeId: str = Field(..., min_length=1)
    portId: str = Field(..., min_length=1)


class EdgeEndpointClientRef(BaseModel):
    """Endpoint que referencia un node creado en el patch por su client_id."""
    model_config = ConfigDict(extra="forbid")

    clientId: str = Field(..., min_length=1, max_length=128)
    portId: str = Field(..., min_length=1)


EdgeEndpoint = Annotated[
    EdgeEndpointNodeRef | EdgeEndpointClientRef,
    Field(discriminator=False),
]


# ------------------------------------------------------------------
# Operaciones discriminadas
# ------------------------------------------------------------------


class PatchCreateNodeOperation(BaseModel):
    """Creación de un nodo dentro del patch."""
    model_config = ConfigDict(extra="forbid")

    op: Literal["create_node"]
    client_id: str = Field(..., min_length=1, max_length=128)
    node: MCPNodeInput


class PatchUpdateNodeOperation(BaseModel):
    """Actualización parcial de un nodo existente."""
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_node"]
    node_id: str = Field(..., min_length=1)
    changes: dict[str, Any]


class PatchMoveNodeOperation(BaseModel):
    """Movimiento de un nodo existente a nuevas coordenadas."""
    model_config = ConfigDict(extra="forbid")

    op: Literal["move_node"]
    node_id: str = Field(..., min_length=1)
    x: Annotated[float, Field(allow_inf_nan=False)]
    y: Annotated[float, Field(allow_inf_nan=False)]

    @field_validator("x", "y", mode="before")
    @classmethod
    def _reject_bool(cls, v: object) -> object:
        if isinstance(v, bool):
            raise ValueError("Coordenada booleana no permitida")
        return v


class PatchCreateEdgeOperation(BaseModel):
    """Creación de un edge dentro del patch."""
    model_config = ConfigDict(extra="forbid")

    op: Literal["create_edge"]
    client_id: str = Field(..., min_length=1, max_length=128)
    edge: dict[str, Any]


class PatchUpdateEdgeOperation(BaseModel):
    """Actualización parcial de un edge existente."""
    model_config = ConfigDict(extra="forbid")

    op: Literal["update_edge"]
    edge_id: str = Field(..., min_length=1)
    changes: dict[str, Any]


PatchOperation = Annotated[
    PatchCreateNodeOperation
    | PatchUpdateNodeOperation
    | PatchMoveNodeOperation
    | PatchCreateEdgeOperation
    | PatchUpdateEdgeOperation,
    Field(discriminator="op"),
]


# ------------------------------------------------------------------
# Payload principal del patch
# ------------------------------------------------------------------


class BoardPatchPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_id: str
    expected_version: int
    dry_run: bool
    idempotency_key: str | None = None
    operations: list[PatchOperation] = Field(..., min_length=1, max_length=1_000_000)


# ------------------------------------------------------------------
# Plan de operación (resultado de dry-run)
# ------------------------------------------------------------------


class PlanOperationStatus(BaseModel):
    index: int
    op: str
    status: str = "valid"


class ClientReference(BaseModel):
    resource_type: str
    status: str = "will_create"


class BoardPatchPlan(BaseModel):
    dry_run: bool
    valid: bool
    board_id: str
    current_version: int
    predicted_version: int
    operation_count: int
    summary: dict[str, int]
    client_references: dict[str, ClientReference]
    operations: list[PlanOperationStatus]
    warnings: list[str]


# ------------------------------------------------------------------
# Resultado de ejecución
# ------------------------------------------------------------------


class ExecutedOperation(BaseModel):
    """Resultado de una operación individual ejecutada."""
    index: int
    op: str
    status: str = "applied"
    resource_id: str | None = None


class CreatedResource(BaseModel):
    """Recurso creado durante la ejecución del patch."""
    resource_type: str
    id: str


class BoardPatchExecutionResult(BaseModel):
    """Resultado estructurado de un patch ejecutado."""
    dry_run: bool = False
    applied: bool = True
    board_id: str
    previous_version: int
    board_version: int
    operation_count: int
    summary: dict[str, int]
    created: dict[str, CreatedResource] = Field(default_factory=dict)
    operations: list[ExecutedOperation]


def build_execution_response(result: BoardPatchExecutionResult) -> dict[str, object]:
    return {
        "ok": True,
        "data": result.model_dump(),
    }


def build_plan_response(plan: BoardPatchPlan) -> dict[str, object]:
    return {
        "ok": True,
        "data": plan.model_dump(),
    }


def build_apply_board_patch_idempotency_payload(
    payload: BoardPatchPayload,
) -> dict[str, Any]:
    return {
        "board_id": payload.board_id,
        "expected_version": payload.expected_version,
        "dry_run": payload.dry_run,
        "operations": payload.model_dump(
            mode="json",
            by_alias=True,
            exclude={"board_id", "expected_version", "dry_run", "idempotency_key"},
        )["operations"],
    }


def validate_apply_board_patch_contract(payload: BoardPatchPayload) -> None:
    if payload.dry_run:
        if payload.idempotency_key is not None:
            raise ValidationFailure(
                "idempotency_key no está permitida cuando dry_run=true"
            )
        return

    if payload.idempotency_key is None:
        raise ValidationFailure(
            "idempotency_key es obligatoria cuando dry_run=false"
        )

    try:
        validate_idempotency_key(payload.idempotency_key)
    except ValueError as exc:
        raise ValidationFailure(str(exc)) from exc


# ------------------------------------------------------------------
# Scopes requeridos por operación
# ------------------------------------------------------------------

_OP_SCOPES: dict[str, str] = {
    "create_node": "nodes:create",
    "update_node": "nodes:update",
    "move_node": "nodes:update",
    "create_edge": "edges:create",
    "update_edge": "edges:update",
}


def required_scopes(operations: list[PatchOperation]) -> set[str]:
    """Retorna todos los scopes necesarios para las operaciones indicadas."""
    scopes: set[str] = set()
    for op in operations:
        scope = _OP_SCOPES.get(op.op)
        if scope:
            scopes.add(scope)
    return scopes


# ------------------------------------------------------------------
# Ejecución transaccional
# ------------------------------------------------------------------


def _load_existing_resources(
    db: Session,
    board_id: str,
    operations: list[PatchOperation],
) -> tuple[dict[str, models.Node], dict[str, models.Edge]]:
    """Precarga los nodos y edges existentes referenciados por las operaciones."""
    existing_nodes_map: dict[str, models.Node] = {}
    existing_edges_map: dict[str, models.Edge] = {}
    node_ids_to_load: set[str] = set()
    edge_ids_to_load: set[str] = set()

    for op in operations:
        if isinstance(op, (PatchUpdateNodeOperation, PatchMoveNodeOperation)):
            node_ids_to_load.add(op.node_id)
        elif isinstance(op, PatchCreateEdgeOperation):
            edge_from = op.edge.get("from", {})
            edge_to = op.edge.get("to", {})
            if "nodeId" in edge_from:
                node_ids_to_load.add(edge_from["nodeId"])
            if "nodeId" in edge_to:
                node_ids_to_load.add(edge_to["nodeId"])
        elif isinstance(op, PatchUpdateEdgeOperation):
            edge_ids_to_load.add(op.edge_id)

    if node_ids_to_load:
        nodes = db.scalars(
            select(models.Node).where(
                models.Node.id.in_(node_ids_to_load),
                models.Node.board_id == board_id,
            )
        ).all()
        for n in nodes:
            existing_nodes_map[n.id] = n

    if edge_ids_to_load:
        edges = db.scalars(
            select(models.Edge).where(
                models.Edge.id.in_(edge_ids_to_load),
                models.Edge.board_id == board_id,
            )
        ).all()
        for e in edges:
            existing_edges_map[e.id] = e

    return existing_nodes_map, existing_edges_map


def execute_board_patch(
    db: Session,
    user_id: str,
    payload: BoardPatchPayload,
    board: models.Board | None = None,
) -> BoardPatchExecutionResult:
    """Ejecuta un patch de board de forma transaccional y atómica.

    1. Construye y valida el plan completo (reutilizando build_board_patch_plan).
    2. Genera IDs reales server-side para todas las creaciones.
    3. Ejecuta las operaciones en orden dentro de una única transacción.
    4. Aplica optimistic locking una sola vez.
    5. Commit único o rollback total ante cualquier error.

    Parameters
    ----------
    db : Session
        Sesión de SQLAlchemy.
    user_id : str
        ID del usuario autenticado.
    payload : BoardPatchPayload
        Payload del patch validado externamente.
    board : models.Board | None
        Board precargado (opcional, evita recarga).

    Returns
    -------
    BoardPatchExecutionResult
        Resultado estructurado con IDs reales, resumen y estado por operación.

    Raises
    ------
    VersionConflict
        Si el board fue modificado por otro cliente.
    ValidationFailure
        Si alguna operación es inválida.
    """
    # 1. Construir plan (valida todo: versión, estructura, scopes lógicos,
    #    referencias, puertos, límite de operaciones)
    plan = build_board_patch_plan(db, user_id, payload, board=board)
    board = board or get_owned_board(db, user_id, payload.board_id)

    # 2. Precargar recursos existentes
    existing_nodes_map, existing_edges_map = _load_existing_resources(
        db, board.id, payload.operations,
    )

    # Fase A — Preparación: generar IDs reales y construir modelos de nodos
    created_node_ids: dict[str, str] = {}   # client_id -> real node id
    created_node_models: dict[str, models.Node] = {}  # client_id -> ORM model
    created_edge_ids: dict[str, str] = {}   # client_id -> real edge id

    for op in payload.operations:
        if isinstance(op, PatchCreateNodeOperation):
            real_id = _new_id()
            created_node_ids[op.client_id] = real_id
            node_schema = schemas.NodeSchema(
                id=real_id,
                **op.node.model_dump(),
            )
            node_model = _build_node_model(board.id, node_schema)
            db.add(node_model)
            created_node_models[op.client_id] = node_model

        elif isinstance(op, PatchCreateEdgeOperation):
            created_edge_ids[op.client_id] = _new_id()

    # Flush para que los nodos creados tengan IDs y sean referenciables
    # por edges posteriores (manteniendo la transacción activa)
    db.flush()

    # Mapa combinado: todos los nodos (existentes + creados)
    all_nodes_map: dict[str, models.Node] = dict(existing_nodes_map)
    for node_model in created_node_models.values():
        all_nodes_map[node_model.id] = node_model

    result_ops: list[ExecutedOperation] = []

    try:
        # Fase B — Ejecución lógica en orden original
        for i, op in enumerate(payload.operations):
            if isinstance(op, PatchCreateNodeOperation):
                # Ya creado en Fase A — solo registrar resultado
                result_ops.append(ExecutedOperation(
                    index=i, op="create_node", status="applied",
                    resource_id=created_node_ids[op.client_id],
                ))

            elif isinstance(op, PatchUpdateNodeOperation):
                node = existing_nodes_map[op.node_id]
                update_payload, _ = validate_update_changes(node.type, op.changes)
                data = update_payload.model_dump(exclude_unset=True)
                for field, value in data.items():
                    if field == "tags" and value is None:
                        setattr(node, field, [])
                    else:
                        setattr(node, field, value)
                result_ops.append(ExecutedOperation(
                    index=i, op="update_node", status="applied",
                    resource_id=op.node_id,
                ))

            elif isinstance(op, PatchMoveNodeOperation):
                node = existing_nodes_map[op.node_id]
                node.x = op.x
                node.y = op.y
                result_ops.append(ExecutedOperation(
                    index=i, op="move_node", status="applied",
                    resource_id=op.node_id,
                ))

            elif isinstance(op, PatchCreateEdgeOperation):
                edge_data = op.edge
                from_endpoint = _parse_edge_endpoint(edge_data["from"])
                to_endpoint = _parse_edge_endpoint(edge_data["to"])

                # Resolver endpoints: clientId -> real nodeId
                if isinstance(from_endpoint, EdgeEndpointClientRef):
                    from_node_id = created_node_ids[from_endpoint.clientId]
                else:
                    from_node_id = from_endpoint.nodeId

                if isinstance(to_endpoint, EdgeEndpointClientRef):
                    to_node_id = created_node_ids[to_endpoint.clientId]
                else:
                    to_node_id = to_endpoint.nodeId

                # Construir schema de edge para validación y persistencia
                edge_schema = schemas.EdgeSchema(
                    id=created_edge_ids[op.client_id],
                    **{"from": {"nodeId": from_node_id, "portId": from_endpoint.portId},
                       "to": {"nodeId": to_node_id, "portId": to_endpoint.portId},
                       "curved": edge_data.get("curved", True),
                       "label": edge_data.get("label", "")},
                )

                # Validar endpoints contra los modelos reales (ORM)
                board_nodes_list = list(all_nodes_map.values())
                _validate_edge_endpoints(board_nodes_list, edge_schema)

                # Construir modelo ORM y agregarlo a la sesión
                edge_model = _build_edge_model(board.id, edge_schema)
                db.add(edge_model)

                result_ops.append(ExecutedOperation(
                    index=i, op="create_edge", status="applied",
                    resource_id=created_edge_ids[op.client_id],
                ))

            elif isinstance(op, PatchUpdateEdgeOperation):
                edge = existing_edges_map[op.edge_id]
                if "curved" in op.changes:
                    edge.curved = op.changes["curved"]
                if "label" in op.changes:
                    edge.label = op.changes["label"] if op.changes["label"] is not None else ""
                result_ops.append(ExecutedOperation(
                    index=i, op="update_edge", status="applied",
                    resource_id=op.edge_id,
                ))

        # 3. Optimistic locking: incrementar versión exactamente una vez
        now = models._now()
        result = db.execute(
            update(models.Board)
            .where(
                models.Board.id == board.id,
                models.Board.version == payload.expected_version,
            )
            .values(version=models.Board.version + 1, updated_at=now)
        )
        if result.rowcount == 0:
            db.rollback()
            current_board = db.get(models.Board, board.id)
            actual_version = current_board.version if current_board else board.version
            raise VersionConflict(
                board_id=board.id,
                expected_version=payload.expected_version,
                current_version=actual_version,
            )

        # 4. Commit único
        db.commit()

    except (
        ResourceNotFound,
        ValidationFailure,
        VersionConflict,
        OperationLimitExceeded,
    ):
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    # 5. Construir respuesta estructurada
    created_resources: dict[str, CreatedResource] = {}
    for cid, rid in created_node_ids.items():
        created_resources[cid] = CreatedResource(resource_type="node", id=rid)
    for cid, rid in created_edge_ids.items():
        created_resources[cid] = CreatedResource(resource_type="edge", id=rid)

    return BoardPatchExecutionResult(
        dry_run=False,
        applied=True,
        board_id=board.id,
        previous_version=plan.current_version,
        board_version=board.version,
        operation_count=plan.operation_count,
        summary=plan.summary,
        created=created_resources,
        operations=result_ops,
    )


def execute_idempotent_board_patch(
    session_factory: Callable[[], Session],
    *,
    user_id: str,
    token_id: str,
    payload: BoardPatchPayload,
    request_id: str | None = None,
    client_name: str | None = None,
    scope_validator: Callable[[list[PatchOperation]], None] | None = None,
    board_loader: Callable[[Session], models.Board] | None = None,
    cleanup_exceptions: tuple[type[BaseException], ...] = (),
) -> dict[str, object]:
    """Orquesta reserva idempotente, ejecución del patch y completado.

    La reserva, la ejecución de negocio y el completado del registro usan
    sesiones separadas para evitar que un rollback posterior borre la reserva.
    """
    validate_apply_board_patch_contract(payload)
    if payload.dry_run:
        raise ValidationFailure(
            "execute_idempotent_board_patch solo admite dry_run=false"
        )

    start = time.perf_counter()
    audit_metadata = _build_apply_board_patch_audit_metadata(
        operation_count=len(payload.operations),
        summary={
            "nodes_created": 0,
            "nodes_updated": 0,
            "nodes_moved": 0,
            "edges_created": 0,
            "edges_updated": 0,
        },
        dry_run=False,
    )

    with session_factory() as reserve_db:
        try:
            begin_result = begin_idempotent_operation(
                reserve_db,
                user_id=user_id,
                token_id=token_id,
                tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
                idempotency_key=payload.idempotency_key,
                payload=build_apply_board_patch_idempotency_payload(payload),
                recover_expired_in_progress=False,
            )
        except (IdempotencyConflict, IdempotencyInProgress, IdempotencyStateUncertain) as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            status = (
                MCP_AUDIT_STATUS_STATE_UNCERTAIN
                if isinstance(exc, IdempotencyStateUncertain)
                else MCP_AUDIT_STATUS_ERROR
            )
            if isinstance(exc, IdempotencyStateUncertain):
                logger.warning(
                    "mcp idempotency state uncertain tool=%s request_id=%s board_id=%s",
                    APPLY_BOARD_PATCH_TOOL_NAME,
                    request_id,
                    payload.board_id,
                )
            _persist_audit_entry(
                session_factory,
                user_id=user_id,
                token_id=token_id,
                client_name=client_name,
                tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
                request_id=request_id,
                resource_type="board",
                resource_id=payload.board_id,
                status=status,
                error_code=_audit_error_code(exc),
                affected_count=0,
                version_before=payload.expected_version,
                version_after=None,
                duration_ms=duration_ms,
                is_replay=False,
                idempotency_key=payload.idempotency_key,
                metadata=audit_metadata,
            )
            raise

    if begin_result.status == "replay":
        response_json = begin_result.response_json or {}
        duration_ms = int((time.perf_counter() - start) * 1000)
        replay_summary = (
            response_json.get("data", {}).get("summary", {})
            if isinstance(response_json, dict)
            else {}
        )
        replay_operation_count = (
            response_json.get("data", {}).get("operation_count", len(payload.operations))
            if isinstance(response_json, dict)
            else len(payload.operations)
        )
        original_before = begin_result.record.resource_version_before
        original_after = begin_result.record.resource_version_after
        _persist_audit_entry(
            session_factory,
            user_id=user_id,
            token_id=token_id,
            client_name=client_name,
            tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
            request_id=request_id,
            resource_type="board",
            resource_id=payload.board_id,
            status=MCP_AUDIT_STATUS_REPLAY,
            error_code=None,
            affected_count=0,
            version_before=original_before,
            version_after=original_after,
            duration_ms=duration_ms,
            is_replay=True,
            idempotency_key=payload.idempotency_key,
            metadata=_build_apply_board_patch_audit_metadata(
                operation_count=int(replay_operation_count),
                summary=replay_summary if isinstance(replay_summary, dict) else {},
                dry_run=False,
                original_affected_count=int(replay_operation_count),
            ),
        )
        return response_json

    request_hash = begin_result.request_hash
    recoverable_errors = (
        ResourceNotFound,
        ValidationFailure,
        VersionConflict,
        OperationLimitExceeded,
    ) + cleanup_exceptions

    try:
        if scope_validator is not None:
            scope_validator(payload.operations)

        with session_factory() as business_db:
            board = (
                board_loader(business_db)
                if board_loader is not None
                else get_owned_board(business_db, user_id, payload.board_id)
            )
            result = execute_board_patch(
                business_db,
                user_id,
                payload,
                board=board,
            )
    except recoverable_errors:
        duration_ms = int((time.perf_counter() - start) * 1000)
        exc = sys.exc_info()[1]
        with session_factory() as fail_db:
            fail_idempotent_operation(
                fail_db,
                user_id=user_id,
                token_id=token_id,
                tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
                idempotency_key=payload.idempotency_key,
                request_hash=request_hash,
                persist_failure=False,
            )
        if exc is not None:
            _persist_audit_entry(
                session_factory,
                user_id=user_id,
                token_id=token_id,
                client_name=client_name,
                tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
                request_id=request_id,
                resource_type="board",
                resource_id=payload.board_id,
                status=MCP_AUDIT_STATUS_ERROR,
                error_code=_audit_error_code(exc),
                affected_count=0,
                version_before=payload.expected_version,
                version_after=None,
                duration_ms=duration_ms,
                is_replay=False,
                idempotency_key=payload.idempotency_key,
                metadata=audit_metadata,
            )
        raise
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        _persist_audit_entry(
            session_factory,
            user_id=user_id,
            token_id=token_id,
            client_name=client_name,
            tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
            request_id=request_id,
            resource_type="board",
            resource_id=payload.board_id,
            status=MCP_AUDIT_STATUS_ERROR,
            error_code=_audit_error_code(exc),
            affected_count=0,
            version_before=payload.expected_version,
            version_after=None,
            duration_ms=duration_ms,
            is_replay=False,
            idempotency_key=payload.idempotency_key,
            metadata=audit_metadata,
        )
        raise

    response_payload = build_execution_response(result)

    try:
        with session_factory() as complete_db:
            complete_idempotent_operation(
                complete_db,
                user_id=user_id,
                token_id=token_id,
                tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
                idempotency_key=payload.idempotency_key,
                request_hash=request_hash,
                response_json=response_payload,
                resource_version_before=result.previous_version,
                resource_version_after=result.board_version,
            )
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.warning(
            "mcp idempotency completion uncertain tool=%s request_id=%s board_id=%s",
            APPLY_BOARD_PATCH_TOOL_NAME,
            request_id,
            payload.board_id,
        )
        _persist_audit_entry(
            session_factory,
            user_id=user_id,
            token_id=token_id,
            client_name=client_name,
            tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
            request_id=request_id,
            resource_type="board",
            resource_id=payload.board_id,
            status=MCP_AUDIT_STATUS_STATE_UNCERTAIN,
            error_code=IDEMPOTENCY_ERROR_CODE,
            affected_count=result.operation_count,
            version_before=result.previous_version,
            version_after=result.board_version,
            duration_ms=duration_ms,
            is_replay=False,
            idempotency_key=payload.idempotency_key,
            metadata=_build_apply_board_patch_audit_metadata(
                operation_count=result.operation_count,
                summary=result.summary,
                dry_run=False,
            ),
        )
        raise

    duration_ms = int((time.perf_counter() - start) * 1000)
    _persist_audit_entry(
        session_factory,
        user_id=user_id,
        token_id=token_id,
        client_name=client_name,
        tool_name=APPLY_BOARD_PATCH_TOOL_NAME,
        request_id=request_id,
        resource_type="board",
        resource_id=payload.board_id,
        status=MCP_AUDIT_STATUS_SUCCESS,
        error_code=None,
        affected_count=result.operation_count,
        version_before=result.previous_version,
        version_after=result.board_version,
        duration_ms=duration_ms,
        is_replay=False,
        idempotency_key=payload.idempotency_key,
        metadata=_build_apply_board_patch_audit_metadata(
            operation_count=result.operation_count,
            summary=result.summary,
            dry_run=False,
        ),
    )

    return response_payload


# ------------------------------------------------------------------
# Validación de endpoints de edge
# ------------------------------------------------------------------


def _parse_edge_endpoint(data: dict[str, Any]) -> EdgeEndpoint:
    """Valida que un endpoint tenga exactamente nodeId o clientId, no ambos."""
    has_node = "nodeId" in data
    has_client = "clientId" in data
    if has_node and has_client:
        raise ValidationFailure(
            "Un endpoint de edge no puede tener nodeId y clientId simultáneamente"
        )
    if not has_node and not has_client:
        raise ValidationFailure(
            "Un endpoint de edge debe tener nodeId o clientId"
        )
    if has_node:
        return EdgeEndpointNodeRef(**data)
    return EdgeEndpointClientRef(**data)


def _validate_edge_structure(data: dict[str, Any]) -> None:
    """Valida la estructura de un endpoint de edge (excluyente nodeId/clientId)."""
    has_node = "nodeId" in data
    has_client = "clientId" in data
    if has_node and has_client:
        raise ValidationFailure(
            "Un endpoint de edge no puede tener nodeId y clientId simultáneamente"
        )
    if not has_node and not has_client:
        raise ValidationFailure(
            "Un endpoint de edge debe tener nodeId o clientId"
        )


def _validate_edge_endpoint_ref(
    endpoint: EdgeEndpoint,
    existing_nodes: dict[str, models.Node],
    created_nodes: dict[str, str],  # client_id -> placeholder
    board_nodes: list[models.Node],
) -> None:
    """Valida que un endpoint de edge referencie un node existente o creado."""
    if isinstance(endpoint, EdgeEndpointNodeRef):
        if endpoint.nodeId not in existing_nodes:
            raise ValidationFailure(
                f"El nodo '{endpoint.nodeId}' referenciado por el edge no existe en el board"
            )
    elif isinstance(endpoint, EdgeEndpointClientRef):
        if endpoint.clientId not in created_nodes:
            raise ValidationFailure(
                f"El client_id '{endpoint.clientId}' referenciado por el edge "
                f"no corresponde a ningún nodo creado en el patch"
            )


def _validate_edge_endpoint_port(
    endpoint: EdgeEndpoint,
    existing_nodes: dict[str, models.Node],
    created_node_payloads: dict[str, schemas.NodeSchema],
) -> None:
    """Valida que el puerto exista en el node referenciado."""
    if isinstance(endpoint, EdgeEndpointNodeRef):
        node = existing_nodes.get(endpoint.nodeId)
        if node is not None and node.ports:
            port_ids = {p["id"] for p in node.ports} if isinstance(node.ports, list) else set()
            if endpoint.portId not in port_ids:
                raise ValidationFailure(
                    f"Puerto '{endpoint.portId}' no existe en el nodo '{endpoint.nodeId}'"
                )
    elif isinstance(endpoint, EdgeEndpointClientRef):
        schema = created_node_payloads.get(endpoint.clientId)
        if schema is not None and schema.ports:
            port_ids = {p.id for p in schema.ports}
            if endpoint.portId not in port_ids:
                raise ValidationFailure(
                    f"Puerto '{endpoint.portId}' no existe en el nodo lógico "
                    f"'{endpoint.clientId}'"
                )


# ------------------------------------------------------------------
# Planificador
# ------------------------------------------------------------------


def build_board_patch_plan(
    db: Session,
    user_id: str,
    payload: BoardPatchPayload,
    board: models.Board | None = None,
) -> BoardPatchPlan:
    """Valida un patch de board y devuelve un plan estructurado sin ejecutar nada.

    No realiza escrituras, no incrementa versión, no modifica la base de datos.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Cargar board ---
    board = board or get_owned_board(db, user_id, payload.board_id)

    # --- Validar expected_version ---
    if payload.expected_version != board.version:
        raise VersionConflict(
            board_id=payload.board_id,
            expected_version=payload.expected_version,
            current_version=board.version,
        )

    # --- Validar límite ---
    if len(payload.operations) > MCP_MAX_PATCH_OPERATIONS:
        raise OperationLimitExceeded(
            f"El patch supera el límite máximo de {MCP_MAX_PATCH_OPERATIONS} operaciones. "
            f"Recibidas: {len(payload.operations)}"
        )

    # --- Indexar client_ids de creación (creación + edge) ---
    created_node_client_ids: dict[str, schemas.NodeSchema] = {}  # client_id -> schema
    created_edge_client_ids: set[str] = set()

    for op in payload.operations:
        if isinstance(op, PatchCreateNodeOperation):
            if op.client_id in created_node_client_ids:
                raise ValidationFailure(
                    f"client_id duplicado para creación de nodo: '{op.client_id}'"
                )
            node_payload = schemas.NodeSchema(
                id=None,
                **op.node.model_dump(),
            )
            created_node_client_ids[op.client_id] = node_payload

        elif isinstance(op, PatchCreateEdgeOperation):
            if op.client_id in created_edge_client_ids:
                raise ValidationFailure(
                    f"client_id duplicado para creación de edge: '{op.client_id}'"
                )
            if op.client_id in created_node_client_ids:
                raise ValidationFailure(
                    f"client_id '{op.client_id}' ya usado por un nodo en el mismo patch"
                )
            created_edge_client_ids.add(op.client_id)

    # --- Validar estructura de endpoints de edge antes de precargar ---
    for op in payload.operations:
        if isinstance(op, PatchCreateEdgeOperation):
            edge_data = op.edge
            if "from" not in edge_data or "to" not in edge_data:
                raise ValidationFailure("El edge debe tener campos 'from' y 'to'")
            # Validar exclusividad nodeId / clientId
            _validate_edge_structure(edge_data["from"])
            _validate_edge_structure(edge_data["to"])

    # --- Precargar recursos existentes ---
    existing_nodes_map: dict[str, models.Node] = {}
    existing_edges_map: dict[str, models.Edge] = {}
    node_ids_to_load: set[str] = set()
    edge_ids_to_load: set[str] = set()

    for op in payload.operations:
        if isinstance(op, (PatchUpdateNodeOperation, PatchMoveNodeOperation)):
            node_ids_to_load.add(op.node_id)
        elif isinstance(op, PatchCreateEdgeOperation):
            # nodeId references
            edge_from = op.edge.get("from", {})
            edge_to = op.edge.get("to", {})
            if "nodeId" in edge_from:
                node_ids_to_load.add(edge_from["nodeId"])
            if "nodeId" in edge_to:
                node_ids_to_load.add(edge_to["nodeId"])
        elif isinstance(op, PatchUpdateEdgeOperation):
            edge_ids_to_load.add(op.edge_id)

    # Cargar nodes existentes
    if node_ids_to_load:
        from sqlalchemy import select
        nodes = db.scalars(
            select(models.Node).where(
                models.Node.id.in_(node_ids_to_load),
                models.Node.board_id == board.id,
            )
        ).all()
        for n in nodes:
            existing_nodes_map[n.id] = n
        # Verificar que todos los IDs solicitados existen
        for nid in node_ids_to_load:
            if nid not in existing_nodes_map:
                errors.append(f"Nodo '{nid}' no encontrado en el board")

    # Cargar edges existentes
    if edge_ids_to_load:
        from sqlalchemy import select as sel2
        edges = db.scalars(
            sel2(models.Edge).where(
                models.Edge.id.in_(edge_ids_to_load),
                models.Edge.board_id == board.id,
            )
        ).all()
        for e in edges:
            existing_edges_map[e.id] = e
        for eid in edge_ids_to_load:
            if eid not in existing_edges_map:
                errors.append(f"Edge '{eid}' no encontrado en el board")

    if errors:
        raise ValidationFailure("; ".join(errors))

    # --- Validar cada operación ---
    plan_ops: list[PlanOperationStatus] = []
    summaries: dict[str, int] = {
        "nodes_created": 0,
        "nodes_updated": 0,
        "nodes_moved": 0,
        "edges_created": 0,
        "edges_updated": 0,
    }
    client_refs: dict[str, ClientReference] = {}

    for i, op in enumerate(payload.operations):
        try:
            if isinstance(op, PatchCreateNodeOperation):
                op.node  # validate
                summaries["nodes_created"] += 1
                client_refs[op.client_id] = ClientReference(
                    resource_type="node", status="will_create"
                )

            elif isinstance(op, PatchUpdateNodeOperation):
                if op.node_id not in existing_nodes_map:
                    raise ValidationFailure(
                        f"Nodo '{op.node_id}' no encontrado en el board"
                    )
                node_type = existing_nodes_map[op.node_id].type
                validate_update_changes(node_type, op.changes)
                summaries["nodes_updated"] += 1

            elif isinstance(op, PatchMoveNodeOperation):
                if op.node_id not in existing_nodes_map:
                    raise ValidationFailure(
                        f"Nodo '{op.node_id}' no encontrado en el board"
                    )
                summaries["nodes_moved"] += 1

            elif isinstance(op, PatchCreateEdgeOperation):
                # Validar estructura del edge
                edge_data = op.edge
                if "from" not in edge_data or "to" not in edge_data:
                    raise ValidationFailure("El edge debe tener campos 'from' y 'to'")

                from_endpoint = _parse_edge_endpoint(edge_data["from"])
                to_endpoint = _parse_edge_endpoint(edge_data["to"])

                _validate_edge_endpoint_ref(
                    from_endpoint, existing_nodes_map,
                    created_node_client_ids, board.nodes,
                )
                _validate_edge_endpoint_ref(
                    to_endpoint, existing_nodes_map,
                    created_node_client_ids, board.nodes,
                )

                _validate_edge_endpoint_port(
                    from_endpoint, existing_nodes_map, created_node_client_ids,
                )
                _validate_edge_endpoint_port(
                    to_endpoint, existing_nodes_map, created_node_client_ids,
                )

                summaries["edges_created"] += 1
                client_refs[op.client_id] = ClientReference(
                    resource_type="edge", status="will_create"
                )

            elif isinstance(op, PatchUpdateEdgeOperation):
                if op.edge_id not in existing_edges_map:
                    raise ValidationFailure(
                        f"Edge '{op.edge_id}' no encontrado en el board"
                    )
                # Validate changes structure
                if "curved" not in op.changes and "label" not in op.changes:
                    raise ValidationFailure(
                        "Debe especificar al menos un cambio (curved o label)"
                    )
                if "curved" in op.changes:
                    if not isinstance(op.changes["curved"], bool):
                        raise ValidationFailure("curved debe ser un booleano")
                if "label" in op.changes and op.changes["label"] is not None:
                    if not isinstance(op.changes["label"], str):
                        raise ValidationFailure("label debe ser un string")
                summaries["edges_updated"] += 1

        except ValidationFailure as e:
            raise ValidationFailure(f"Operación {i} ({op.op}): {e.message}")

        plan_ops.append(PlanOperationStatus(index=i, op=op.op, status="valid"))

    # --- Warnings opcionales ---
    # Self-edge en create_edge
    for i, op in enumerate(payload.operations):
        if isinstance(op, PatchCreateEdgeOperation):
            edge_from = op.edge.get("from", {})
            edge_to = op.edge.get("to", {})
            from_node = edge_from.get("nodeId") or edge_from.get("clientId")
            to_node = edge_to.get("nodeId") or edge_to.get("clientId")
            if from_node and from_node == to_node:
                warnings.append(f"Operación {i}: self-edge detectado")

    return BoardPatchPlan(
        dry_run=payload.dry_run,
        valid=True,
        board_id=payload.board_id,
        current_version=board.version,
        predicted_version=board.version + 1,
        operation_count=len(payload.operations),
        summary=summaries,
        client_references=client_refs,
        operations=plan_ops,
        warnings=warnings,
    )
