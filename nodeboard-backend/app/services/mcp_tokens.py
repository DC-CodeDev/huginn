"""Servicio de dominio para MCP Tokens.

Operaciones: crear, listar, revocar y eliminar tokens MCP,
todas con verificación de ownership.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from .authorization import get_owned_board, get_owned_studio
from .errors import ResourceNotFound, ValidationFailure

# ------------------------------------------------------------------
# constantes
# ------------------------------------------------------------------

_TOKEN_PREFIX = "huginn_mcp_"
_HASH_ALGO = "sha-256"
_MAX_NAME = 200
_MIN_DAYS = 1
_MAX_DAYS = 365
_DEFAULT_DAYS = 90
_MAX_SCOPES = 20
_MAX_STUDIO_IDS = 100
_MAX_BOARD_IDS = 100

# ------------------------------------------------------------------
# helpers de generación
# ------------------------------------------------------------------


def _generate_token() -> tuple[str, str, str]:
    """Genera un token criptográficamente seguro.

    Returns
    -------
        (token_completo, token_hash, token_prefix)
    """
    secret = secrets.token_urlsafe(32)
    token = f"{_TOKEN_PREFIX}{secret}"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    prefix = f"{_TOKEN_PREFIX}{secret[:6]}"
    return token, token_hash, prefix


# ------------------------------------------------------------------
# validación de constraints
# ------------------------------------------------------------------


def _validate_constraints(
    db: Session,
    user_id: str,
    constraints: schemas.MCPTokenConstraints | None,
) -> dict | None:
    """Valida y normaliza constraints de un token.

    Verifica ownership de studios y boards, y consistencia entre ambas listas.
    Devuelve el dict normalizado (o None si constraints es None).
    """
    if constraints is None:
        return None

    raw = constraints.model_dump(exclude_none=True)

    # studio_ids
    studio_ids = raw.get("studio_ids")
    if studio_ids is not None:
        # deduplicar
        seen_s: set[str] = set()
        deduped_s: list[str] = []
        for sid in studio_ids:
            if not isinstance(sid, str) or not sid.strip():
                raise ValidationFailure("studio_ids debe contener strings no vacíos")
            if sid in seen_s:
                continue
            seen_s.add(sid)
            deduped_s.append(sid)
        if len(deduped_s) > _MAX_STUDIO_IDS:
            raise ValidationFailure(
                f"Máximo {_MAX_STUDIO_IDS} studio_ids por token"
            )
        # verificar ownership (no revelar si es ajeno)
        for sid in deduped_s:
            get_owned_studio(db, user_id, sid)
        raw["studio_ids"] = deduped_s

    # board_ids
    board_ids = raw.get("board_ids")
    if board_ids is not None:
        seen_b: set[str] = set()
        deduped_b: list[str] = []
        for bid in board_ids:
            if not isinstance(bid, str) or not bid.strip():
                raise ValidationFailure("board_ids debe contener strings no vacíos")
            if bid in seen_b:
                continue
            seen_b.add(bid)
            deduped_b.append(bid)
        if len(deduped_b) > _MAX_BOARD_IDS:
            raise ValidationFailure(
                f"Máximo {_MAX_BOARD_IDS} board_ids por token"
            )
        # verificar ownership
        for bid in deduped_b:
            get_owned_board(db, user_id, bid)
        raw["board_ids"] = deduped_b

    # consistencia: cada board debe pertenecer a un studio permitido
    if "studio_ids" in raw and "board_ids" in raw:
        allowed_studios = set(raw["studio_ids"])
        for bid in raw["board_ids"]:
            board = get_owned_board(db, user_id, bid)
            # El board ya fue verificado como propio
            # Solo validamos que su studio_id esté en la lista permitida
            # Consulta el studio_id directamente del board
            board_obj = db.get(models.Board, bid)
            if board_obj and board_obj.studio_id not in allowed_studios:
                raise ValidationFailure(
                    f"El board {bid} no pertenece a un studio de los permitidos"
                )

    return raw if raw else None


# ------------------------------------------------------------------
# helpers de consulta
# ------------------------------------------------------------------


def get_owned_mcp_token(
    db: Session, user_id: str, token_id: str
) -> models.MCPToken:
    """Retorna un MCPToken que pertenece al usuario, o lanza ResourceNotFound."""
    token = (
        db.execute(
            select(models.MCPToken).where(
                models.MCPToken.id == token_id,
                models.MCPToken.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )
    if not token:
        raise ResourceNotFound(
            "MCPToken", token_id, "Token no encontrado"
        )
    return token


# ------------------------------------------------------------------
# funciones del servicio
# ------------------------------------------------------------------


def create_mcp_token(
    db: Session,
    user_id: str,
    payload: schemas.MCPTokenCreate,
) -> schemas.MCPTokenCreated:
    """Crea un token MCP para el usuario.

    Valida nombre, scopes, constraints y expiración.
    Genera el token criptográficamente seguro y persiste solo el hash.
    La respuesta incluye el token completo (única exposición).
    """
    # 1. validar y normalizar nombre
    name = payload.name.strip() if payload.name else ""
    if not name:
        raise ValidationFailure("El nombre del token no puede estar vacío")
    if len(name) > _MAX_NAME:
        raise ValidationFailure(
            f"El nombre del token no puede superar {_MAX_NAME} caracteres"
        )

    # 2. validar y normalizar scopes
    scopes = payload.scopes
    if not scopes:
        raise ValidationFailure("Debe especificar al menos un scope")
    scopes = schemas.normalise_scopes(scopes)

    # 3. validar expiración
    days = payload.expires_in_days
    if days < _MIN_DAYS or days > _MAX_DAYS:
        raise ValidationFailure(
            f"expires_in_days debe estar entre {_MIN_DAYS} y {_MAX_DAYS}"
        )

    # 4. validar constraints
    constraints_dict = _validate_constraints(db, user_id, payload.constraints)

    # 5. generar token
    token, token_hash, prefix = _generate_token()

    # 6. calcular expiración (naive UTC)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now + timedelta(days=days)

    # 7. persistir
    mcp_token = models.MCPToken(
        id=uuid.uuid4().hex,
        user_id=user_id,
        name=name,
        token_prefix=prefix,
        token_hash=token_hash,
        scopes=scopes,
        constraints=constraints_dict,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(mcp_token)
    try:
        db.commit()
        db.refresh(mcp_token)
    except Exception:
        db.rollback()
        raise

    # Reconstruir constraints normalizados para la respuesta
    response_constraints = None
    if constraints_dict:
        response_constraints = schemas.MCPTokenConstraints(
            studio_ids=constraints_dict.get("studio_ids"),
            board_ids=constraints_dict.get("board_ids"),
        )

    return schemas.MCPTokenCreated(
        id=mcp_token.id,
        name=mcp_token.name,
        token=token,
        token_prefix=mcp_token.token_prefix,
        scopes=scopes,
        constraints=response_constraints,
        created_at=mcp_token.created_at,
        expires_at=mcp_token.expires_at,
    )


def list_mcp_tokens(
    db: Session,
    user_id: str,
) -> list[schemas.MCPTokenSummary]:
    """Lista todos los tokens MCP del usuario.

    No expone token_hash ni el token completo.
    Ordena por created_at DESC, luego id DESC.
    No hace commit, no modifica last_used_at.
    """
    tokens = (
        db.execute(
            select(models.MCPToken)
            .where(models.MCPToken.user_id == user_id)
            .order_by(
                models.MCPToken.created_at.desc(),
                models.MCPToken.id.desc(),
            )
        )
        .scalars()
        .all()
    )

    summaries: list[schemas.MCPTokenSummary] = []
    for t in tokens:
        constraints = None
        if t.constraints:
            constraints = schemas.MCPTokenConstraints(**t.constraints)
        summaries.append(
            schemas.MCPTokenSummary(
                id=t.id,
                name=t.name,
                token_prefix=t.token_prefix,
                scopes=list(t.scopes) if t.scopes else [],
                constraints=constraints,
                created_at=t.created_at,
                last_used_at=t.last_used_at,
                expires_at=t.expires_at,
                revoked_at=t.revoked_at,
            )
        )
    return summaries


def revoke_mcp_token(
    db: Session,
    user_id: str,
    token_id: str,
) -> schemas.MCPTokenSummary:
    """Revoca un token MCP.

    Idempotente: si ya está revocado, devuelve su estado actual.
    """
    token = get_owned_mcp_token(db, user_id, token_id)

    if token.revoked_at is None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        token.revoked_at = now
        try:
            db.commit()
            db.refresh(token)
        except Exception:
            db.rollback()
            raise

    constraints = None
    if token.constraints:
        constraints = schemas.MCPTokenConstraints(**token.constraints)

    return schemas.MCPTokenSummary(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        scopes=list(token.scopes) if token.scopes else [],
        constraints=constraints,
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
    )


def delete_mcp_token(
    db: Session,
    user_id: str,
    token_id: str,
) -> None:
    """Elimina físicamente un token MCP.

    Es una operación administrativa — la revocación es el camino normal.
    """
    token = get_owned_mcp_token(db, user_id, token_id)
    try:
        db.delete(token)
        db.commit()
    except Exception:
        db.rollback()
        raise
