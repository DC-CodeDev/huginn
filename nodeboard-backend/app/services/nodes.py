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


def _build_node_model(
    board_id: str,
    payload: NodeSchema,
    overrides: dict | None = None,
) -> models.Node:
    """Construye un ORM Node a partir de un payload validado sin persistir.

    No realiza ningún commit — el caller es responsable de añadir el
    nodo a la sesión y hacer flush/commit.
    """
    dumped = payload.model_dump()
    kw = {
        "id": payload.id or _new_id(),
        "board_id": board_id,
        "type": payload.type,
        "x": payload.x,
        "y": payload.y,
        "w": payload.w,
        "title": payload.title,
        "ports": dumped["ports"],
        "blocks": dumped["blocks"],
        "stages": dumped["stages"],
        "tags": dumped["tags"],
        "orientation": payload.orientation,
    }
    if overrides:
        kw.update(overrides)
    return models.Node(**kw)


def create_node(
    db: Session, user_id: str, board_id: str,
    payload: NodeSchema, expected_version: int,
    board: models.Board | None = None,
) -> NodeSchema:
    """Crea un nodo en un board, verificando ownership y versión."""
    board = board or get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, expected_version)
    try:
        node = _build_node_model(board.id, payload)
        db.add(node)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(node)
    return node_to_schema(node)


def create_nodes_batch(
    db: Session,
    user_id: str,
    board_id: str,
    payloads: list[NodeSchema],
    expected_version: int,
    board: models.Board | None = None,
) -> dict:
    """Crea múltiples nodos en un mismo board en una única transacción.

    La operación es estrictamente atómica: cualquier fallo revierte
    completamente sin nodos creados ni versión incrementada.

    Devuelve un diccionario con:
    - ``nodes``: lista de ``NodeSchema`` (mismo orden que los payloads)
    - ``client_map``: ``dict[int, str]`` mapeando índice a ID real
    """
    board = board or get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, expected_version)
    try:
        nodes: list[models.Node] = []
        for p in payloads:
            node = _build_node_model(board.id, p)
            db.add(node)
            nodes.append(node)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    schemas_list: list[NodeSchema] = []
    for n in nodes:
        db.refresh(n)
        schemas_list.append(node_to_schema(n))
    return {
        "nodes": schemas_list,
        "client_map": {i: n.id for i, n in enumerate(nodes)},
    }


def update_node(
    db: Session, user_id: str, node_id: str,
    payload: NodeUpdate, expected_version: int,
    node: models.Node | None = None,
    board: models.Board | None = None,
) -> NodeSchema:
    """Actualiza parcialmente un nodo verificando ownership y versión."""
    node = node or get_owned_node(db, user_id, node_id)
    board_id = board.id if board is not None else node.board_id
    increment_board_version(db, board_id, expected_version)
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


def move_node(
    db: Session, user_id: str, node_id: str,
    x: float, y: float,
    expected_version: int,
    node: models.Node | None = None,
    board: models.Board | None = None,
) -> tuple[NodeSchema, dict[str, float], dict[str, float]]:
    """Mueve un nodo a una nueva posición verificando ownership y versión.

    Únicamente modifica las coordenadas ``x`` e ``y``, preservando el
    resto del contenido del nodo.  Devuelve (schema, prev_pos, new_pos).

    El movimiento completo de ambos ejes es obligatorio — la tool MCP
    ya valida que ambos estén presentes antes de llegar aquí.
    """
    node = node or get_owned_node(db, user_id, node_id)
    board_id = board.id if board is not None else node.board_id
    increment_board_version(db, board_id, expected_version)
    try:
        prev_pos: dict[str, float] = {"x": node.x, "y": node.y}
        node.x = x
        node.y = y
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(node)
    node_schema = node_to_schema(node)
    new_pos: dict[str, float] = {"x": node_schema.x, "y": node_schema.y}
    return node_schema, prev_pos, new_pos


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
