"""Helpers reutilizables para tools MCP de escritura.

Esta capa encapsula:
- resolución segura de contexto autenticado
- autorización por scope y board
- normalización de ``expected_version``
- respuestas de éxito homogéneas
- conversión uniforme de errores de dominio

No contiene lógica específica de ninguna tool concreta.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

from sqlalchemy.orm import Session

from .. import models
from ..services.authorization import get_owned_board, get_owned_edge_with_board, get_owned_node_with_board
from ..services.errors import (
    ForbiddenResource,
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStateUncertain,
    OperationLimitExceeded,
    RateLimitExceeded,
    ResourceNotFound,
    ValidationFailure,
    VersionConflict,
)
from . import auth as mcp_auth
from .context import MCPContext


def _require_context(context: MCPContext | None) -> MCPContext:
    if context is None:
        raise RuntimeError("No hay contexto MCP disponible en esta operación.")
    return context


def require_scope(
    context: MCPContext | None,
    required_scope: str,
) -> MCPContext:
    """Exige un scope MCP y devuelve el contexto validado."""
    ctx = _require_context(context)
    mcp_auth.require_scope(ctx, required_scope)
    return ctx


def load_board(
    db: Session,
    context: MCPContext | None,
    board_id: str,
) -> models.Board:
    """Carga un board del usuario actual y aplica constraints MCP."""
    ctx = _require_context(context)
    board = get_owned_board(db, ctx.user_id, board_id)
    mcp_auth.enforce_board_constraint_for_board(ctx, board)
    return board


def require_board_scope(
    db: Session,
    context: MCPContext | None,
    board_id: str,
    required_scope: str,
) -> models.Board:
    """Exige scope y acceso al board, devolviendo el board cargado."""
    ctx = require_scope(context, required_scope)
    return load_board(db, ctx, board_id)


def load_node_with_board(
    db: Session,
    context: MCPContext | None,
    node_id: str,
) -> tuple[models.Node, models.Board]:
    """Carga un node del usuario actual junto a su board y aplica constraints."""
    ctx = _require_context(context)
    node, board = get_owned_node_with_board(db, ctx.user_id, node_id)
    mcp_auth.enforce_board_constraint_for_board(ctx, board)
    return node, board


def require_node_scope(
    db: Session,
    context: MCPContext | None,
    node_id: str,
    required_scope: str,
) -> tuple[models.Node, models.Board]:
    """Exige scope y acceso al node, devolviendo node y board cargados."""
    ctx = require_scope(context, required_scope)
    return load_node_with_board(db, ctx, node_id)


def load_edge_with_board(
    db: Session,
    context: MCPContext | None,
    edge_id: str,
) -> tuple[models.Edge, models.Board]:
    """Carga un edge del usuario actual junto a su board y aplica constraints."""
    ctx = _require_context(context)
    edge, board = get_owned_edge_with_board(db, ctx.user_id, edge_id)
    mcp_auth.enforce_board_constraint_for_board(ctx, board)
    return edge, board


def require_edge_scope(
    db: Session,
    context: MCPContext | None,
    edge_id: str,
    required_scope: str,
) -> tuple[models.Edge, models.Board]:
    """Exige scope y acceso al edge, devolviendo edge y board cargados."""
    ctx = require_scope(context, required_scope)
    return load_edge_with_board(db, ctx, edge_id)


def resolve_expected_version(
    board: models.Board,
    expected_version: int | None,
) -> int:
    """Normaliza ``expected_version`` para escrituras con optimistic locking.

    - Si no se informa, usa la versión actual del board.
    - Si se informa y no coincide, lanza ``VersionConflict``.

    Las services de escritura siguen siendo la autoridad final y deben
    aplicar su propio control atómico de versión al persistir.
    """
    if expected_version is None:
        return board.version

    if expected_version != board.version:
        raise VersionConflict(
            board_id=board.id,
            expected_version=expected_version,
            current_version=board.version,
        )

    return expected_version


def build_success(**payload: object) -> dict[str, object]:
    """Construye una respuesta homogénea de éxito para tools de escritura."""
    return {"ok": True, **payload}


def map_domain_error(error: Exception) -> ValueError:
    """Convierte errores de dominio a un error externo homogéneo."""
    if isinstance(error, ResourceNotFound):
        return ValueError(error.message or f"{error.resource_type} no encontrado")

    if isinstance(error, ForbiddenResource):
        return ValueError(
            error.message or f"Acceso denegado a {error.resource_type}"
        )

    if isinstance(error, (ValidationFailure, OperationLimitExceeded)):
        return ValueError(error.message)

    if isinstance(error, VersionConflict):
        return ValueError(
            json.dumps(
                {
                    "code": "VERSION_CONFLICT",
                    "message": error.message,
                    "board_id": error.board_id,
                    "expected_version": error.expected_version,
                    "current_version": error.current_version,
                },
                ensure_ascii=False,
            )
        )

    if isinstance(error, IdempotencyConflict):
        return ValueError(
            json.dumps(
                {
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": error.message,
                    "idempotency_key": error.idempotency_key,
                },
                ensure_ascii=False,
            )
        )

    if isinstance(error, IdempotencyInProgress):
        return ValueError(
            json.dumps(
                {
                    "code": "IDEMPOTENCY_IN_PROGRESS",
                    "message": error.message,
                    "idempotency_key": error.idempotency_key,
                },
                ensure_ascii=False,
            )
        )

    if isinstance(error, IdempotencyStateUncertain):
        return ValueError(
            json.dumps(
                {
                    "code": "IDEMPOTENCY_STATE_UNCERTAIN",
                    "message": error.message,
                    "idempotency_key": error.idempotency_key,
                },
                ensure_ascii=False,
            )
        )

    if isinstance(error, RateLimitExceeded):
        return ValueError(
            json.dumps(
                {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": error.message,
                    "retry_after_seconds": error.retry_after_seconds,
                    "limit": error.limit,
                    "window_seconds": error.window_seconds,
                },
                ensure_ascii=False,
            )
        )

    return ValueError("Error de dominio no soportado.")


@contextmanager
def reraise_domain_errors():
    """Convierte errores de dominio soportados preservando traceback."""
    try:
        yield
    except (
        ResourceNotFound,
        ForbiddenResource,
        ValidationFailure,
        VersionConflict,
        OperationLimitExceeded,
        RateLimitExceeded,
        IdempotencyConflict,
        IdempotencyInProgress,
        IdempotencyStateUncertain,
    ) as exc:
        raise map_domain_error(exc) from exc
