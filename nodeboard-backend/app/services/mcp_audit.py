"""Infraestructura persistente y segura de auditoría para operaciones MCP."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

MCP_AUDIT_STATUS_SUCCESS = "success"
MCP_AUDIT_STATUS_ERROR = "error"
MCP_AUDIT_STATUS_REPLAY = "replay"
MCP_AUDIT_STATUS_IN_PROGRESS = "in_progress"
MCP_AUDIT_STATUS_STATE_UNCERTAIN = "state_uncertain"

ALLOWED_AUDIT_STATUSES = {
    MCP_AUDIT_STATUS_SUCCESS,
    MCP_AUDIT_STATUS_ERROR,
    MCP_AUDIT_STATUS_REPLAY,
    MCP_AUDIT_STATUS_IN_PROGRESS,
    MCP_AUDIT_STATUS_STATE_UNCERTAIN,
}

MAX_AUDIT_LIST_LIMIT = 100
DEFAULT_MCP_AUDIT_RETENTION_DAYS = 90
IDEMPOTENCY_KEY_PREFIX_LENGTH = 8

_SUMMARY_KEYS = {
    "nodes_created",
    "nodes_updated",
    "nodes_moved",
    "edges_created",
    "edges_updated",
}
_METADATA_TOP_LEVEL_KEYS = {
    "operation_count",
    "summary",
    "dry_run",
    "original_affected_count",
    "safe_message",
    "limit",
    "window_seconds",
    "retry_after_seconds",
    "created_count",
    "changed_field_count",
    "operation_kind",
    "batch_size",
    "returned_count",
    "cursor_present",
    "include_images",
    "response_truncated",
}
_SENSITIVE_METADATA_KEYS = {
    "token",
    "token_hash",
    "authorization",
    "Authorization",
    "bearer",
    "payload",
    "response_json",
    "request_hash",
    "blocks",
    "stages",
    "tags",
    "label",
    "labels",
}


@dataclass(frozen=True)
class MCPAuditEntryInput:
    user_id: str | None
    token_id: str | None
    client_name: str | None
    tool_name: str
    request_id: str | None
    resource_type: str
    resource_id: str | None
    status: str
    error_code: str | None = None
    affected_count: int = 0
    version_before: int | None = None
    version_after: int | None = None
    duration_ms: int = 0
    is_replay: bool = False
    idempotency_key: str | None = None
    metadata: Mapping[str, Any] | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class MCPAuditListFilters:
    user_id: str | None = None
    token_id: str | None = None
    tool_name: str | None = None
    status: str | None = None
    resource_id: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 50
    offset: int = 0


def _now() -> datetime:
    return models._now()


def _retention_days() -> int:
    raw = os.getenv(
        "MCP_AUDIT_RETENTION_DAYS",
        str(DEFAULT_MCP_AUDIT_RETENTION_DAYS),
    )
    value = int(raw)
    if value <= 0:
        raise ValueError("MCP_AUDIT_RETENTION_DAYS debe ser un entero positivo")
    return value


def summarise_idempotency_key(idempotency_key: str | None) -> str | None:
    if not idempotency_key:
        return None
    prefix = idempotency_key[:IDEMPOTENCY_KEY_PREFIX_LENGTH]
    if len(idempotency_key) <= IDEMPOTENCY_KEY_PREFIX_LENGTH:
        return prefix
    return f"{prefix}…"


def _coerce_duration_ms(duration_ms: int | float) -> int:
    value = int(round(duration_ms))
    return max(value, 0)


def _clean_summary(summary: Any) -> dict[str, int] | None:
    if not isinstance(summary, Mapping):
        return None

    cleaned: dict[str, int] = {}
    for key in _SUMMARY_KEYS:
        value = summary.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            cleaned[key] = value
    return cleaned or None


def build_audit_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, Mapping):
        return None

    cleaned: dict[str, Any] = {}
    for key in _METADATA_TOP_LEVEL_KEYS:
        if key not in metadata or key in _SENSITIVE_METADATA_KEYS:
            continue
        value = metadata[key]
        if key == "summary":
            summary = _clean_summary(value)
            if summary:
                cleaned["summary"] = summary
            continue
        if key == "operation_kind" and isinstance(value, str):
            cleaned["operation_kind"] = value[:100]
            continue
        if key == "dry_run" and isinstance(value, bool):
            cleaned["dry_run"] = value
            continue
        if key in {
            "operation_count",
            "original_affected_count",
            "limit",
            "window_seconds",
            "retry_after_seconds",
            "created_count",
            "changed_field_count",
            "batch_size",
            "returned_count",
        }:
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                cleaned[key] = value
            continue
        if key in {"cursor_present", "include_images", "response_truncated"}:
            if isinstance(value, bool):
                cleaned[key] = value
            continue
        if key == "safe_message" and isinstance(value, str):
            cleaned["safe_message"] = value[:200]

    return cleaned or None


def create_audit_entry(
    db: Session,
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
    metadata: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> models.MCPAuditLog:
    if status not in ALLOWED_AUDIT_STATUSES:
        raise ValueError(f"Estado de auditoría no soportado: {status}")

    entry = models.MCPAuditLog(
        user_id=user_id,
        token_id=token_id,
        client_name=client_name,
        tool_name=tool_name,
        request_id=request_id,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        error_code=error_code,
        affected_count=max(int(affected_count), 0),
        version_before=version_before,
        version_after=version_after,
        duration_ms=_coerce_duration_ms(duration_ms),
        is_replay=is_replay,
        idempotency_key_prefix=summarise_idempotency_key(idempotency_key),
        metadata_json=build_audit_metadata(metadata),
        created_at=created_at or _now(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_audit_entry(db: Session, audit_id: str) -> models.MCPAuditLog | None:
    return db.get(models.MCPAuditLog, audit_id)


def list_audit_entries(
    db: Session,
    *,
    user_id: str | None = None,
    token_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    resource_id: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[models.MCPAuditLog]:
    effective_limit = max(1, min(int(limit), MAX_AUDIT_LIST_LIMIT))
    stmt = select(models.MCPAuditLog).order_by(
        models.MCPAuditLog.created_at.desc(),
        models.MCPAuditLog.id.desc(),
    )
    if user_id is not None:
        stmt = stmt.where(models.MCPAuditLog.user_id == user_id)
    if token_id is not None:
        stmt = stmt.where(models.MCPAuditLog.token_id == token_id)
    if tool_name is not None:
        stmt = stmt.where(models.MCPAuditLog.tool_name == tool_name)
    if status is not None:
        stmt = stmt.where(models.MCPAuditLog.status == status)
    if resource_id is not None:
        stmt = stmt.where(models.MCPAuditLog.resource_id == resource_id)
    if created_after is not None:
        stmt = stmt.where(models.MCPAuditLog.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(models.MCPAuditLog.created_at <= created_before)
    stmt = stmt.offset(max(int(offset), 0)).limit(effective_limit)
    return list(db.execute(stmt).scalars().all())


def purge_old_audit_entries(
    db: Session,
    *,
    now: datetime | None = None,
    retention_days: int | None = None,
) -> int:
    current_time = now or _now()
    days = retention_days if retention_days is not None else _retention_days()
    if days <= 0:
        raise ValueError("retention_days debe ser un entero positivo")
    cutoff = current_time - timedelta(days=days)
    result = db.execute(
        delete(models.MCPAuditLog).where(models.MCPAuditLog.created_at < cutoff)
    )
    db.commit()
    deleted = int(result.rowcount or 0)
    logger.info(
        "mcp audit purge completed deleted=%d retention_days=%d cutoff=%s",
        deleted,
        days,
        cutoff.isoformat(),
    )
    return deleted
