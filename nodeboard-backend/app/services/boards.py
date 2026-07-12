"""Servicio de dominio para Boards.

Cubre listado, creación, lectura, renombrado y eliminación de boards,
con serialización completa del estado (nodos y edges incluidos).

El reemplazo completo del estado (save_board_state) se extraerá por
separado.
"""
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import models, schemas
from .authorization import get_owned_board, get_owned_folder, get_owned_studio
from .errors import ResourceNotFound, ValidationFailure, VersionConflict


# ------------------------------------------------------------------
# optimistic locking
# ------------------------------------------------------------------


def increment_board_version(
    db: Session,
    board_id: str,
    expected_version: int,
) -> None:
    """Incrementa atómicamente la versión de un board.

    Realiza ``UPDATE boards SET version = version + 1 WHERE id = :id AND version = :expected``.
    Si no afecta filas, consulta la versión actual y lanza ``VersionConflict``.
    """
    now = models._now()
    result = db.execute(
        update(models.Board)
        .where(
            models.Board.id == board_id,
            models.Board.version == expected_version,
        )
        .values(version=models.Board.version + 1, updated_at=now)
    )
    if result.rowcount == 0:
        board = db.get(models.Board, board_id)
        if board is None:
            raise ResourceNotFound("Board", board_id, "Tablero no encontrado")
        raise VersionConflict(
            board_id=board_id,
            expected_version=expected_version,
            current_version=board.version,
        )


# ------------------------------------------------------------------
# helpers de serialización
# ------------------------------------------------------------------


def node_to_schema(n: models.Node) -> schemas.NodeSchema:
    return schemas.NodeSchema.model_validate(n)


def edge_to_schema(e: models.Edge) -> schemas.EdgeSchema:
    return schemas.EdgeSchema(
        id=e.id,
        **{"from": {"nodeId": e.from_node, "portId": e.from_port}},
        to={"nodeId": e.to_node, "portId": e.to_port},
        curved=e.curved,
        label=e.label,
    )


def board_state(board: models.Board) -> schemas.BoardState:
    """Construye el estado completo de un board con sus nodos y edges."""
    return schemas.BoardState(
        id=board.id,
        name=board.name,
        version=board.version,
        updated_at=board.updated_at,
        nodes=[node_to_schema(n) for n in board.nodes],
        edges=[edge_to_schema(e) for e in board.edges],
    )


def _board_summary(
    board: models.Board, db: Session
) -> schemas.BoardSummary:
    """Construye un resumen de board con conteos de nodos y edges."""
    s = schemas.BoardSummary.model_validate(board)
    s.node_count = db.scalar(
        select(func.count())
        .select_from(models.Node)
        .where(models.Node.board_id == board.id)
    ) or 0
    s.edge_count = db.scalar(
        select(func.count())
        .select_from(models.Edge)
        .where(models.Edge.board_id == board.id)
    ) or 0
    return s


# ------------------------------------------------------------------
# listado
# ------------------------------------------------------------------


def list_boards(
    db: Session, user_id: str
) -> list[schemas.BoardSummary]:
    """Retorna todos los boards accesibles por el usuario, ordenados por updated_at descendente."""
    boards = db.scalars(
        select(models.Board)
        .join(models.Studio, models.Board.studio_id == models.Studio.id)
        .where(models.Studio.user_id == user_id)
        .order_by(models.Board.updated_at.desc())
    ).all()
    return [_board_summary(b, db) for b in boards]


def list_studio_boards(
    db: Session, user_id: str, studio_id: str
) -> schemas.StudioBoardsOut:
    """Retorna los boards de un studio, separados en raíz y folderizados.

    Verifica ownership del studio antes de listar.
    """
    get_owned_studio(db, user_id, studio_id)
    all_boards = db.scalars(
        select(models.Board)
        .where(models.Board.studio_id == studio_id)
        .order_by(models.Board.updated_at.desc())
    ).all()

    root_boards: list[schemas.BoardSummary] = []
    folder_boards: list[schemas.BoardSummary] = []
    for b in all_boards:
        summary = _board_summary(b, db)
        if b.folder_id is None:
            root_boards.append(summary)
        else:
            folder_boards.append(summary)
    return schemas.StudioBoardsOut(
        root_boards=root_boards, folder_boards=folder_boards
    )


def list_folder_boards(
    db: Session, user_id: str, folder_id: str
) -> list[schemas.BoardSummary]:
    """Retorna los boards dentro de un folder, verificando ownership."""
    get_owned_folder(db, user_id, folder_id)
    boards = db.scalars(
        select(models.Board)
        .where(models.Board.folder_id == folder_id)
        .order_by(models.Board.updated_at.desc())
    ).all()
    return [_board_summary(b, db) for b in boards]


# ------------------------------------------------------------------
# creación
# ------------------------------------------------------------------


def create_board(
    db: Session, user_id: str, payload: schemas.BoardCreate
) -> schemas.BoardState:
    """Crea un board verificando studio y folder.

    Valida que el folder (si se indica) pertenezca al mismo studio.
    El board se crea con version=1.
    """
    get_owned_studio(db, user_id, payload.studio_id)
    if payload.folder_id:
        folder = get_owned_folder(db, user_id, payload.folder_id)
        if folder.studio_id != payload.studio_id:
            raise ValidationFailure(
                "La carpeta no pertenece al Studio especificado"
            )
    board = models.Board(
        id=uuid.uuid4().hex,
        name=payload.name,
        studio_id=payload.studio_id,
        folder_id=payload.folder_id,
        version=1,
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return board_state(board)


# ------------------------------------------------------------------
# lectura
# ------------------------------------------------------------------


def get_board(
    db: Session, user_id: str, board_id: str
) -> schemas.BoardState:
    """Retorna el estado completo de un board verificando ownership."""
    board = get_owned_board(db, user_id, board_id)
    return board_state(board)


# ------------------------------------------------------------------
# renombrado
# ------------------------------------------------------------------


def rename_board(
    db: Session,
    user_id: str,
    board_id: str,
    payload: schemas.BoardRename,
    board: models.Board | None = None,
) -> schemas.BoardState:
    """Renombra un board verificando ownership y versión."""
    board = board or get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, payload.expected_version)
    try:
        board.name = payload.name
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(board)
    return board_state(board)


# ------------------------------------------------------------------
# eliminación
# ------------------------------------------------------------------


def delete_board(
    db: Session, user_id: str, board_id: str, expected_version: int
) -> None:
    """Elimina un board y sus nodos/edges en cascada, verificando versión."""
    board = get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, expected_version)
    try:
        db.delete(board)
        db.commit()
    except Exception:
        db.rollback()
        raise
