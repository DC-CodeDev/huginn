"""Esquemas Pydantic.

El formato expuesto por la API es exactamente el que maneja el canvas,
así el frontend puede hacer fetch y setear estado sin transformaciones:

  node -> {id, type, x, y, w, title, ports, blocks, stages, tags}
  edge -> {id, from: {nodeId, portId}, to: {nodeId, portId}, curved, label}

Las estructuras internas del nodo (ports, blocks, stages) se validan con tipos
reales que espejan el modelo del frontend (src/types.ts): puertos con colores de
una paleta cerrada y bloques como union discriminada por `type`.
"""
from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# ------------------------------------------------------- Estructuras del nodo
# Espejan src/types.ts (Port, Block, TimelineStage) — fuente de verdad del dominio.

# Los 6 colores reales de PORT_COLORS (paleta cerrada, no str libre).
PortColor = Literal["#C4847A", "#4ADE80", "#F87171", "#60A5FA", "#C084FC", "#E8EBF0"]


class Port(BaseModel):
    id: str
    side: Literal["left", "right"]
    color: PortColor
    label: str


class TextBlock(BaseModel):
    type: Literal["text"]
    id: str
    value: str


class NumberBlock(BaseModel):
    type: Literal["number"]
    id: str
    value: str
    label: str


class TableBlock(BaseModel):
    type: Literal["table"]
    id: str
    data: list[list[str]]


class ImageBlock(BaseModel):
    type: Literal["image"]
    id: str
    src: Optional[str]


# Union discriminada por `type`: Pydantic elige la variante según ese campo.
Block = Annotated[
    Union[TextBlock, NumberBlock, TableBlock, ImageBlock],
    Field(discriminator="type"),
]


class TimelineStage(BaseModel):
    id: str
    title: str
    tags: list[str]


# ---------------------------------------------------------------- Nodos
class NodeSchema(BaseModel):
    id: Optional[str] = None
    type: Literal["card", "timeline"] = "card"
    x: float = 0
    y: float = 0
    w: float = 280
    title: str = ""
    ports: list[Port] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)
    stages: list[TimelineStage] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class NodeUpdate(BaseModel):
    """Actualización parcial: solo se aplican los campos enviados."""
    type: Optional[Literal["card", "timeline"]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    w: Optional[float] = None
    title: Optional[str] = None
    ports: Optional[list[Port]] = None
    blocks: Optional[list[Block]] = None
    stages: Optional[list[TimelineStage]] = None
    tags: Optional[list[str]] = None


# ---------------------------------------------------------------- Aristas
class PortRef(BaseModel):
    nodeId: str
    portId: str


class EdgeSchema(BaseModel):
    id: Optional[str] = None
    from_: PortRef = Field(alias="from")
    to: PortRef
    curved: bool = True
    label: str = ""

    model_config = ConfigDict(populate_by_name=True)


class EdgeUpdate(BaseModel):
    curved: Optional[bool] = None
    label: Optional[str] = None


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
