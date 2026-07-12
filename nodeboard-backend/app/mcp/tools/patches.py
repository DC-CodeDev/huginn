"""Tool MCP apply_board_patch — validación (dry-run) y ejecución transaccional.

Soporta ``dry_run=true`` para validar operaciones agrupadas sin
ejecutar escrituras y ``dry_run=false`` para ejecución real atómica
con optimistic locking, rollback y respuesta estructurada.
"""

import logging
import time

from pydantic import ValidationError

from ... import database as _database
from ...mcp.write_helpers import (
    load_board,
    require_scope,
    reraise_domain_errors,
)
from ...mcp.errors import ConstraintViolation, InsufficientScope
from ...services.board_patches import (
    MCP_MAX_PATCH_OPERATIONS,
    BoardPatchPayload,
    BoardPatchPlan,
    BoardPatchExecutionResult,
    build_execution_response,
    build_plan_response,
    build_board_patch_plan,
    execute_idempotent_board_patch,
    required_scopes,
    validate_apply_board_patch_contract,
)
from ...services import mcp_rate_limit
from ...services.mcp_audit import (
    MCP_AUDIT_STATUS_ERROR,
    MCP_AUDIT_STATUS_SUCCESS,
    create_audit_entry,
)
from ...services.errors import RateLimitExceeded
from ..context import get_context

logger = logging.getLogger(__name__)
_PATCH_RATE_LIMIT_CATEGORY = "patch"


def register(mcp) -> None:
    @mcp.tool(
        name="apply_board_patch",
        description=(
            "Valida y ejecuta un conjunto de operaciones sobre un board. "
            "Acepta board_id, expected_version, dry_run, idempotency_key y una lista de operations "
            "con op: create_node, update_node, move_node, create_edge, update_edge. "
            "Soporta referencias entre operaciones mediante client_id. "
            "dry_run=true solo valida sin escribir y no admite idempotency_key; "
            "dry_run=false exige idempotency_key y ejecuta "
            "de forma transaccional y atómica. "
            "Requiere scopes según las operaciones incluidas. "
            "Máximo {} operaciones por patch."
        ).format(MCP_MAX_PATCH_OPERATIONS),
    )
    def apply_board_patch(
        board_id: str,
        expected_version: int,
        dry_run: bool,
        operations: list[dict],
        idempotency_key: str | None = None,
    ) -> dict:
        """Valida (dry-run) o ejecuta (dry_run=false) un patch de board."""
        try:
            payload = BoardPatchPayload(
                board_id=board_id,
                expected_version=expected_version,
                dry_run=dry_run,
                idempotency_key=idempotency_key,
                operations=operations,
            )
        except ValidationError as exc:
            message = exc.errors()[0]["msg"] if exc.errors() else "Payload inválido"
            raise ValueError(message) from exc

        ctx = get_context()
        started = time.perf_counter()

        with reraise_domain_errors():
            validate_apply_board_patch_contract(payload)
            _consume_patch_rate_limit(ctx=ctx, payload=payload, started=started)

            # Validar scopes requeridos
            scopes_needed = required_scopes(payload.operations)

            def _validate_scopes(_: list[object]) -> None:
                for scope in scopes_needed:
                    require_scope(ctx, scope)

            if payload.dry_run:
                try:
                    _validate_scopes(payload.operations)
                    with _database.SessionLocal() as db:
                        board = load_board(db, ctx, payload.board_id)
                        plan = build_board_patch_plan(
                            db, ctx.user_id, payload, board=board,
                        )
                        response = _plan_to_response(plan)
                except Exception as exc:
                    _persist_patch_audit(
                        ctx=ctx,
                        payload=payload,
                        status=MCP_AUDIT_STATUS_ERROR,
                        error=exc,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                    raise

                _persist_patch_audit(
                    ctx=ctx,
                    payload=payload,
                    status=MCP_AUDIT_STATUS_SUCCESS,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    affected_count=0,
                    version_before=plan.current_version,
                    version_after=plan.current_version,
                    metadata={
                        "operation_count": plan.operation_count,
                        "summary": plan.summary,
                        "dry_run": True,
                    },
                )
                return response

            return execute_idempotent_board_patch(
                _database.SessionLocal,
                user_id=ctx.user_id,
                token_id=ctx.token_id,
                request_id=ctx.request_id,
                client_name=ctx.client_name,
                payload=payload,
                scope_validator=_validate_scopes,
                board_loader=lambda db: load_board(db, ctx, payload.board_id),
                cleanup_exceptions=(InsufficientScope, ConstraintViolation),
            )


def _plan_to_response(plan: BoardPatchPlan) -> dict:
    """Convierte un BoardPatchPlan a la respuesta homogénea."""
    return build_plan_response(plan)


def _execution_to_response(result: BoardPatchExecutionResult) -> dict:
    """Convierte un BoardPatchExecutionResult a la respuesta homogénea."""
    return build_execution_response(result)


def _audit_error_code(error: Exception) -> str:
    if isinstance(error, RateLimitExceeded):
        return "RATE_LIMIT_EXCEEDED"
    if isinstance(error, ValueError):
        text = str(error)
        if '"code": "VERSION_CONFLICT"' in text:
            return "VERSION_CONFLICT"
        if '"code": "RATE_LIMIT_EXCEEDED"' in text:
            return "RATE_LIMIT_EXCEEDED"
        if '"code": "IDEMPOTENCY_CONFLICT"' in text:
            return "IDEMPOTENCY_CONFLICT"
        if '"code": "IDEMPOTENCY_IN_PROGRESS"' in text:
            return "IDEMPOTENCY_IN_PROGRESS"
        if '"code": "IDEMPOTENCY_STATE_UNCERTAIN"' in text:
            return "IDEMPOTENCY_STATE_UNCERTAIN"
        return "VALIDATION_FAILURE"
    if isinstance(error, (InsufficientScope, ConstraintViolation)):
        return "FORBIDDEN_RESOURCE"
    return "INTERNAL_ERROR"


def _rate_limit_audit_metadata(error: RateLimitExceeded) -> dict[str, int]:
    return {
        "limit": error.limit,
        "window_seconds": error.window_seconds,
        "retry_after_seconds": error.retry_after_seconds,
    }


def _consume_patch_rate_limit(*, ctx, payload: BoardPatchPayload, started: float) -> None:
    try:
        mcp_rate_limit.consume_rate_limit(
            token_id=ctx.token_id,
            tool_name="apply_board_patch",
            category=_PATCH_RATE_LIMIT_CATEGORY,
            cost=1,
        )
    except RateLimitExceeded as exc:
        _persist_patch_audit(
            ctx=ctx,
            payload=payload,
            status=MCP_AUDIT_STATUS_ERROR,
            error=exc,
            affected_count=0,
            version_before=payload.expected_version,
            version_after=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            metadata=_rate_limit_audit_metadata(exc),
        )
        raise


def _persist_patch_audit(
    *,
    ctx,
    payload: BoardPatchPayload,
    status: str,
    duration_ms: int,
    error: Exception | None = None,
    affected_count: int = 0,
    version_before: int | None = None,
    version_after: int | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        with _database.SessionLocal() as audit_db:
            create_audit_entry(
                audit_db,
                user_id=ctx.user_id,
                token_id=ctx.token_id,
                client_name=ctx.client_name,
                tool_name="apply_board_patch",
                request_id=ctx.request_id,
                resource_type="board",
                resource_id=payload.board_id,
                status=status,
                error_code=_audit_error_code(error) if error is not None else None,
                affected_count=affected_count,
                version_before=version_before,
                version_after=version_after,
                duration_ms=duration_ms,
                is_replay=False,
                idempotency_key=payload.idempotency_key,
                metadata=metadata,
            )
    except Exception:
        logger.exception(
            "mcp audit persistence failed tool=apply_board_patch request_id=%s status=%s board_id=%s",
            ctx.request_id,
            status,
            payload.board_id,
        )
