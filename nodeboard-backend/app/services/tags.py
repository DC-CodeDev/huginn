"""Servicio de dominio para tags de Board.

Operación: obtener tags únicos de todos los nodes de un board,
con el orden y criterio de deduplicación que espera el frontend.
"""
from sqlalchemy.orm import Session

from .authorization import get_owned_board


def list_board_tags(
    db: Session, user_id: str, board_id: str
) -> list[str]:
    """Retorna los tags únicos de un board, ordenados case-insensitive.

    Verifica ownership del board antes de leer los tags.
    No hace commit ni modifica la base de datos.
    """
    board = get_owned_board(db, user_id, board_id)
    unique: dict[str, None] = {}
    for node in board.nodes:
        for tag in node.tags or []:
            if isinstance(tag, str) and tag and tag not in unique:
                unique[tag] = None
    return sorted(unique, key=str.lower)
