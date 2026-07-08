"""Funciones reutilizables de resolución y autorización de recursos.

Cada función consulta SQLAlchemy y verifica que el recurso pertenezca
al usuario indicado.  Lanzan excepciones de dominio (no HTTP) para que
la capa HTTP decida cómo traducirlas.

Reglas:
- "no existe" y "pertenece a otro usuario" se tratan igual
  (ResourceNotFound) para evitar enumeración de recursos ajenos.
- No hacen commit, no cierran la sesión, no dependen de FastAPI.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from .errors import ResourceNotFound


def get_owned_studio(
    db: Session, user_id: str, studio_id: str
) -> models.Studio:
    """Retorna un Studio que pertenece a *user_id*, o lanza ResourceNotFound."""
    studio = (
        db.execute(
            select(models.Studio).where(
                models.Studio.id == studio_id,
                models.Studio.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )
    if not studio:
        raise ResourceNotFound("Studio", studio_id, "Studio no encontrado")
    return studio


def get_owned_folder(
    db: Session, user_id: str, folder_id: str
) -> models.Folder:
    """Retorna un Folder que pertenece al usuario (via Studio), o lanza ResourceNotFound."""
    folder = (
        db.execute(
            select(models.Folder)
            .join(models.Studio, models.Folder.studio_id == models.Studio.id)
            .where(
                models.Folder.id == folder_id,
                models.Studio.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )
    if not folder:
        raise ResourceNotFound("Folder", folder_id, "Carpeta no encontrada")
    return folder


def get_owned_board(
    db: Session, user_id: str, board_id: str
) -> models.Board:
    """Retorna un Board que pertenece al usuario (via Studio), o lanza ResourceNotFound."""
    board = (
        db.execute(
            select(models.Board)
            .join(models.Studio, models.Board.studio_id == models.Studio.id)
            .where(
                models.Board.id == board_id,
                models.Studio.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )
    if not board:
        raise ResourceNotFound("Board", board_id, "Tablero no encontrado")
    return board


def get_owned_node(
    db: Session, user_id: str, node_id: str
) -> models.Node:
    """Retorna un Node que pertenece al usuario (via Board→Studio), o lanza ResourceNotFound."""
    node = (
        db.execute(
            select(models.Node)
            .join(models.Board, models.Node.board_id == models.Board.id)
            .join(models.Studio, models.Board.studio_id == models.Studio.id)
            .where(
                models.Node.id == node_id,
                models.Studio.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )
    if not node:
        raise ResourceNotFound("Node", node_id, "Nodo no encontrado")
    return node


def get_owned_edge(
    db: Session, user_id: str, edge_id: str
) -> models.Edge:
    """Retorna un Edge que pertenece al usuario (via Board→Studio), o lanza ResourceNotFound."""
    edge = (
        db.execute(
            select(models.Edge)
            .join(models.Board, models.Edge.board_id == models.Board.id)
            .join(models.Studio, models.Board.studio_id == models.Studio.id)
            .where(
                models.Edge.id == edge_id,
                models.Studio.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )
    if not edge:
        raise ResourceNotFound("Edge", edge_id, "Arista no encontrada")
    return edge
