"""Wrapper común para tools MCP mutativas."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from .. import models
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
from ..services.mcp_audit import (
    MCP_AUDIT_STATUS_ERROR,
    MCP_AUDIT_STATUS_SUCCESS,
    create_audit_entry,
)
from ..services.mcp_rate_limit import consume_rate_limit
from .context import MCPContext
from .errors import ConstraintViolation, InsufficientScope
from .write_helpers import map_domain_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MutationResult:
    response: dict[str, Any]
    resource_type: str
    resource_id: str | None
    affected_count: int
    version_before: int | None
    version_after: int | None
    metadata: Mapping[str, Any] | None = None


_DOMAIN_ERRORS = (
    ResourceNotFound,
    ValidationFailure,
    VersionConflict,
    OperationLimitExceeded,
    RateLimitExceeded,
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStateUncertain,
)
_FORBIDDEN_ERRORS = (InsufficientScope, ConstraintViolation)


def map_audit_error_code(error: BaseException) -> str:
    if isinstance(error, ValidationFailure):
        return "VALIDATION_FAILURE"
    if isinstance(error, ResourceNotFound):
        return "RESOURCE_NOT_FOUND"
    if isinstance(error, VersionConflict):
        return "VERSION_CONFLICT"
    if isinstance(error, OperationLimitExceeded):
        return "OPERATION_LIMIT_EXCEEDED"
    if isinstance(error, RateLimitExceeded):
        return "RATE_LIMIT_EXCEEDED"
    if isinstance(error, IdempotencyConflict):
        return "IDEMPOTENCY_CONFLICT"
    if isinstance(error, IdempotencyInProgress):
        return "IDEMPOTENCY_IN_PROGRESS"
    if isinstance(error, IdempotencyStateUncertain):
        return "IDEMPOTENCY_STATE_UNCERTAIN"
    if isinstance(error, _FORBIDDEN_ERRORS):
        return "FORBIDDEN_RESOURCE"
    return "INTERNAL_ERROR"


def build_rate_limit_audit_metadata(error: RateLimitExceeded) -> dict[str, int]:
    return {
        "limit": error.limit,
        "window_seconds": error.window_seconds,
        "retry_after_seconds": error.retry_after_seconds,
    }


def persist_mutation_audit_entry(
    session_factory: Callable[[], Session],
    *,
    ctx: MCPContext,
    tool_name: str,
    resource_type: str,
    resource_id: str | None,
    status: str,
    error_code: str | None = None,
    affected_count: int = 0,
    version_before: int | None = None,
    version_after: int | None = None,
    duration_ms: int = 0,
    metadata: Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
    is_replay: bool = False,
) -> None:
    logger.debug("[mcp-audit] write begin tool=%s", tool_name)
    try:
        with session_factory() as audit_db:
            persisted_token_id = (
                ctx.token_id
                if audit_db.get(models.MCPToken, ctx.token_id) is not None
                else None
            )
            create_audit_entry(
                audit_db,
                user_id=ctx.user_id,
                token_id=persisted_token_id,
                client_name=ctx.client_name,
                tool_name=tool_name,
                request_id=ctx.request_id,
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
        logger.debug("[mcp-audit] write complete tool=%s", tool_name)
    except Exception:
        logger.exception(
            "mcp audit persistence failed tool=%s request_id=%s status=%s resource_type=%s resource_id=%s",
            tool_name,
            ctx.request_id,
            status,
            resource_type,
            resource_id,
        )


def execute_mutating_tool(
    session_factory: Callable[[], Session],
    *,
    ctx: MCPContext,
    tool_name: str,
    category: str,
    capability_type: str,
    audit_resource_type: str,
    audit_resource_id: str | None,
    operation: Callable[[], MutationResult],
    cost: int = 1,
) -> dict[str, Any]:
    start = time.perf_counter()

    try:
        consume_rate_limit(
            token_id=ctx.token_id,
            tool_name=tool_name,
            category=category,
            capability_type=capability_type,
            cost=cost,
        )
    except RateLimitExceeded as exc:
        persist_mutation_audit_entry(
            session_factory,
            ctx=ctx,
            tool_name=tool_name,
            resource_type=audit_resource_type,
            resource_id=audit_resource_id,
            status=MCP_AUDIT_STATUS_ERROR,
            error_code=map_audit_error_code(exc),
            affected_count=0,
            version_before=None,
            version_after=None,
            duration_ms=int((time.perf_counter() - start) * 1000),
            metadata=build_rate_limit_audit_metadata(exc),
        )
        raise map_domain_error(exc) from exc

    try:
        result = operation()
    except _DOMAIN_ERRORS as exc:
        persist_mutation_audit_entry(
            session_factory,
            ctx=ctx,
            tool_name=tool_name,
            resource_type=audit_resource_type,
            resource_id=audit_resource_id,
            status=MCP_AUDIT_STATUS_ERROR,
            error_code=map_audit_error_code(exc),
            affected_count=0,
            version_before=None,
            version_after=None,
            duration_ms=int((time.perf_counter() - start) * 1000),
            metadata=None,
        )
        raise map_domain_error(exc) from exc
    except _FORBIDDEN_ERRORS as exc:
        persist_mutation_audit_entry(
            session_factory,
            ctx=ctx,
            tool_name=tool_name,
            resource_type=audit_resource_type,
            resource_id=audit_resource_id,
            status=MCP_AUDIT_STATUS_ERROR,
            error_code=map_audit_error_code(exc),
            affected_count=0,
            version_before=None,
            version_after=None,
            duration_ms=int((time.perf_counter() - start) * 1000),
            metadata=None,
        )
        raise
    except Exception:
        persist_mutation_audit_entry(
            session_factory,
            ctx=ctx,
            tool_name=tool_name,
            resource_type=audit_resource_type,
            resource_id=audit_resource_id,
            status=MCP_AUDIT_STATUS_ERROR,
            error_code="INTERNAL_ERROR",
            affected_count=0,
            version_before=None,
            version_after=None,
            duration_ms=int((time.perf_counter() - start) * 1000),
            metadata=None,
        )
        raise

    persist_mutation_audit_entry(
        session_factory,
        ctx=ctx,
        tool_name=tool_name,
        resource_type=result.resource_type,
        resource_id=result.resource_id,
        status=MCP_AUDIT_STATUS_SUCCESS,
        error_code=None,
        affected_count=result.affected_count,
        version_before=result.version_before,
        version_after=result.version_after,
        duration_ms=int((time.perf_counter() - start) * 1000),
        metadata=result.metadata,
    )
    return result.response
