"""Modelos ORM del nodeboard.

Los nodos guardan sus partes flexibles (ports, blocks, stages) como JSON,
porque su estructura varía según el tipo de nodo y evoluciona con el frontend.
Las aristas se guardan normalizadas para poder consultarlas o validarlas.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Board(Base):
    __tablename__ = "boards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), default="Tablero sin nombre")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
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
