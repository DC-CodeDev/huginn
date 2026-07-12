"""Validación MCP estricta para payloads de nodos.

Centraliza la matriz de campos compatibles por tipo para evitar
duplicación entre ``create_node`` y ``update_node``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import schemas
from ..services.errors import ValidationFailure

FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]


class MCPCardNodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["card"]
    title: str = ""
    x: FiniteNumber = 0
    y: FiniteNumber = 0
    w: FiniteNumber = 280
    ports: list[schemas.Port] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    blocks: list[schemas.Block] = Field(default_factory=list)


class MCPTimelineNodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["timeline"]
    title: str = ""
    x: FiniteNumber = 0
    y: FiniteNumber = 0
    w: FiniteNumber = 280
    ports: list[schemas.Port] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    orientation: Literal["horizontal", "vertical"] | None = None
    stages: list[schemas.TimelineStage] = Field(default_factory=list)


MCPNodeInput = Annotated[
    MCPCardNodeInput | MCPTimelineNodeInput,
    Field(discriminator="type"),
]


class MCPCardNodeChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    w: FiniteNumber | None = None
    ports: list[schemas.Port] | None = None
    tags: list[str] | None = None
    blocks: list[schemas.Block] | None = None


class MCPTimelineNodeChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    w: FiniteNumber | None = None
    ports: list[schemas.Port] | None = None
    tags: list[str] | None = None
    stages: list[schemas.TimelineStage] | None = None
    orientation: Literal["horizontal", "vertical"] | None = None


_UPDATE_MODELS = {
    "card": MCPCardNodeChanges,
    "timeline": MCPTimelineNodeChanges,
}


def validate_update_changes(
    node_type: str,
    changes: object,
) -> tuple[schemas.NodeUpdate, list[str]]:
    """Valida cambios parciales MCP y devuelve payload + campos cambiados."""
    model_cls = _UPDATE_MODELS.get(node_type)
    if model_cls is None:
        raise ValidationFailure(f"Tipo de nodo no soportado: {node_type}")

    parsed = model_cls.model_validate(changes)
    changed_fields = [
        field_name
        for field_name in parsed.__class__.model_fields
        if field_name in parsed.model_fields_set
    ]
    if not changed_fields:
        raise ValidationFailure("Debe especificar al menos un cambio")

    payload = schemas.NodeUpdate(**parsed.model_dump(exclude_unset=True))
    return payload, changed_fields
