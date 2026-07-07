"""API REST del nodeboard.

Endpoints de autenticación:
  POST   /api/auth/login                    -> login con Google OAuth
  POST   /api/auth/logout                   -> cerrar sesión
  GET    /api/auth/me                       -> usuario actual

Endpoints de negocio (requieren autenticación):
  GET    /api/studios                       -> lista de studios del usuario
  POST   /api/studios                       -> crear studio
  DELETE /api/studios/{studio_id}           -> eliminar studio

  POST   /api/folders                       -> crear carpeta
  GET    /api/studios/{studio_id}/folders   -> carpetas de un studio
  DELETE /api/folders/{folder_id}           -> eliminar carpeta

  GET    /api/boards                        -> lista de tableros del usuario
  POST   /api/boards                        -> crear tablero
  GET    /api/studios/{studio_id}/boards    -> tableros de un studio
  GET    /api/folders/{folder_id}/boards    -> tableros de una carpeta
  GET    /api/boards/{board_id}             -> estado completo (nodes + edges)
  GET    /api/boards/{board_id}/tags        -> tags únicos del tablero
  PATCH  /api/boards/{board_id}             -> renombrar tablero
  PUT    /api/boards/{board_id}/state       -> guardar TODO el estado (autosave)
  DELETE /api/boards/{board_id}             -> eliminar tablero

  POST   /api/boards/{board_id}/nodes       -> crear nodo
  PATCH  /api/nodes/{node_id}               -> actualizar nodo (parcial)
  DELETE /api/nodes/{node_id}               -> eliminar nodo (+ sus aristas)

  POST   /api/boards/{board_id}/edges       -> crear arista
  PATCH  /api/edges/{edge_id}               -> actualizar arista
  DELETE /api/edges/{edge_id}               -> eliminar arista

  GET    /api/health                        -> health check (sin auth)

Ejecución:
  uvicorn app.main:app --reload --port 8001
"""
import os
import re
import uuid
import mimetypes

from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config
from alembic import command
from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from sqlalchemy import event, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# Cargar variables de entorno desde .env antes de cualquier otra cosa
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from . import auth, models, schemas
from .database import engine as db_engine, get_db

# SQLite no aplica ON DELETE CASCADE si no se activan las foreign keys
@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass


_ALEMBIC_CFG = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")

_COOKIE_SESSION = "session"
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_HASHED_ASSET_RE = re.compile(r"[-.][A-Za-z0-9_-]{8,}\.")
_PWA_ROOT_NO_CACHE_PATHS = {"/sw.js", "/manifest.webmanifest", "/offline.html"}
_LONG_CACHE_STATIC_PATHS = {
    "/apple-touch-icon.png",
    "/favicon.ico",
}
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
}
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("application/javascript", ".js")


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = Config(_ALEMBIC_CFG)
    command.upgrade(cfg, "head")
    yield


app = FastAPI(title="Nodeboard API", version="1.0.0", lifespan=lifespan)

# CORS: leer orígenes desde variable de entorno (separados por coma),
# con fallback a localhost para desarrollo local
_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# ------------------------------------------------------------------ auth deps


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _environment() -> str:
    return os.getenv("ENVIRONMENT", "development").strip().lower()


def _is_production() -> bool:
    return _environment() == "production"


def _cookie_secure() -> bool:
    override = os.getenv("COOKIE_SECURE")
    if override is not None:
        return _is_true(override)
    return _is_production()


def _session_cookie_options() -> dict[str, object]:
    return {
        "httponly": True,
        "secure": _cookie_secure(),
        "samesite": "lax",
        "path": "/",
        "max_age": auth.SESSION_DURATION_DAYS * 24 * 3600,
    }


def _session_cookie_delete_options() -> dict[str, object]:
    options = _session_cookie_options().copy()
    options.pop("max_age", None)
    return options


def _looks_like_hashed_asset(path: str) -> bool:
    if not path.startswith("/assets/"):
        return False
    return bool(_HASHED_ASSET_RE.search(Path(path).name))


def _looks_like_file_request(full_path: str) -> bool:
    return "." in Path(full_path).name


def _resolve_static_file(full_path: str) -> Path | None:
    if not full_path:
        return None
    candidate = (_STATIC_DIR / full_path).resolve()
    try:
        candidate.relative_to(_STATIC_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _static_response(path: Path) -> Response:
    media_type, _ = mimetypes.guess_type(path.name)
    return Response(
        content=path.read_bytes(),
        media_type=media_type or "application/octet-stream",
    )


def _cache_control_for(path: str, status_code: int, content_type: str) -> str | None:
    if path == "/api/health":
        return "no-store"
    if path.startswith("/api/"):
        return "private, no-store"
    if path in _PWA_ROOT_NO_CACHE_PATHS:
        return "no-cache"
    if path.startswith("/icons/") or path in _LONG_CACHE_STATIC_PATHS:
        return "public, max-age=31536000, immutable"
    if status_code < 400 and _looks_like_hashed_asset(path):
        return "public, max-age=31536000, immutable"
    if content_type == "text/html":
        return "no-cache"
    return None


def _security_headers_for(scheme: str) -> dict[str, str]:
    headers = dict(_SECURITY_HEADERS)
    if _is_production() and scheme == "https":
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


class ResponseHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        scheme = scope.get("scheme", "http")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                cache_control = _cache_control_for(path, message["status"], content_type)
                if cache_control:
                    headers["Cache-Control"] = cache_control
                for header, value in _security_headers_for(scheme).items():
                    headers.setdefault(header, value)
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(ResponseHeadersMiddleware)


def get_current_user(
    db: Session = Depends(get_db),
    session_id: str = Cookie(default=None, alias=_COOKIE_SESSION),
) -> models.User:
    """FastAPI Depends: resuelve el usuario autenticado desde la cookie de sesión.

    Si la cookie no existe, la sesión no existe, o expiró → 401.
    """
    if not session_id:
        raise HTTPException(401, "No autenticado")
    session = db.get(models.Session, session_id)
    if not session:
        raise HTTPException(401, "Sesión inválida")
    from datetime import datetime, timezone
    if session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        # expires_at es naive UTC (convención del proyecto)
        db.delete(session)
        db.commit()
        raise HTTPException(401, "Sesión expirada")
    user = db.get(models.User, session.user_id)
    if not user:
        raise HTTPException(401, "Usuario no encontrado")
    return user


# ------------------------------------------------------------------ helpers


def _uid() -> str:
    return uuid.uuid4().hex


def _get_board(db: Session, board_id: str, user: models.User) -> models.Board:
    """Busca un Board asegurando que pertenece al usuario via Studio.user_id."""
    board = (
        db.execute(
            select(models.Board)
            .join(models.Studio, models.Board.studio_id == models.Studio.id)
            .where(models.Board.id == board_id, models.Studio.user_id == user.id)
        )
        .scalars()
        .first()
    )
    if not board:
        raise HTTPException(404, "Tablero no encontrado")
    return board


def _get_studio(db: Session, studio_id: str, user: models.User) -> models.Studio:
    """Busca un Studio asegurando que pertenece al usuario."""
    studio = (
        db.execute(
            select(models.Studio).where(
                models.Studio.id == studio_id, models.Studio.user_id == user.id
            )
        )
        .scalars()
        .first()
    )
    if not studio:
        raise HTTPException(404, "Studio no encontrado")
    return studio


def _get_folder(db: Session, folder_id: str, user: models.User) -> models.Folder:
    """Busca un Folder asegurando que pertenece al usuario via Studio.user_id."""
    folder = (
        db.execute(
            select(models.Folder)
            .join(models.Studio, models.Folder.studio_id == models.Studio.id)
            .where(models.Folder.id == folder_id, models.Studio.user_id == user.id)
        )
        .scalars()
        .first()
    )
    if not folder:
        raise HTTPException(404, "Carpeta no encontrada")
    return folder


def _get_owned_node(db: Session, node_id: str, user: models.User) -> models.Node:
    """Busca un Node asegurando que pertenece al usuario via cadena de FKs."""
    node = (
        db.execute(
            select(models.Node)
            .join(models.Board, models.Node.board_id == models.Board.id)
            .join(models.Studio, models.Board.studio_id == models.Studio.id)
            .where(models.Node.id == node_id, models.Studio.user_id == user.id)
        )
        .scalars()
        .first()
    )
    if not node:
        raise HTTPException(404, "Nodo no encontrado")
    return node


def _get_owned_edge(db: Session, edge_id: str, user: models.User) -> models.Edge:
    """Busca un Edge asegurando que pertenece al usuario via cadena de FKs."""
    edge = (
        db.execute(
            select(models.Edge)
            .join(models.Board, models.Edge.board_id == models.Board.id)
            .join(models.Studio, models.Board.studio_id == models.Studio.id)
            .where(models.Edge.id == edge_id, models.Studio.user_id == user.id)
        )
        .scalars()
        .first()
    )
    if not edge:
        raise HTTPException(404, "Arista no encontrada")
    return edge


def _node_to_schema(n: models.Node) -> schemas.NodeSchema:
    return schemas.NodeSchema.model_validate(n)


def _edge_to_schema(e: models.Edge) -> schemas.EdgeSchema:
    return schemas.EdgeSchema(
        id=e.id,
        **{"from": {"nodeId": e.from_node, "portId": e.from_port}},
        to={"nodeId": e.to_node, "portId": e.to_port},
        curved=e.curved,
        label=e.label,
    )


def _board_state(board: models.Board) -> schemas.BoardState:
    return schemas.BoardState(
        id=board.id,
        name=board.name,
        updated_at=board.updated_at,
        nodes=[_node_to_schema(n) for n in board.nodes],
        edges=[_edge_to_schema(e) for e in board.edges],
    )


# ------------------------------------------------------------------ auth endpoints


@app.post("/api/auth/login")
def login(payload: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Intercambia un code de Google por una sesión (cookie httpOnly, 7 días)."""
    identity = auth.verify_google_token(payload.code)

    # Buscar o crear usuario
    user = db.scalar(
        select(models.User).where(
            models.User.email == identity.email,
            models.User.auth_provider == "google",
        )
    )
    if not user:
        user = models.User(
            email=identity.email,
            name=identity.name,
            avatar_url=identity.avatar_url,
            auth_provider="google",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Actualizar datos que pueden cambiar en Google
        user.name = identity.name
        user.avatar_url = identity.avatar_url
        db.commit()

    session = auth.create_session(db, user)

    response.set_cookie(
        key=_COOKIE_SESSION,
        value=session.id,
        **_session_cookie_options(),
    )
    return schemas.UserOut.model_validate(user)


@app.post("/api/auth/logout")
def logout(
    response: Response,
    db: Session = Depends(get_db),
    session_id: str = Cookie(default=None, alias=_COOKIE_SESSION),
):
    """Elimina la sesión actual y limpia la cookie."""
    if session_id:
        session = db.get(models.Session, session_id)
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(key=_COOKIE_SESSION, **_session_cookie_delete_options())


@app.get("/api/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ------------------------------------------------------------------ studios


@app.post("/api/studios", response_model=schemas.StudioOut, status_code=201)
def create_studio(
    payload: schemas.StudioCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    studio = models.Studio(
        id=_uid(), name=payload.name, color=payload.color, user_id=current_user.id
    )
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


@app.get("/api/studios", response_model=list[schemas.StudioOut])
def list_studios(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return list(
        db.scalars(
            select(models.Studio)
            .where(models.Studio.user_id == current_user.id)
            .order_by(models.Studio.name)
        ).all()
    )


@app.delete("/api/studios/{studio_id}", status_code=204)
def delete_studio(
    studio_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db.delete(_get_studio(db, studio_id, current_user))
    db.commit()


# ------------------------------------------------------------------ folders


@app.post("/api/folders", response_model=schemas.FolderOut, status_code=201)
def create_folder(
    payload: schemas.FolderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_studio(db, payload.studio_id, current_user)
    folder = models.Folder(id=_uid(), name=payload.name, studio_id=payload.studio_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@app.get("/api/studios/{studio_id}/folders", response_model=list[schemas.FolderOut])
def list_folders(
    studio_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_studio(db, studio_id, current_user)
    return list(
        db.scalars(
            select(models.Folder)
            .where(models.Folder.studio_id == studio_id)
            .order_by(models.Folder.name)
        ).all()
    )


@app.delete("/api/folders/{folder_id}", status_code=204)
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db.delete(_get_folder(db, folder_id, current_user))
    db.commit()


# ------------------------------------------------------------------ boards


@app.get("/api/boards", response_model=list[schemas.BoardSummary])
def list_boards(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    boards = db.scalars(
        select(models.Board)
        .join(models.Studio, models.Board.studio_id == models.Studio.id)
        .where(models.Studio.user_id == current_user.id)
        .order_by(models.Board.updated_at.desc())
    ).all()
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
def create_board(
    payload: schemas.BoardCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_studio(db, payload.studio_id, current_user)
    if payload.folder_id:
        folder = _get_folder(db, payload.folder_id, current_user)
        if folder.studio_id != payload.studio_id:
            raise HTTPException(
                422,
                "La carpeta no pertenece al Studio especificado",
            )
    board = models.Board(
        id=_uid(),
        name=payload.name,
        studio_id=payload.studio_id,
        folder_id=payload.folder_id,
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return _board_state(board)


@app.get("/api/studios/{studio_id}/boards", response_model=schemas.StudioBoardsOut)
def list_studio_boards(
    studio_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_studio(db, studio_id, current_user)
    all_boards = db.scalars(
        select(models.Board)
        .where(models.Board.studio_id == studio_id)
        .order_by(models.Board.updated_at.desc())
    ).all()

    root_boards = []
    folder_boards = []
    for b in all_boards:
        s = schemas.BoardSummary.model_validate(b)
        s.node_count = db.scalar(
            select(func.count()).select_from(models.Node).where(models.Node.board_id == b.id)
        )
        s.edge_count = db.scalar(
            select(func.count()).select_from(models.Edge).where(models.Edge.board_id == b.id)
        )
        if b.folder_id is None:
            root_boards.append(s)
        else:
            folder_boards.append(s)
    return schemas.StudioBoardsOut(root_boards=root_boards, folder_boards=folder_boards)


@app.get("/api/folders/{folder_id}/boards", response_model=list[schemas.BoardSummary])
def list_folder_boards(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _get_folder(db, folder_id, current_user)
    boards = db.scalars(
        select(models.Board)
        .where(models.Board.folder_id == folder_id)
        .order_by(models.Board.updated_at.desc())
    ).all()
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


@app.get("/api/boards/{board_id}", response_model=schemas.BoardState)
def get_board(
    board_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _board_state(_get_board(db, board_id, current_user))


@app.get("/api/boards/{board_id}/tags", response_model=list[str])
def board_tags(
    board_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Tags únicos usados por los nodos del tablero, para autocompletar en el editor."""
    board = _get_board(db, board_id, current_user)
    unique: dict[str, None] = {}
    for node in board.nodes:
        for tag in node.tags or []:
            if isinstance(tag, str) and tag and tag not in unique:
                unique[tag] = None
    return sorted(unique, key=str.lower)


@app.patch("/api/boards/{board_id}", response_model=schemas.BoardState)
def rename_board(
    board_id: str,
    payload: schemas.BoardRename,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    board = _get_board(db, board_id, current_user)
    board.name = payload.name
    db.commit()
    db.refresh(board)
    return _board_state(board)


@app.delete("/api/boards/{board_id}", status_code=204)
def delete_board(
    board_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db.delete(_get_board(db, board_id, current_user))
    db.commit()


@app.put("/api/boards/{board_id}/state", response_model=schemas.BoardState)
def save_board_state(
    board_id: str,
    payload: schemas.BoardStateSave,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Reemplaza nodos y aristas del tablero con el estado enviado.

    Pensado para el autosave del canvas: el frontend manda todo el estado
    (con debounce) y la API lo persiste de forma atómica.
    """
    board = _get_board(db, board_id, current_user)
    if payload.name is not None:
        board.name = payload.name

    # Reemplazo total: borrar lo existente y recrear
    for n in list(board.nodes):
        db.delete(n)
    for e in list(board.edges):
        db.delete(e)
    db.flush()

    for n in payload.nodes:
        dumped = n.model_dump()
        db.add(models.Node(
            id=n.id or _uid(),
            board_id=board.id,
            type=n.type, x=n.x, y=n.y, w=n.w, title=n.title,
            ports=dumped["ports"], blocks=dumped["blocks"],
            stages=dumped["stages"], tags=dumped["tags"],
        ))
    for e in payload.edges:
        db.add(models.Edge(
            id=e.id or _uid(),
            board_id=board.id,
            from_node=e.from_.nodeId, from_port=e.from_.portId,
            to_node=e.to.nodeId, to_port=e.to.portId,
            curved=e.curved, label=e.label,
        ))

    board.updated_at = models._now()
    db.commit()
    db.refresh(board)
    return _board_state(board)


# ------------------------------------------------------------------ nodos


@app.post("/api/boards/{board_id}/nodes", response_model=schemas.NodeSchema, status_code=201)
def create_node(
    board_id: str,
    payload: schemas.NodeSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    board = _get_board(db, board_id, current_user)
    dumped = payload.model_dump()
    node = models.Node(
        id=payload.id or _uid(),
        board_id=board.id,
        type=payload.type, x=payload.x, y=payload.y, w=payload.w, title=payload.title,
        ports=dumped["ports"], blocks=dumped["blocks"],
        stages=dumped["stages"], tags=dumped["tags"],
    )
    db.add(node)
    board.updated_at = models._now()
    db.commit()
    db.refresh(node)
    return _node_to_schema(node)


@app.patch("/api/nodes/{node_id}", response_model=schemas.NodeSchema)
def update_node(
    node_id: str,
    payload: schemas.NodeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = _get_owned_node(db, node_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    if "tags" in data and data["tags"] is None:
        data["tags"] = []
    for field, value in data.items():
        setattr(node, field, value)
    node.board.updated_at = models._now()
    db.commit()
    db.refresh(node)
    return _node_to_schema(node)


@app.delete("/api/nodes/{node_id}", status_code=204)
def delete_node(
    node_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    node = _get_owned_node(db, node_id, current_user)
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
def create_edge(
    board_id: str,
    payload: schemas.EdgeSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    board = _get_board(db, board_id, current_user)

    node_ids = {n.id for n in board.nodes}
    if payload.from_.nodeId not in node_ids or payload.to.nodeId not in node_ids:
        raise HTTPException(422, "La arista referencia nodos que no existen en este tablero")

    edge = models.Edge(
        id=payload.id or _uid(),
        board_id=board.id,
        from_node=payload.from_.nodeId, from_port=payload.from_.portId,
        to_node=payload.to.nodeId, to_port=payload.to.portId,
        curved=payload.curved, label=payload.label,
    )
    db.add(edge)
    board.updated_at = models._now()
    db.commit()
    db.refresh(edge)
    return _edge_to_schema(edge)


@app.patch("/api/edges/{edge_id}", response_model=schemas.EdgeSchema)
def update_edge(
    edge_id: str,
    payload: schemas.EdgeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    edge = _get_owned_edge(db, edge_id, current_user)
    if payload.curved is not None:
        edge.curved = payload.curved
    fields = payload.model_dump(exclude_unset=True)
    if "label" in fields:
        edge.label = fields["label"] if fields["label"] is not None else ""
    edge.board.updated_at = models._now()
    db.commit()
    db.refresh(edge)
    return _edge_to_schema(edge)


@app.delete("/api/edges/{edge_id}", status_code=204)
def delete_edge(
    edge_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    edge = _get_owned_edge(db, edge_id, current_user)
    edge.board.updated_at = models._now()
    db.delete(edge)
    db.commit()


# ------------------------------------------------------------------ health


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------
# Frontend estático — orden crítico
# ------------------------------------------------------------------
# Este bloque DEBE estar al final del archivo, después de TODOS los
# endpoints /api/*. Starlette resuelve rutas por orden de registro,
# no por especificidad. Si el catch-all se registrara antes que
# /api/..., las rutas de la API nunca se alcanzarían (el catch-all
# las taparía porque matchea cualquier path).
#
# En desarrollo local este directorio no existe (Vite sirve el
# frontend con su proxy), así que el bloque se saltea.

if _STATIC_DIR.is_dir():
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def _serve_spa(full_path: str):
        # No capturar rutas /api/* que no existen (responder 404 limpio)
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        static_file = _resolve_static_file(full_path)
        if static_file:
            return _static_response(static_file)
        if _looks_like_file_request(full_path):
            raise HTTPException(404, "Not found")
        return _static_response(_STATIC_DIR / "index.html")
