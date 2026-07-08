"""Servicio de dominio para el reemplazo completo del estado de un Board.

Operación atómica: validación del snapshot, optimistic locking,
eliminación de nodes/edges anteriores, inserción de los nuevos,
todo en una única transacción.
"""
import uuid

from sqlalchemy.orm import Session

from .. import models
from ..schemas import BoardStateSave
from .authorization import get_owned_board
from .boards import board_state, increment_board_version
from .errors import ValidationFailure


def load_board_state(
    db: Session, user_id: str, board_id: str
) -> BoardStateSave:
    """Carga el estado completo de un board verificando ownership."""
    board = get_owned_board(db, user_id, board_id)
    return board_state(board)


def save_board_state(
    db: Session,
    user_id: str,
    board_id: str,
    payload: BoardStateSave,
) -> BoardStateSave:
    """Reemplaza atómicamente nodes y edges de un board.

    Usa optimistic locking para evitar sobrescrituras concurrentes.
    Valida el snapshot antes de modificar cualquier registro.
    Si algo falla, se hace rollback y el board queda intacto.
    """
    board = get_owned_board(db, user_id, board_id)

    # 1. Asignar IDs auto-generados a nodes/edges sin ID
    _ensure_ids(payload)

    # 2. Validar el snapshot antes de tocar la BD
    _validate_snapshot(payload)

    # 3. Ejecutar optimistic locking + reemplazo con rollback explícito
    try:
        # 3a. Optimistic locking: verificar versión
        increment_board_version(db, board_id, payload.expected_version)

        # 3b. Actualizar nombre si viene en el payload
        if payload.name is not None:
            board.name = payload.name

        # 3c. Reemplazo total: borrar existente y crear nuevo
        for n in list(board.nodes):
            db.delete(n)
        for e in list(board.edges):
            db.delete(e)
        db.flush()

        for n in payload.nodes:
            dumped = n.model_dump()
            db.add(models.Node(
                id=n.id,
                board_id=board.id,
                type=n.type, x=n.x, y=n.y, w=n.w, title=n.title,
                ports=dumped["ports"], blocks=dumped["blocks"],
                stages=dumped["stages"], tags=dumped["tags"],
            ))

        for e in payload.edges:
            db.add(models.Edge(
                id=e.id,
                board_id=board.id,
                from_node=e.from_.nodeId, from_port=e.from_.portId,
                to_node=e.to.nodeId, to_port=e.to.portId,
                curved=e.curved, label=e.label,
            ))

        db.commit()

    except Exception:
        db.rollback()
        raise

    db.refresh(board)
    return board_state(board)


def _ensure_ids(payload: BoardStateSave) -> None:
    """Asigna UUIDs a nodes y edges que no tengan ID."""
    for n in payload.nodes:
        if not n.id:
            n.id = uuid.uuid4().hex
    for e in payload.edges:
        if not e.id:
            e.id = uuid.uuid4().hex


def _validate_snapshot(payload: BoardStateSave) -> None:
    """Valida que el snapshot sea consistente antes de persistir.

    - IDs de nodes únicos
    - IDs de edges únicos
    - Cada edge referencia nodes existentes en el mismo snapshot
    """
    node_ids: set[str] = set()
    for n in payload.nodes:
        if n.id in node_ids:
            raise ValidationFailure(f"ID de nodo duplicado: {n.id}")
        node_ids.add(n.id)

    for e in payload.edges:
        if e.id in {x.id for x in payload.edges if x is not e}:
            pass  # ya validamos abajo con set

    edge_ids: set[str] = set()
    for e in payload.edges:
        if e.id in edge_ids:
            raise ValidationFailure(f"ID de arista duplicado: {e.id}")
        edge_ids.add(e.id)

        if e.from_.nodeId not in node_ids:
            raise ValidationFailure(
                "La arista referencia nodo origen que no existe en el snapshot"
            )
        if e.to.nodeId not in node_ids:
            raise ValidationFailure(
                "La arista referencia nodo destino que no existe en el snapshot"
            )
