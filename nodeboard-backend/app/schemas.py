"""Esquemas Pydantic.

El formato expuesto por la API es exactamente el que maneja nodeboard.jsx,
así el frontend puede hacer fetch y setear estado sin transformaciones:

  node -> {id, type, x, y, w, title, ports, blocks, stages}
  edge -> {id, from: {nodeId, portId}, to: {nodeId, portId}, curved}
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- Nodos
class NodeSchema(BaseModel):
    id: Optional[str] = None
    type: Literal["card", "timeline"] = "card"
    x: float = 0
    y: float = 0
    w: float = 280
    title: str = ""
    ports: list[dict[str, Any]] = Field(default_factory=list)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    stages: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class NodeUpdate(BaseModel):
    """Actualización parcial: solo se aplican los campos enviados."""
    type: Optional[Literal["card", "timeline"]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    w: Optional[float] = None
    title: Optional[str] = None
    ports: Optional[list[dict[str, Any]]] = None
    blocks: Optional[list[dict[str, Any]]] = None
    stages: Optional[list[dict[str, Any]]] = None


# ---------------------------------------------------------------- Aristas
class PortRef(BaseModel):
    nodeId: str
    portId: str


class EdgeSchema(BaseModel):
    id: Optional[str] = None
    from_: PortRef = Field(alias="from")
    to: PortRef
    curved: bool = True

    model_config = ConfigDict(populate_by_name=True)


class EdgeUpdate(BaseModel):
    curved: Optional[bool] = None


# ---------------------------------------------------------------- Boards
class BoardCreate(BaseModel):
    name: str = "Tablero sin nombre"


class BoardRename(BaseModel):
    name: str


class BoardSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    edge_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class BoardState(BaseModel):
    """Estado completo del tablero, tal como lo consume el canvas."""
    id: str
    name: str
    updated_at: datetime
    nodes: list[NodeSchema]
    edges: list[EdgeSchema]


class BoardStateSave(BaseModel):
    """Payload para guardar todo el estado de una (autosave del canvas)."""
    name: Optional[str] = None
    nodes: list[NodeSchema] = Field(default_factory=list)
    edges: list[EdgeSchema] = Field(default_factory=list)
