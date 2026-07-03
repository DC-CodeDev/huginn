"""API REST del nodeboard.

Endpoints:
  GET    /api/boards                   -> lista de tableros (resumen)
  POST   /api/boards                   -> crear tablero
  GET    /api/boards/{board_id}        -> estado completo (nodes + edges)
  PATCH  /api/boards/{board_id}        -> renombrar tablero
  PUT    /api/boards/{board_id}/state  -> guardar TODO el estado (autosave)
  DELETE /api/boards/{board_id}        -> eliminar tablero

  POST   /api/boards/{board_id}/nodes  -> crear nodo
  PATCH  /api/nodes/{node_id}          -> actualizar nodo (parcial)
  DELETE /api/nodes/{node_id}          -> eliminar nodo (+ sus aristas)

  POST   /api/boards/{board_id}/edges  -> crear arista
  PATCH  /api/edges/{edge_id}          -> actualizar arista (curved)
  DELETE /api/edges/{edge_id}          -> eliminar arista

Ejecución:
  uvicorn app.main:app --reload --port 8000
"""
import uuid

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import event, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db

# SQLite no aplica ON DELETE CASCADE si no se activan las foreign keys
@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Nodeboard API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ helpers
def _uid() -> str:
    return uuid.uuid4().hex


def _get_board(db: Session, board_id: str) -> models.Board:
    board = db.get(models.Board, board_id)
    if not board:
        raise HTTPException(404, "Tablero no encontrado")
    return board


def _node_to_schema(n: models.Node) -> schemas.NodeSchema:
    return schemas.NodeSchema.model_validate(n)


def _edge_to_schema(e: models.Edge) -> schemas.EdgeSchema:
    return schemas.EdgeSchema(
        id=e.id,
        **{"from": {"nodeId": e.from_node, "portId": e.from_port}},
        to={"nodeId": e.to_node, "portId": e.to_port},
        curved=e.curved,
    )


def _board_state(board: models.Board) -> schemas.BoardState:
    return schemas.BoardState(
        id=board.id,
        name=board.name,
        updated_at=board.updated_at,
        nodes=[_node_to_schema(n) for n in board.nodes],
        edges=[_edge_to_schema(e) for e in board.edges],
    )


# ------------------------------------------------------------------ boards
@app.get("/api/boards", response_model=list[schemas.BoardSummary])
def list_boards(db: Session = Depends(get_db)):
    boards = db.scalars(select(models.Board).order_by(models.Board.updated_at.desc())).all()
    out = []
    for b in boards:
        s = schemas.BoardSummary.model_validate(b)
        s.node_count = db.scalar(
            select(func.count()).select_from(models.Node).where(models.Node.board_id == b.id)
        )
        s.edge_count = db.scalar(
            select(func.count()).select_from(models.Edge).where(models.Edge.board_id == b.id)
        )
        out.append(s)
    return out


@app.post("/api/boards", response_model=schemas.BoardState, status_code=201)
def create_board(payload: schemas.BoardCreate, db: Session = Depends(get_db)):
    board = models.Board(id=_uid(), name=payload.name)
    db.add(board)
    db.commit()
    db.refresh(board)
    return _board_state(board)


@app.get("/api/boards/{board_id}", response_model=schemas.BoardState)
def get_board(board_id: str, db: Session = Depends(get_db)):
    return _board_state(_get_board(db, board_id))


@app.patch("/api/boards/{board_id}", response_model=schemas.BoardState)
def rename_board(board_id: str, payload: schemas.BoardRename, db: Session = Depends(get_db)):
    board = _get_board(db, board_id)
    board.name = payload.name
    db.commit()
    db.refresh(board)
    return _board_state(board)


@app.delete("/api/boards/{board_id}", status_code=204)
def delete_board(board_id: str, db: Session = Depends(get_db)):
    db.delete(_get_board(db, board_id))
    db.commit()


@app.put("/api/boards/{board_id}/state", response_model=schemas.BoardState)
def save_board_state(board_id: str, payload: schemas.BoardStateSave, db: Session = Depends(get_db)):
    """Reemplaza nodos y aristas del tablero con el estado enviado.

    Pensado para el autosave del canvas: el frontend manda todo el estado
    (con debounce) y la API lo persiste de forma atómica.
    """
    board = _get_board(db, board_id)
    if payload.name is not None:
        board.name = payload.name

    # Reemplazo total: borrar lo existente y recrear
    for n in list(board.nodes):
        db.delete(n)
    for e in list(board.edges):
        db.delete(e)
    db.flush()

    for n in payload.nodes:
        db.add(models.Node(
            id=n.id or _uid(),
            board_id=board.id,
            type=n.type, x=n.x, y=n.y, w=n.w, title=n.title,
            ports=n.ports, blocks=n.blocks, stages=n.stages,
        ))
    for e in payload.edges:
        db.add(models.Edge(
            id=e.id or _uid(),
            board_id=board.id,
            from_node=e.from_.nodeId, from_port=e.from_.portId,
            to_node=e.to.nodeId, to_port=e.to.portId,
            curved=e.curved,
        ))

    board.updated_at = models._now()
    db.commit()
    db.refresh(board)
    return _board_state(board)


# ------------------------------------------------------------------ nodos
@app.post("/api/boards/{board_id}/nodes", response_model=schemas.NodeSchema, status_code=201)
def create_node(board_id: str, payload: schemas.NodeSchema, db: Session = Depends(get_db)):
    board = _get_board(db, board_id)
    node = models.Node(
        id=payload.id or _uid(),
        board_id=board.id,
        type=payload.type, x=payload.x, y=payload.y, w=payload.w, title=payload.title,
        ports=payload.ports, blocks=payload.blocks, stages=payload.stages,
    )
    db.add(node)
    board.updated_at = models._now()
    db.commit()
    db.refresh(node)
    return _node_to_schema(node)


@app.patch("/api/nodes/{node_id}", response_model=schemas.NodeSchema)
def update_node(node_id: str, payload: schemas.NodeUpdate, db: Session = Depends(get_db)):
    node = db.get(models.Node, node_id)
    if not node:
        raise HTTPException(404, "Nodo no encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(node, field, value)
    node.board.updated_at = models._now()
    db.commit()
    db.refresh(node)
    return _node_to_schema(node)


@app.delete("/api/nodes/{node_id}", status_code=204)
def delete_node(node_id: str, db: Session = Depends(get_db)):
    node = db.get(models.Node, node_id)
    if not node:
        raise HTTPException(404, "Nodo no encontrado")
    # Eliminar también las aristas conectadas a este nodo
    edges = db.scalars(
        select(models.Edge).where(
            models.Edge.board_id == node.board_id,
            or_(models.Edge.from_node == node_id, models.Edge.to_node == node_id),
        )
    ).all()
    for e in edges:
        db.delete(e)
    node.board.updated_at = models._now()
    db.delete(node)
    db.commit()


# ------------------------------------------------------------------ aristas
@app.post("/api/boards/{board_id}/edges", response_model=schemas.EdgeSchema, status_code=201)
def create_edge(board_id: str, payload: schemas.EdgeSchema, db: Session = Depends(get_db)):
    board = _get_board(db, board_id)

    node_ids = {n.id for n in board.nodes}
    if payload.from_.nodeId not in node_ids or payload.to.nodeId not in node_ids:
        raise HTTPException(422, "La arista referencia nodos que no existen en este tablero")

    edge = models.Edge(
        id=payload.id or _uid(),
        board_id=board.id,
        from_node=payload.from_.nodeId, from_port=payload.from_.portId,
        to_node=payload.to.nodeId, to_port=payload.to.portId,
        curved=payload.curved,
    )
    db.add(edge)
    board.updated_at = models._now()
    db.commit()
    db.refresh(edge)
    return _edge_to_schema(edge)


@app.patch("/api/edges/{edge_id}", response_model=schemas.EdgeSchema)
def update_edge(edge_id: str, payload: schemas.EdgeUpdate, db: Session = Depends(get_db)):
    edge = db.get(models.Edge, edge_id)
    if not edge:
        raise HTTPException(404, "Arista no encontrada")
    if payload.curved is not None:
        edge.curved = payload.curved
    edge.board.updated_at = models._now()
    db.commit()
    db.refresh(edge)
    return _edge_to_schema(edge)


@app.delete("/api/edges/{edge_id}", status_code=204)
def delete_edge(edge_id: str, db: Session = Depends(get_db)):
    edge = db.get(models.Edge, edge_id)
    if not edge:
        raise HTTPException(404, "Arista no encontrada")
    edge.board.updated_at = models._now()
    db.delete(edge)
    db.commit()


@app.get("/api/health")
def health():
    return {"status": "ok"}
