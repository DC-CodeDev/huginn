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


def _build_edge_model(
    board_id: str,
    payload: EdgeSchema,
    overrides: dict | None = None,
) -> models.Edge:
    """Construye un ORM Edge a partir de un payload validado sin persistir.

    No realiza ningún commit — el caller es responsable de añadir el
    edge a la sesión y hacer flush/commit.
    """
    kw = {
        "id": payload.id or _new_id(),
        "board_id": board_id,
        "from_node": payload.from_.nodeId,
        "from_port": payload.from_.portId,
        "to_node": payload.to.nodeId,
        "to_port": payload.to.portId,
        "curved": payload.curved,
        "label": payload.label,
    }
    if overrides:
        kw.update(overrides)
    return models.Edge(**kw)


def _validate_edge_endpoints(
    board_nodes: list[models.Node],
    payload: EdgeSchema,
) -> None:
    """Valida que los nodos y puertos referenciados por un edge existan en el board.

    Lanza ``ValidationFailure`` si algún nodo o puerto no existe.
    """
    node_ids = {n.id for n in board_nodes}
    if payload.from_.nodeId not in node_ids or payload.to.nodeId not in node_ids:
        raise ValidationFailure(
            "La arista referencia nodos que no existen en este tablero"
        )

    nodes_map = {n.id: n for n in board_nodes}
    source_node = nodes_map.get(payload.from_.nodeId)
    target_node = nodes_map.get(payload.to.nodeId)

    if source_node is not None and source_node.ports:
        source_port_ids = {p["id"] for p in source_node.ports
                           } if isinstance(source_node.ports, list) else set()
        if payload.from_.portId not in source_port_ids:
            raise ValidationFailure(
                f"Puerto origen '{payload.from_.portId}' no existe en el nodo '{payload.from_.nodeId}'"
            )

    if target_node is not None and target_node.ports:
        target_port_ids = {p["id"] for p in target_node.ports
                           } if isinstance(target_node.ports, list) else set()
        if payload.to.portId not in target_port_ids:
            raise ValidationFailure(
                f"Puerto destino '{payload.to.portId}' no existe en el nodo '{payload.to.nodeId}'"
            )


def create_edge(
    db: Session, user_id: str, board_id: str,
    payload: EdgeSchema, expected_version: int,
    board: models.Board | None = None,
) -> EdgeSchema:
    """Crea una arista en un board, verificando ownership, nodos, puertos y versión.

    Valida que ambos nodos existan en el board, que los puertos referenciados
    existan dentro de cada nodo y que el tablero pertenezca al usuario.

    Si *board* se pasa precargado, evita una consulta adicional.
    """
    board = board or get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, expected_version)
    try:
        _validate_edge_endpoints(board.nodes, payload)
        edge = _build_edge_model(board.id, payload)
        db.add(edge)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(edge)
    return edge_to_schema(edge)


def create_edges_batch(
    db: Session,
    user_id: str,
    board_id: str,
    payloads: list[EdgeSchema],
    expected_version: int,
    board: models.Board | None = None,
) -> dict:
    """Crea múltiples edges en un mismo board en una única transacción.

    Precarga los nodos del board y valida todos los endpoints antes
    de persistir.  Cualquier fallo revierte completamente.

    Devuelve un diccionario con:
    - ``edges``: lista de ``EdgeSchema`` (mismo orden que los payloads)
    - ``client_map``: ``dict[int, str]`` mapeando índice a ID real
    """
    board = board or get_owned_board(db, user_id, board_id)
    increment_board_version(db, board_id, expected_version)

    # Precargar todos los nodos del board (una sola consulta)
    board_nodes = list(board.nodes) if board.nodes else board.nodes

    # Validar todos los endpoints antes de persistir
    for p in payloads:
        _validate_edge_endpoints(board_nodes, p)

    try:
        edges: list[models.Edge] = []
        for p in payloads:
            edge = _build_edge_model(board.id, p)
            db.add(edge)
            edges.append(edge)
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        raise

    schemas_list: list[EdgeSchema] = []
    for e in edges:
        db.refresh(e)
        schemas_list.append(edge_to_schema(e))
    return {
        "edges": schemas_list,
        "client_map": {i: e.id for i, e in enumerate(edges)},
    }


def update_edge(
    db: Session, user_id: str, edge_id: str,
    payload: EdgeUpdate, expected_version: int,
    edge: models.Edge | None = None,
    board: models.Board | None = None,
) -> EdgeSchema:
    """Actualiza parcialmente una arista verificando ownership y versión.

    Si *edge* o *board* se pasan precargados, evita consultas adicionales.
    """
    edge = edge or get_owned_edge(db, user_id, edge_id)
    board_id = board.id if board is not None else edge.board_id
    increment_board_version(db, board_id, expected_version)
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
