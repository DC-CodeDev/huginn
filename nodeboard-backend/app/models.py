"""Modelos ORM del nodeboard.

Los nodos guardan sus partes flexibles (ports, blocks, stages) como JSON,
porque su estructura varía según el tipo de nodo y evoluciona con el frontend.
Las aristas se guardan normalizadas para poder consultarlas o validarlas.

Jerarquía de organización:
  Studio -> Folder -> Board
  Studio -> Board (directo, sin carpeta)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    """Devuelve la hora actual como datetime NAIVE en UTC.

    Convención del proyecto: todos los datetimes guardados en la BD son
    naive pero representan siempre UTC.  Nunca usar datetime.now() a secas
    (hora local) ni datetime.now(timezone.utc) directo (aware) en este
    contexto sin .replace(tzinfo=None).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200))
    avatar_url: Mapped[str] = mapped_column(String(1000), default="")
    auth_provider: Mapped[str] = mapped_column(String(50), default="google")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    studios: Mapped[list["Studio"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mcp_tokens: Mapped[list["MCPToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mcp_idempotency_records: Mapped[list["MCPIdempotencyRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    mcp_audit_logs: Mapped[list["MCPAuditLog"]] = relationship(
        back_populates="user"
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Studio(Base):
    __tablename__ = "studios"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(20))
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped["User"] = relationship(back_populates="studios")
    folders: Mapped[list["Folder"]] = relationship(
        back_populates="studio", cascade="all, delete-orphan"
    )
    boards: Mapped[list["Board"]] = relationship(
        back_populates="studio", cascade="all, delete-orphan"
    )


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    studio_id: Mapped[str] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True
    )

    studio: Mapped["Studio"] = relationship(back_populates="folders")
    boards: Mapped[list["Board"]] = relationship(
        back_populates="folder", foreign_keys="[Board.folder_id]"
    )


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), default="Tablero sin nombre")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )
    studio_id: Mapped[str] = mapped_column(
        ForeignKey("studios.id", ondelete="CASCADE"), index=True
    )
    folder_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), index=True, nullable=True
    )

    studio: Mapped["Studio"] = relationship(back_populates="boards")
    folder: Mapped[Optional["Folder"]] = relationship(
        back_populates="boards", foreign_keys=[folder_id]
    )
    nodes: Mapped[list["Node"]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )
    edges: Mapped[list["Edge"]] = relationship(
        back_populates="board", cascade="all, delete-orphan"
    )


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    board_id: Mapped[str] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(20), default="card")  # card | timeline
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)
    w: Mapped[float] = mapped_column(Float, default=280)
    title: Mapped[str] = mapped_column(String(300), default="")

    # Estructuras flexibles que espera el frontend
    ports: Mapped[list] = mapped_column(JSON, default=list)    # [{id, side, color, label}]
    blocks: Mapped[list] = mapped_column(JSON, default=list)   # [{id, type, ...}]
    stages: Mapped[list] = mapped_column(JSON, default=list)   # [{id, title, tags}]
    tags: Mapped[list] = mapped_column(JSON, default=list)     # ["texto libre", ...]
    orientation: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default=None)

    board: Mapped["Board"] = relationship(back_populates="nodes")


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    board_id: Mapped[str] = mapped_column(
        ForeignKey("boards.id", ondelete="CASCADE"), index=True
    )
    from_node: Mapped[str] = mapped_column(String(64))
    from_port: Mapped[str] = mapped_column(String(64))
    to_node: Mapped[str] = mapped_column(String(64))
    to_port: Mapped[str] = mapped_column(String(64))
    curved: Mapped[bool] = mapped_column(Boolean, default=True)
    label: Mapped[str] = mapped_column(String(300), default="")  # texto libre: "depende de", etc.

    board: Mapped["Board"] = relationship(back_populates="edges")


class MCPToken(Base):
    __tablename__ = "mcp_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    constraints: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="mcp_tokens")
    idempotency_records: Mapped[list["MCPIdempotencyRecord"]] = relationship(
        back_populates="token", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["MCPAuditLog"]] = relationship(
        back_populates="token"
    )


class MCPIdempotencyRecord(Base):
    __tablename__ = "mcp_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "token_id",
            "tool_name",
            "idempotency_key",
            name="uq_mcp_idempotency_token_tool_key",
        ),
        Index("ix_mcp_idempotency_records_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_id: Mapped[str] = mapped_column(
        ForeignKey("mcp_tokens.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    resource_version_before: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    resource_version_after: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    user: Mapped["User"] = relationship(back_populates="mcp_idempotency_records")
    token: Mapped["MCPToken"] = relationship(back_populates="idempotency_records")


class MCPAuditLog(Base):
    __tablename__ = "mcp_audit_log"
    __table_args__ = (
        Index("ix_mcp_audit_log_tool_name", "tool_name"),
        Index("ix_mcp_audit_log_request_id", "request_id"),
        Index("ix_mcp_audit_log_resource_id", "resource_id"),
        Index("ix_mcp_audit_log_status", "status"),
        Index("ix_mcp_audit_log_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    token_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("mcp_tokens.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    client_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    version_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version_after: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    is_replay: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa_false())
    idempotency_key_prefix: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    user: Mapped[Optional["User"]] = relationship(back_populates="mcp_audit_logs")
    token: Mapped[Optional["MCPToken"]] = relationship(back_populates="audit_logs")
