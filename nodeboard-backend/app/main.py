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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

# Cargar variables de entorno desde .env antes de cualquier otra cosa
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from . import auth, models, schemas
from .database import engine as db_engine, get_db
from .mcp.context import get_mcp_context as _get_mcp_context
from .services.authorization import (
    get_owned_board,
)
from .services.board_state import (
    save_board_state as _board_state_service_save,
)
from .services.boards import (
    create_board as _board_service_create,
    delete_board as _board_service_delete,
    get_board as _board_service_get,
    list_boards as _board_service_list_all,
    list_folder_boards as _board_service_list_folder,
    list_studio_boards as _board_service_list_studio,
    rename_board as _board_service_rename,
)
from .services.tags import (
    list_board_tags as _tags_service_list,
)
from .services.errors import ResourceNotFound, ValidationFailure, VersionConflict
from .services.folders import (
    create_folder as _folder_service_create,
    delete_folder as _folder_service_delete,
    list_folders as _folder_service_list,
)
from .services.nodes import (
    create_node as _node_service_create,
    delete_node as _node_service_delete,
    update_node as _node_service_update,
)
from .services.edges import (
    create_edge as _edge_service_create,
    delete_edge as _edge_service_delete,
    update_edge as _edge_service_update,
)
from .services.studios import (
    create_studio as _studio_service_create,
    delete_studio as _studio_service_delete,
    list_studios as _studio_service_list,
)
from .services.mcp_tokens import (
    create_mcp_token as _mcp_token_service_create,
    list_mcp_tokens as _mcp_token_service_list,
    revoke_mcp_token as _mcp_token_service_revoke,
    delete_mcp_token as _mcp_token_service_delete,
)

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

    mcp_enabled = _is_true(os.getenv("MCP_ENABLED"))
    if mcp_enabled:
        from .mcp.server import mcp_lifespan
        async with mcp_lifespan():
            yield
    else:
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


def _or_404(fn, *args, **kwargs):
    """Call a service authorization function and translate ResourceNotFound to HTTP 404."""
    try:
        return fn(*args, **kwargs)
    except ResourceNotFound as e:
        raise HTTPException(404, e.message or "Recurso no encontrado")


def _handle_domain(fn, *args, **kwargs):
    """Call a service function and translate domain errors to HTTP responses."""
    try:
        return fn(*args, **kwargs)
    except ResourceNotFound as e:
        raise HTTPException(404, e.message or "Recurso no encontrado")
    except ValidationFailure as e:
        raise HTTPException(422, e.message or "Error de validación")
    except VersionConflict as e:
        raise HTTPException(
            409,
            detail={
                "code": "VERSION_CONFLICT",
                "message": e.message,
                "board_id": e.board_id,
                "expected_version": e.expected_version,
                "current_version": e.current_version,
            },
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
    return _studio_service_create(db=db, user_id=current_user.id, payload=payload)


@app.get("/api/studios", response_model=list[schemas.StudioOut])
def list_studios(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _studio_service_list(db=db, user_id=current_user.id)


@app.delete("/api/studios/{studio_id}", status_code=204)
def delete_studio(
    studio_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _or_404(_studio_service_delete, db=db, user_id=current_user.id, studio_id=studio_id)


# ------------------------------------------------------------------ folders


@app.post("/api/folders", response_model=schemas.FolderOut, status_code=201)
def create_folder(
    payload: schemas.FolderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _or_404(_folder_service_create, db=db, user_id=current_user.id, payload=payload)


@app.get("/api/studios/{studio_id}/folders", response_model=list[schemas.FolderOut])
def list_folders(
    studio_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _or_404(_folder_service_list, db=db, user_id=current_user.id, studio_id=studio_id)


@app.delete("/api/folders/{folder_id}", status_code=204)
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _or_404(_folder_service_delete, db=db, user_id=current_user.id, folder_id=folder_id)


# ------------------------------------------------------------------ boards


@app.get("/api/boards", response_model=list[schemas.BoardSummary])
def list_boards(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _board_service_list_all(db=db, user_id=current_user.id)


@app.post("/api/boards", response_model=schemas.BoardState, status_code=201)
def create_board(
    payload: schemas.BoardCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _board_service_create,
        db=db,
        user_id=current_user.id,
        payload=payload,
    )


@app.get("/api/studios/{studio_id}/boards", response_model=schemas.StudioBoardsOut)
def list_studio_boards(
    studio_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _or_404(
        _board_service_list_studio,
        db=db,
        user_id=current_user.id,
        studio_id=studio_id,
    )


@app.get("/api/folders/{folder_id}/boards", response_model=list[schemas.BoardSummary])
def list_folder_boards(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _or_404(
        _board_service_list_folder,
        db=db,
        user_id=current_user.id,
        folder_id=folder_id,
    )


@app.get("/api/boards/{board_id}", response_model=schemas.BoardState)
def get_board(
    board_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _or_404(
        _board_service_get,
        db=db,
        user_id=current_user.id,
        board_id=board_id,
    )


@app.get("/api/boards/{board_id}/tags", response_model=list[str])
def board_tags(
    board_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Tags únicos usados por los nodos del tablero, para autocompletar en el editor."""
    return _or_404(
        _tags_service_list,
        db=db,
        user_id=current_user.id,
        board_id=board_id,
    )


@app.patch("/api/boards/{board_id}", response_model=schemas.BoardState)
def rename_board(
    board_id: str,
    payload: schemas.BoardRename,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _board_service_rename,
        db=db,
        user_id=current_user.id,
        board_id=board_id,
        payload=payload,
    )


@app.delete("/api/boards/{board_id}", status_code=204)
def delete_board(
    board_id: str,
    expected_version: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _handle_domain(
        _board_service_delete,
        db=db,
        user_id=current_user.id,
        board_id=board_id,
        expected_version=expected_version,
    )


@app.put("/api/boards/{board_id}/state", response_model=schemas.BoardState)
def save_board_state(
    board_id: str,
    payload: schemas.BoardStateSave,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Reemplaza nodos y aristas del tablero con el estado enviado.

    Pensado para el autosave del canvas: el frontend manda todo el estado
    (con debounce) y la API lo persiste de forma atómica con optimistic locking.
    """
    return _handle_domain(
        _board_state_service_save,
        db=db,
        user_id=current_user.id,
        board_id=board_id,
        payload=payload,
    )


# ------------------------------------------------------------------ nodos


@app.post("/api/boards/{board_id}/nodes", response_model=schemas.NodeSchema, status_code=201)
def create_node(
    board_id: str,
    payload: schemas.NodeCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _node_service_create,
        db=db,
        user_id=current_user.id,
        board_id=board_id,
        payload=payload,
        expected_version=payload.expected_version,
    )


@app.patch("/api/nodes/{node_id}", response_model=schemas.NodeSchema)
def update_node(
    node_id: str,
    payload: schemas.NodeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _node_service_update,
        db=db,
        user_id=current_user.id,
        node_id=node_id,
        payload=payload,
        expected_version=payload.expected_version,
    )


@app.delete("/api/nodes/{node_id}", status_code=204)
def delete_node(
    node_id: str,
    expected_version: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _handle_domain(
        _node_service_delete,
        db=db,
        user_id=current_user.id,
        node_id=node_id,
        expected_version=expected_version,
    )


# ------------------------------------------------------------------ aristas


@app.post("/api/boards/{board_id}/edges", response_model=schemas.EdgeSchema, status_code=201)
def create_edge(
    board_id: str,
    payload: schemas.EdgeCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _edge_service_create,
        db=db,
        user_id=current_user.id,
        board_id=board_id,
        payload=payload,
        expected_version=payload.expected_version,
    )


@app.patch("/api/edges/{edge_id}", response_model=schemas.EdgeSchema)
def update_edge(
    edge_id: str,
    payload: schemas.EdgeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _edge_service_update,
        db=db,
        user_id=current_user.id,
        edge_id=edge_id,
        payload=payload,
        expected_version=payload.expected_version,
    )


@app.delete("/api/edges/{edge_id}", status_code=204)
def delete_edge(
    edge_id: str,
    expected_version: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _handle_domain(
        _edge_service_delete,
        db=db,
        user_id=current_user.id,
        edge_id=edge_id,
        expected_version=expected_version,
    )


# ------------------------------------------------------------------ mcp tokens


@app.post(
    "/api/integrations/mcp/tokens",
    response_model=schemas.MCPTokenCreated,
    status_code=201,
)
def create_mcp_token(
    payload: schemas.MCPTokenCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _mcp_token_service_create,
        db=db,
        user_id=current_user.id,
        payload=payload,
    )


@app.get(
    "/api/integrations/mcp/tokens",
    response_model=list[schemas.MCPTokenSummary],
)
def list_mcp_tokens(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _mcp_token_service_list(db=db, user_id=current_user.id)


@app.post(
    "/api/integrations/mcp/tokens/{token_id}/revoke",
    response_model=schemas.MCPTokenSummary,
)
def revoke_mcp_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _handle_domain(
        _mcp_token_service_revoke,
        db=db,
        user_id=current_user.id,
        token_id=token_id,
    )


@app.delete(
    "/api/integrations/mcp/tokens/{token_id}",
    status_code=204,
)
def delete_mcp_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _handle_domain(
        _mcp_token_service_delete,
        db=db,
        user_id=current_user.id,
        token_id=token_id,
    )


@app.get(
    "/api/integrations/mcp/auth-check",
    response_model=schemas.MCPAuthCheck,
)
def mcp_auth_check(
    ctx: schemas.MCPAuthCheck = Depends(_get_mcp_context),
):
    """Endpoint temporal de diagnóstico para autenticación Bearer MCP.

    Solo acepta Bearer MCP (no cookie de sesión web).
    Devuelve información mínima y no sensible.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return schemas.MCPAuthCheck(
        authenticated=True,
        token_id=ctx.token_id,
        token_prefix=ctx.token_prefix,
        scopes=sorted(ctx.scopes),
        constraints=None
        if ctx.constraints is None
        else schemas.MCPTokenConstraints(
            studio_ids=ctx.constraints.get("studio_ids"),
            board_ids=ctx.constraints.get("board_ids"),
        ),
        expires_at=ctx.expires_at,
        last_used_at=now,
    )


# ------------------------------------------------------------------ health


@app.api_route("/api/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}


# ------------------------------------------------------------------
# Servidor MCP (solo lectura, Streamable HTTP)
# ------------------------------------------------------------------
# Se monta ANTES del catch-all SPA para que las rutas MCP tengan
# prioridad sobre el frontend estático.  El servidor MCP solo se
# activa cuando MCP_ENABLED=true.

if _is_true(os.getenv("MCP_ENABLED")):
    from starlette.routing import Mount as _Mount

    from .mcp.server import get_mcp_asgi

    app.mount("/mcp", get_mcp_asgi())


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
