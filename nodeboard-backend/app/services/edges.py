"""Servicio de dominio para operaciones individuales sobre Edges.

Cubre creación, actualización y eliminación de aristas, con
verificación de ownership y validación de nodos origen/destino.
"""
import uuid

from sqlalchemy.orm import Session

from .. import models
from ..schemas import EdgeSchema, EdgeUpdate
from .authorization import get_owned_board, get_owned_edge
from .boards import edge_to_schema, increment_board_version
from .errors import ValidationFailure


def _new_id() -> str:
    return uuid.uuid4().hex


def create_edge(
    db: Session, user_id: str, board_id: str,
    payload: EdgeSchema, expected_version: int,
) -> EdgeSchema:
    """Crea una arista en un board, verificando ownership, nodos y versión."""
    board = get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, expected_version)
    try:
        node_ids = {n.id for n in board.nodes}
        if payload.from_.nodeId not in node_ids or payload.to.nodeId not in node_ids:
            raise ValidationFailure(
                "La arista referencia nodos que no existen en este tablero"
            )

        edge = models.Edge(
            id=payload.id or _new_id(),
            board_id=board.id,
            from_node=payload.from_.nodeId,
            from_port=payload.from_.portId,
            to_node=payload.to.nodeId,
            to_port=payload.to.portId,
            curved=payload.curved,
            label=payload.label,
        )
        db.add(edge)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(edge)
    return edge_to_schema(edge)


def update_edge(
    db: Session, user_id: str, edge_id: str,
    payload: EdgeUpdate, expected_version: int,
) -> EdgeSchema:
    """Actualiza parcialmente una arista verificando ownership y versión."""
    edge = get_owned_edge(db, user_id, edge_id)
    increment_board_version(db, edge.board_id, expected_version)
    try:
        if payload.curved is not None:
            edge.curved = payload.curved
        fields = payload.model_dump(exclude_unset=True)
        if "label" in fields:
            edge.label = fields["label"] if fields["label"] is not None else ""
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(edge)
    return edge_to_schema(edge)


def delete_edge(db: Session, user_id: str, edge_id: str, expected_version: int) -> None:
    """Elimina una arista verificando ownership y versión."""
    edge = get_owned_edge(db, user_id, edge_id)
    increment_board_version(db, edge.board_id, expected_version)
    try:
        db.delete(edge)
        db.commit()
    except Exception:
        db.rollback()
        raise
