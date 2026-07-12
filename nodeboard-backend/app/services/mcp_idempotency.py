"""Infraestructura persistente de idempotencia para escrituras MCP.

El flujo esperado para futuras tools es:

1. ``begin_idempotent_operation`` reserva la clave en una transacción corta.
2. La operación de negocio se ejecuta fuera de esa reserva.
3. ``complete_idempotent_operation`` persiste la respuesta serializable.
4. ``fail_idempotent_operation`` libera o marca el registro fallido.

No integra todavía ninguna tool MCP concreta; esta capa solo expone
primitivas reutilizables.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, Mapping

from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from .errors import (
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStateUncertain,
    ResourceNotFound,
)

IDEMPOTENCY_STATUS_IN_PROGRESS = "in_progress"
IDEMPOTENCY_STATUS_COMPLETED = "completed"
IDEMPOTENCY_STATUS_FAILED = "failed"

IDEMPOTENCY_MIN_KEY_LENGTH = 8
IDEMPOTENCY_MAX_KEY_LENGTH = 128
DEFAULT_IDEMPOTENCY_TTL_HOURS = 24
DEFAULT_IN_PROGRESS_TTL_SECONDS = 300
DEFAULT_FAILED_TTL_SECONDS = 60


@dataclass(frozen=True)
class BeginIdempotentOperationResult:
    status: Literal["created", "replay"]
    request_hash: str
    record: models.MCPIdempotencyRecord
    response_json: dict[str, Any] | None = None
    recovered: bool = False


def _now() -> datetime:
    return models._now()


def _ttl_hours() -> int:
    raw = os.getenv("MCP_IDEMPOTENCY_TTL_HOURS", str(DEFAULT_IDEMPOTENCY_TTL_HOURS))
    value = int(raw)
    if value <= 0:
        raise ValueError("MCP_IDEMPOTENCY_TTL_HOURS debe ser un entero positivo")
    return value


def _in_progress_ttl_seconds() -> int:
    raw = os.getenv(
        "MCP_IDEMPOTENCY_IN_PROGRESS_TTL_SECONDS",
        str(DEFAULT_IN_PROGRESS_TTL_SECONDS),
    )
    value = int(raw)
    if value <= 0:
        raise ValueError(
            "MCP_IDEMPOTENCY_IN_PROGRESS_TTL_SECONDS debe ser un entero positivo"
        )
    return value


def validate_idempotency_key(idempotency_key: str) -> str:
    if not isinstance(idempotency_key, str):
        raise ValueError("idempotency_key debe ser un string")

    if not idempotency_key.strip():
        raise ValueError("idempotency_key no puede estar vacío")

    if len(idempotency_key) < IDEMPOTENCY_MIN_KEY_LENGTH:
        raise ValueError(
            f"idempotency_key debe tener al menos {IDEMPOTENCY_MIN_KEY_LENGTH} caracteres"
        )

    if len(idempotency_key) > IDEMPOTENCY_MAX_KEY_LENGTH:
        raise ValueError(
            f"idempotency_key no puede superar {IDEMPOTENCY_MAX_KEY_LENGTH} caracteres"
        )

    return idempotency_key


def _normalise_for_json(
    value: Any,
    *,
    exclude_fields: set[str] | None = None,
) -> Any:
    exclude = exclude_fields or set()

    if isinstance(value, BaseModel):
        return _normalise_for_json(
            value.model_dump(mode="json", by_alias=True),
            exclude_fields=exclude,
        )

    if hasattr(value, "__dataclass_fields__"):
        return _normalise_for_json(asdict(value), exclude_fields=exclude)

    if isinstance(value, Mapping):
        normalised: dict[str, Any] = {}
        for key in sorted(value.keys(), key=lambda item: str(item)):
            key_str = str(key)
            if key_str in exclude:
                continue
            normalised[key_str] = _normalise_for_json(
                value[key],
                exclude_fields=exclude,
            )
        return normalised

    if isinstance(value, (list, tuple)):
        return [
            _normalise_for_json(item, exclude_fields=exclude)
            for item in value
        ]

    if isinstance(value, (set, frozenset)):
        return sorted(
            (_normalise_for_json(item, exclude_fields=exclude) for item in value),
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    if isinstance(value, uuid.UUID):
        return str(value)

    return value


def build_idempotency_request_hash(
    *,
    tool_name: str,
    payload: Any,
    user_id: str,
    token_id: str,
    exclude_fields: set[str] | None = None,
) -> str:
    canonical_payload = {
        "tool_name": tool_name,
        "user_id": user_id,
        "token_id": token_id,
        "payload": _normalise_for_json(payload, exclude_fields=exclude_fields),
    }
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_idempotency_record(
    db: Session,
    *,
    user_id: str,
    token_id: str,
    tool_name: str,
    idempotency_key: str,
) -> models.MCPIdempotencyRecord | None:
    return (
        db.execute(
            select(models.MCPIdempotencyRecord).where(
                models.MCPIdempotencyRecord.user_id == user_id,
                models.MCPIdempotencyRecord.token_id == token_id,
                models.MCPIdempotencyRecord.tool_name == tool_name,
                models.MCPIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        .scalars()
        .first()
    )


def _is_expired(record: models.MCPIdempotencyRecord, now: datetime) -> bool:
    return record.expires_at <= now


def _create_in_progress_record(
    db: Session,
    *,
    user_id: str,
    token_id: str,
    tool_name: str,
    idempotency_key: str,
    request_hash: str,
    now: datetime,
) -> BeginIdempotentOperationResult:
    record = models.MCPIdempotencyRecord(
        id=uuid.uuid4().hex,
        user_id=user_id,
        token_id=token_id,
        tool_name=tool_name,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        status=IDEMPOTENCY_STATUS_IN_PROGRESS,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=_in_progress_ttl_seconds()),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return BeginIdempotentOperationResult(
        status="created",
        request_hash=request_hash,
        record=record,
    )


def resolve_idempotent_replay(
    db: Session,
    *,
    record: models.MCPIdempotencyRecord,
    request_hash: str,
    now: datetime | None = None,
    recover_expired_in_progress: bool = True,
    recover_failed: bool = True,
) -> BeginIdempotentOperationResult | None:
    current_time = now or _now()

    if record.request_hash != request_hash:
        raise IdempotencyConflict(
            tool_name=record.tool_name,
            idempotency_key=record.idempotency_key,
        )

    if record.status == IDEMPOTENCY_STATUS_COMPLETED:
        if _is_expired(record, current_time):
            db.delete(record)
            db.commit()
            return None
        return BeginIdempotentOperationResult(
            status="replay",
            request_hash=request_hash,
            record=record,
            response_json=record.response_json,
        )

    if record.status == IDEMPOTENCY_STATUS_IN_PROGRESS:
        if not _is_expired(record, current_time):
            raise IdempotencyInProgress(
                tool_name=record.tool_name,
                idempotency_key=record.idempotency_key,
            )

        if not recover_expired_in_progress:
            raise IdempotencyStateUncertain(
                tool_name=record.tool_name,
                idempotency_key=record.idempotency_key,
                message=(
                    "La operación pudo haberse aplicado, pero la respuesta "
                    "idempotente no quedó confirmada."
                ),
            )

        updated = db.execute(
            update(models.MCPIdempotencyRecord)
            .where(
                models.MCPIdempotencyRecord.id == record.id,
                models.MCPIdempotencyRecord.status == IDEMPOTENCY_STATUS_IN_PROGRESS,
                models.MCPIdempotencyRecord.expires_at == record.expires_at,
            )
            .values(
                updated_at=current_time,
                expires_at=current_time + timedelta(seconds=_in_progress_ttl_seconds()),
            )
        )
        if updated.rowcount == 0:
            db.rollback()
            raise IdempotencyInProgress(
                tool_name=record.tool_name,
                idempotency_key=record.idempotency_key,
            )
        db.commit()
        refreshed = get_idempotency_record(
            db,
            user_id=record.user_id,
            token_id=record.token_id,
            tool_name=record.tool_name,
            idempotency_key=record.idempotency_key,
        )
        assert refreshed is not None
        return BeginIdempotentOperationResult(
            status="created",
            request_hash=request_hash,
            record=refreshed,
            recovered=True,
        )

    if record.status == IDEMPOTENCY_STATUS_FAILED:
        if not recover_failed:
            raise IdempotencyInProgress(
                tool_name=record.tool_name,
                idempotency_key=record.idempotency_key,
            )
        if _is_expired(record, current_time):
            db.delete(record)
            db.commit()
            return None

        db.execute(
            update(models.MCPIdempotencyRecord)
            .where(models.MCPIdempotencyRecord.id == record.id)
            .values(
                status=IDEMPOTENCY_STATUS_IN_PROGRESS,
                response_json=None,
                resource_version_before=None,
                resource_version_after=None,
                updated_at=current_time,
                expires_at=current_time + timedelta(seconds=_in_progress_ttl_seconds()),
            )
        )
        db.commit()
        refreshed = get_idempotency_record(
            db,
            user_id=record.user_id,
            token_id=record.token_id,
            tool_name=record.tool_name,
            idempotency_key=record.idempotency_key,
        )
        assert refreshed is not None
        return BeginIdempotentOperationResult(
            status="created",
            request_hash=request_hash,
            record=refreshed,
            recovered=True,
        )

    raise ValueError(f"Estado de idempotencia no soportado: {record.status}")


def begin_idempotent_operation(
    db: Session,
    *,
    user_id: str,
    token_id: str,
    tool_name: str,
    idempotency_key: str,
    payload: Any,
    exclude_fields: set[str] | None = None,
    now: datetime | None = None,
    recover_expired_in_progress: bool = True,
    recover_failed: bool = True,
) -> BeginIdempotentOperationResult:
    validate_idempotency_key(idempotency_key)
    current_time = now or _now()
    request_hash = build_idempotency_request_hash(
        tool_name=tool_name,
        payload=payload,
        user_id=user_id,
        token_id=token_id,
        exclude_fields=exclude_fields,
    )

    for _ in range(3):
        existing = get_idempotency_record(
            db,
            user_id=user_id,
            token_id=token_id,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            resolved = resolve_idempotent_replay(
                db,
                record=existing,
                request_hash=request_hash,
                now=current_time,
                recover_expired_in_progress=recover_expired_in_progress,
                recover_failed=recover_failed,
            )
            if resolved is not None:
                return resolved
            continue

        try:
            return _create_in_progress_record(
                db,
                user_id=user_id,
                token_id=token_id,
                tool_name=tool_name,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=current_time,
            )
        except IntegrityError:
            db.rollback()

    existing = get_idempotency_record(
        db,
        user_id=user_id,
        token_id=token_id,
        tool_name=tool_name,
        idempotency_key=idempotency_key,
    )
    if existing is None:
        raise RuntimeError("No se pudo reservar la clave de idempotencia")
    resolved = resolve_idempotent_replay(
        db,
        record=existing,
        request_hash=request_hash,
        now=current_time,
        recover_expired_in_progress=recover_expired_in_progress,
        recover_failed=recover_failed,
    )
    if resolved is None:
        raise RuntimeError("No se pudo reciclar la clave de idempotencia expirada")
    return resolved


def complete_idempotent_operation(
    db: Session,
    *,
    user_id: str,
    token_id: str,
    tool_name: str,
    idempotency_key: str,
    response_json: Mapping[str, Any],
    resource_version_before: int | None = None,
    resource_version_after: int | None = None,
    request_hash: str | None = None,
    now: datetime | None = None,
) -> models.MCPIdempotencyRecord:
    current_time = now or _now()
    record = get_idempotency_record(
        db,
        user_id=user_id,
        token_id=token_id,
        tool_name=tool_name,
        idempotency_key=idempotency_key,
    )
    if record is None:
        raise ResourceNotFound(
            "MCPIdempotencyRecord",
            idempotency_key,
            "Registro de idempotencia no encontrado",
        )

    if request_hash is not None and record.request_hash != request_hash:
        raise IdempotencyConflict(tool_name=tool_name, idempotency_key=idempotency_key)

    record.status = IDEMPOTENCY_STATUS_COMPLETED
    record.response_json = _normalise_for_json(response_json)
    record.resource_version_before = resource_version_before
    record.resource_version_after = resource_version_after
    record.updated_at = current_time
    record.expires_at = current_time + timedelta(hours=_ttl_hours())
    db.commit()
    db.refresh(record)
    return record


def fail_idempotent_operation(
    db: Session,
    *,
    user_id: str,
    token_id: str,
    tool_name: str,
    idempotency_key: str,
    request_hash: str | None = None,
    error_payload: Mapping[str, Any] | None = None,
    persist_failure: bool = False,
    failure_ttl_seconds: int = DEFAULT_FAILED_TTL_SECONDS,
    now: datetime | None = None,
) -> None:
    current_time = now or _now()
    record = get_idempotency_record(
        db,
        user_id=user_id,
        token_id=token_id,
        tool_name=tool_name,
        idempotency_key=idempotency_key,
    )
    if record is None:
        return

    if request_hash is not None and record.request_hash != request_hash:
        raise IdempotencyConflict(tool_name=tool_name, idempotency_key=idempotency_key)

    if persist_failure:
        record.status = IDEMPOTENCY_STATUS_FAILED
        record.response_json = (
            _normalise_for_json(error_payload) if error_payload is not None else None
        )
        record.resource_version_before = None
        record.resource_version_after = None
        record.updated_at = current_time
        record.expires_at = current_time + timedelta(seconds=failure_ttl_seconds)
        db.commit()
        return

    db.delete(record)
    db.commit()


def purge_expired_idempotency_records(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    current_time = now or _now()
    result = db.execute(
        delete(models.MCPIdempotencyRecord).where(
            models.MCPIdempotencyRecord.expires_at <= current_time
        )
    )
    db.commit()
    return int(result.rowcount or 0)
