"""Wrapper común para tools MCP de lectura."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

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
from ..services.mcp_audit import MCP_AUDIT_STATUS_ERROR, MCP_AUDIT_STATUS_SUCCESS
from ..services.mcp_rate_limit import consume_rate_limit
from .context import MCPContext
from .errors import ConstraintViolation, InsufficientScope
from .mutation_guard import (
    build_rate_limit_audit_metadata,
    map_audit_error_code,
    persist_mutation_audit_entry,
)
from .write_helpers import map_domain_error


@dataclass(frozen=True)
class ReadResult:
    response: dict[str, Any]
    resource_type: str
    resource_id: str | None
    returned_count: int
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


def execute_read_tool(
    session_factory: Callable[[], Session],
    *,
    ctx: MCPContext,
    tool_name: str,
    capability_type: str,
    audit_resource_type: str,
    audit_resource_id: str | None,
    operation: Callable[[], ReadResult],
    cost: int = 1,
) -> dict[str, Any]:
    start = time.perf_counter()

    try:
        consume_rate_limit(
            token_id=ctx.token_id,
            tool_name=tool_name,
            category="read",
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
    except ValueError as exc:
        persist_mutation_audit_entry(
            session_factory,
            ctx=ctx,
            tool_name=tool_name,
            resource_type=audit_resource_type,
            resource_id=audit_resource_id,
            status=MCP_AUDIT_STATUS_ERROR,
            error_code="VALIDATION_FAILURE",
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
        affected_count=result.returned_count,
        version_before=None,
        version_after=None,
        duration_ms=int((time.perf_counter() - start) * 1000),
        metadata=result.metadata,
    )
    return result.response
