"""Servicio de dominio para operaciones individuales sobre Nodes.

Cubre creación, actualización y eliminación de nodos, con
verificación de ownership y serialización Pydantic.
"""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import NodeSchema, NodeUpdate
from .authorization import get_owned_board, get_owned_node
from .boards import increment_board_version, node_to_schema


def _new_id() -> str:
    return uuid.uuid4().hex


def create_node(
    db: Session, user_id: str, board_id: str,
    payload: NodeSchema, expected_version: int,
) -> NodeSchema:
    """Crea un nodo en un board, verificando ownership y versión."""
    board = get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, expected_version)
    try:
        dumped = payload.model_dump()
        node = models.Node(
            id=payload.id or _new_id(),
            board_id=board.id,
            type=payload.type,
            x=payload.x,
            y=payload.y,
            w=payload.w,
            title=payload.title,
            ports=dumped["ports"],
            blocks=dumped["blocks"],
            stages=dumped["stages"],
            tags=dumped["tags"],
        )
        db.add(node)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(node)
    return node_to_schema(node)


def update_node(
    db: Session, user_id: str, node_id: str,
    payload: NodeUpdate, expected_version: int,
) -> NodeSchema:
    """Actualiza parcialmente un nodo verificando ownership y versión."""
    node = get_owned_node(db, user_id, node_id)
    increment_board_version(db, node.board_id, expected_version)
    try:
        data = payload.model_dump(exclude_unset=True)
        data.pop("expected_version", None)
        if "tags" in data and data["tags"] is None:
            data["tags"] = []
        for field, value in data.items():
            setattr(node, field, value)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(node)
    return node_to_schema(node)


def delete_node(db: Session, user_id: str, node_id: str, expected_version: int) -> None:
    """Elimina un nodo y todas sus edges vinculadas, verificando versión."""
    node = get_owned_node(db, user_id, node_id)
    increment_board_version(db, node.board_id, expected_version)
    try:
        # Eliminar edges que referencian este nodo (origen o destino)
        edges = db.scalars(
            select(models.Edge).where(
                models.Edge.board_id == node.board_id,
                or_(
                    models.Edge.from_node == node_id,
                    models.Edge.to_node == node_id,
                ),
            )
        ).all()
        for e in edges:
            db.delete(e)
        db.delete(node)
        db.commit()
    except Exception:
        db.rollback()
        raise
