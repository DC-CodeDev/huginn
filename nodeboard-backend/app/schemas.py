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


class NodeCreateRequest(NodeSchema):
    """Creación de nodo con optimistic locking."""
    expected_version: int


class NodeUpdateRequest(NodeUpdate):
    """Actualización de nodo con optimistic locking."""
    expected_version: int


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


class EdgeCreateRequest(EdgeSchema):
    """Creación de arista con optimistic locking."""
    expected_version: int


class EdgeUpdateRequest(EdgeUpdate):
    """Actualización de arista con optimistic locking."""
    expected_version: int


# ---------------------------------------------------------------- Auth
class LoginRequest(BaseModel):
    code: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    avatar_url: str
    auth_provider: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Studios y Folders
StudioColor = Literal["terracota", "azul", "verde", "dorado", "violeta", "turquesa"]


class StudioCreate(BaseModel):
    name: str
    color: StudioColor


class StudioOut(BaseModel):
    id: str
    name: str
    color: str
    user_id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class FolderCreate(BaseModel):
    name: str
    studio_id: str


class FolderOut(BaseModel):
    id: str
    name: str
    studio_id: str
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- Boards
class BoardCreate(BaseModel):
    name: str = "Tablero sin nombre"
    studio_id: str
    folder_id: Optional[str] = None


class BoardRename(BaseModel):
    name: str
    expected_version: int


class BoardSummary(BaseModel):
    id: str
    name: str
    version: int
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    edge_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class BoardState(BaseModel):
    """Estado completo del tablero, tal como lo consume el canvas."""
    id: str
    name: str
    version: int
    updated_at: datetime
    nodes: list[NodeSchema]
    edges: list[EdgeSchema]


class BoardStateSave(BaseModel):
    """Payload para guardar todo el estado de una (autosave del canvas)."""
    name: Optional[str] = None
    expected_version: int
    nodes: list[NodeSchema] = Field(default_factory=list)
    edges: list[EdgeSchema] = Field(default_factory=list)


class StudioBoardsOut(BaseModel):
    """Boards de un Studio: separa raíz de los que están en carpetas."""
    root_boards: list[BoardSummary]
    folder_boards: list[BoardSummary]


class MCPAuthCheck(BaseModel):
    """Respuesta del endpoint de diagnóstico auth-check.

    Nunca incluye token completo, token_hash ni email del usuario.
    """
    authenticated: bool = True
    token_id: str
    token_prefix: str
    scopes: list[str]
    constraints: MCPTokenConstraints | None = None
    expires_at: datetime
    last_used_at: datetime | None = None


# ---------------------------------------------------------------- MCP Tokens

MCP_SCOPES: set[str] = {
    "studios:read",
    "folders:read",
    "boards:read",
    "nodes:read",
    "boards:create",
    "boards:update",
    "boards:delete",
    "nodes:create",
    "nodes:update",
    "nodes:delete",
    "edges:create",
    "edges:update",
    "edges:delete",
    "layouts:execute",
}

MAX_SCOPES = 20


def normalise_scopes(scopes: list[str]) -> list[str]:
    """Valida, deduplica y ordena scopes.  Lanza ValidationFailure si hay scopes inválidos."""
    unique: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        if scope in seen:
            continue
        if scope not in MCP_SCOPES:
            from .services.errors import InvalidScope

            raise InvalidScope([scope])
        unique.append(scope)
        seen.add(scope)
    if len(unique) > MAX_SCOPES:
        from .services.errors import ValidationFailure

        raise ValidationFailure(f"Máximo {MAX_SCOPES} scopes por token")
    return unique


class MCPTokenConstraints(BaseModel):
    studio_ids: list[str] | None = None
    board_ids: list[str] | None = None


class MCPTokenCreate(BaseModel):
    name: str
    scopes: list[str]
    expires_in_days: int = 90
    constraints: MCPTokenConstraints | None = None


class MCPTokenCreated(BaseModel):
    """Respuesta que contiene el token completo — única exposición."""

    id: str
    name: str
    token: str
    token_prefix: str
    scopes: list[str]
    constraints: MCPTokenConstraints | None
    created_at: datetime
    expires_at: datetime
    warning: str = "Este token no volverá a mostrarse."


class MCPTokenSummary(BaseModel):
    """Resumen público — nunca incluye token ni token_hash."""

    id: str
    name: str
    token_prefix: str
    scopes: list[str]
    constraints: MCPTokenConstraints | None
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
