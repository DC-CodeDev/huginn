"""Autenticación Bearer MCP — reutilizable y sin dependencia de HTTP.

Flujo:
  extract_bearer_token() → authenticate_mcp_token() → MCPContext

Todas las funciones de dominio son independientes de FastAPI,
FastMCP y tool decorators.
"""
from __future__ import annotations
import hashlib
import hmac
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..services.authorization import get_owned_board, get_owned_studio
from .errors import (
    ConstraintViolation,
    ExpiredMCPToken,
    InsufficientScope,
    InvalidBearerToken,
    MissingBearerToken,
    RevokedMCPToken,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# constantes
# ------------------------------------------------------------------

_TOKEN_PREFIX = "huginn_mcp_"
_MAX_HEADER_LENGTH = 1024
_MAX_TOKEN_LENGTH = 512

# Intervalo mínimo entre escrituras de last_used_at.
MCP_LAST_USED_WRITE_INTERVAL = timedelta(minutes=5)


# ------------------------------------------------------------------
# reloj inyectable (para tests)
# ------------------------------------------------------------------


def _now() -> datetime:
    """Devuelve la hora actual como datetime NAIVE en UTC.

    Convención del proyecto: todos los datetimes son naive pero
    representan siempre UTC.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------
# parsing del header Authorization
# ------------------------------------------------------------------


def extract_bearer_token(authorization: str | None) -> str:
    """Extrae y valida un token Bearer del header Authorization.

    Acepta exclusivamente:
        Authorization: Bearer <token>

    Reglas
    ------
    - header ausente → MissingBearerToken
    - esquema diferente a Bearer (case-insensitive) → InvalidBearerToken
    - Bearer sin valor → InvalidBearerToken
    - token debe comenzar con ``huginn_mcp_`` → InvalidBearerToken
    - header o token excesivamente largo → InvalidBearerToken
    - espacios internos en el token → InvalidBearerToken
    - componentes extra después del token → InvalidBearerToken

    Parameters
    ----------
    authorization : str | None
        Valor completo del header ``Authorization``.

    Returns
    -------
    str
        Token extraído (sin espacios externos).

    Raises
    ------
    MissingBearerToken
        Si el header está ausente.
    InvalidBearerToken
        Si el formato o el token no son válidos.
    """
    if not authorization:
        raise MissingBearerToken("Header Authorization ausente.")

    if len(authorization) > _MAX_HEADER_LENGTH:
        raise InvalidBearerToken("Header Authorization demasiado largo.")

    # Normalizar espacios externos
    stripped = authorization.strip()

    # Separar esquema y valor (solo el primer espacio cuenta)
    parts = stripped.split(" ", 1)

    if len(parts) != 2:
        raise InvalidBearerToken("Formato de autorización inválido.")

    scheme, raw_value = parts[0], parts[1]

    if scheme.lower() != "bearer":
        raise InvalidBearerToken("Esquema de autorización inválido.")

    # Normalizar espacios alrededor del token
    token = raw_value.strip()

    if not token:
        raise InvalidBearerToken("Token Bearer vacío.")

    # Si después de strip hay espacios internos, el split original creó
    # más de 2 partes o el token contiene espacios
    if len(token.split()) > 1:
        raise InvalidBearerToken("Token Bearer con formato inválido.")

    if len(token) > _MAX_TOKEN_LENGTH:
        raise InvalidBearerToken("Token Bearer demasiado largo.")

    if not token.startswith(_TOKEN_PREFIX):
        raise InvalidBearerToken("Prefijo de token inválido.")

    return token


# ------------------------------------------------------------------
# autenticación por hash
# ------------------------------------------------------------------


def authenticate_mcp_token(
    db: Session,
    raw_token: str,
    *,
    update_last_used: bool = True,
) -> MCPContext:
    """Autentica un token MCP y devuelve su contexto.

    Algoritmo
    ---------
    1. Verifica formato básico del token.
    2. Calcula SHA-256 del token completo.
    3. Busca el token por hash en la base de datos.
    4. Rechaza si no existe, está revocado o expirado.
    5. Verifica que el usuario propietario exista.
    6. Actualiza ``last_used_at`` si corresponde.
    7. Construye y devuelve ``MCPContext``.

    Parameters
    ----------
    db : Session
        Sesión de SQLAlchemy.
    raw_token : str
        Token completo extraído del header.
    update_last_used : bool
        Si es True, actualiza ``last_used_at`` bajo las reglas
        del intervalo mínimo.

    Returns
    -------
    MCPContext
        Contexto inmutable sin token completo ni hash.

    Raises
    ------
    InvalidBearerToken
        Si el formato del token es inválido.
    MCPAuthenticationError
        Si el token no existe, está revocado o expirado,
        o el usuario propietario no existe.
    """
    # 1. Validar formato básico
    if not raw_token or not isinstance(raw_token, str):
        raise InvalidBearerToken("Token inválido.")

    if not raw_token.startswith(_TOKEN_PREFIX):
        raise InvalidBearerToken("Prefijo de token inválido.")

    if len(raw_token) > _MAX_TOKEN_LENGTH:
        raise InvalidBearerToken("Token demasiado largo.")

    # 2. Calcular hash
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # 3. Buscar por hash
    token_record = (
        db.execute(
            select(models.MCPToken).where(models.MCPToken.token_hash == token_hash)
        )
        .scalars()
        .first()
    )

    if not token_record:
        logger.warning("MCP auth failed: token_hash not found")
        raise InvalidBearerToken("Credenciales MCP inválidas.")

    # 4. Validar revocación
    if token_record.revoked_at is not None:
        logger.warning("MCP auth failed: token %s is revoked", token_record.id)
        raise RevokedMCPToken("Credenciales MCP inválidas.")

    # 5. Validar expiración
    now = _now()
    if token_record.expires_at is not None and token_record.expires_at <= now:
        logger.warning("MCP auth failed: token %s is expired", token_record.id)
        raise ExpiredMCPToken("Credenciales MCP inválidas.")

    # 6. Verificar usuario propietario
    user = db.get(models.User, token_record.user_id)
    if user is None:
        logger.warning(
            "MCP auth failed: token %s owner user %s not found",
            token_record.id,
            token_record.user_id,
        )
        raise InvalidBearerToken("Credenciales MCP inválidas.")

    # 7. Extraer datos del ORM antes de cualquier commit
    #    (el commit de last_used_at expiraría los objetos y el lazy-load
    #     fallaría con SQLite :memory: en tests).
    scopes_set = (
        frozenset(token_record.scopes) if token_record.scopes else frozenset()
    )
    constraints = (
        dict(token_record.constraints) if token_record.constraints else None
    )
    ctx_user_id = token_record.user_id
    ctx_token_id = token_record.id
    ctx_prefix = token_record.token_prefix
    ctx_expires_at = token_record.expires_at

    # 8. Actualizar last_used_at (controlado) — después de extraer datos
    if update_last_used:
        _update_last_used_if_needed(db, token_record, now)

    # 9. Construir contexto
    # Importación perezosa para evitar ciclo: auth -> context -> auth
    from .context import MCPContext  # fmt: skip

    return MCPContext(
        user_id=ctx_user_id,
        token_id=ctx_token_id,
        scopes=scopes_set,
        constraints=constraints,
        token_prefix=ctx_prefix,
        expires_at=ctx_expires_at,
    )


# ------------------------------------------------------------------
# actualización controlada de last_used_at
# ------------------------------------------------------------------


def _update_last_used_if_needed(
    db: Session,
    token_record: models.MCPToken,
    now: datetime,
) -> None:
    """Actualiza ``last_used_at`` solo si es necesario.

    Escribe cuando:
    - ``last_used_at`` es None (primer uso)
    - han pasado al menos ``MCP_LAST_USED_WRITE_INTERVAL`` desde la última escritura

    No escribe si:
    - el token está revocado
    - el token expiró
    - ``now`` es anterior al último uso (reloj retrocedido)
    """
    last = token_record.last_used_at

    needs_write = False
    if last is None:
        needs_write = True
    elif last < now and (now - last) >= MCP_LAST_USED_WRITE_INTERVAL:
        needs_write = True

    if not needs_write:
        return

    token_record.last_used_at = now
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to update last_used_at for token %s", token_record.id)
        # No relanzamos — la autenticación ya es exitosa,
        # el fallo de escritura no debe bloquear la operación.


# ------------------------------------------------------------------
# scope checking
# ------------------------------------------------------------------


def require_scope(
    context: MCPContext,
    required_scope: str,
) -> None:
    """Verifica que el contexto tenga el scope exacto requerido.

    Reglas
    ------
    - Solo el scope exacto es aceptado (sin jerarquías).
    - No se aceptan comodines (``*``).
    - No modifica el contexto.

    Raises
    ------
    InsufficientScope
        Si el scope requerido no está presente.
    """
    if required_scope not in context.scopes:
        raise InsufficientScope(
            f"Scope '{required_scope}' requerido pero no está presente."
        )


def require_all_scopes(
    context: MCPContext,
    required_scopes: Iterable[str],
) -> None:
    """Verifica que el contexto tenga todos los scopes requeridos.

    Raises
    ------
    InsufficientScope
        Si falta al menos uno de los scopes requeridos.
    """
    missing = [s for s in required_scopes if s not in context.scopes]
    if missing:
        sorted_missing = ", ".join(sorted(missing))
        raise InsufficientScope(
            f"Scopes requeridos ausentes: {sorted_missing}"
        )


# ------------------------------------------------------------------
# enforcement de constraints
# ------------------------------------------------------------------


def enforce_studio_constraint(
    context: MCPContext,
    studio_id: str,
) -> None:
    """Verifica que el contexto permita acceder al studio indicado.

    Reglas
    ------
    - Si ``context.constraints`` es None → sin restricción adicional.
    - Si ``context.constraints`` tiene ``studio_ids`` → el studio debe estar en la lista.
    - Lista vacía de studio_ids → ningún studio permitido.
    - Si la clave ``studio_ids`` no existe en constraints → sin restricción por studio.

    Raises
    ------
    ConstraintViolation
        Si el contexto no permite acceder al studio.
    """
    constraints = context.constraints
    if constraints is None:
        return

    if "studio_ids" not in constraints:
        return

    allowed = constraints["studio_ids"]
    if not allowed:
        raise ConstraintViolation(
            "El token no tiene acceso a ningún studio."
        )

    if studio_id not in allowed:
        raise ConstraintViolation(
            "El token no tiene acceso al studio solicitado."
        )


def enforce_board_constraint(
    db: Session,
    context: MCPContext,
    board_id: str,
) -> None:
    """Verifica que el contexto permita acceder al board indicado.

    Combina restricciones de ``board_ids`` y ``studio_ids``.
    Siempre verifica ownership del board.

    Reglas
    ------
    1. Ownership: el board debe pertenecer al usuario del token.
    2. Si ``context.constraints`` es None → sin restricción adicional.
    3. Si existe ``studio_ids``, el studio del board debe estar permitido.
    4. Si existe ``board_ids``, el board debe estar en la lista.
    5. Lista vacía → ningún recurso permitido en esa dimensión.

    Raises
    ------
    ConstraintViolation
        Si el contexto no permite acceder al board.
    """
    # 1. Ownership primero: recurso ajeno se rechaza indistintamente
    try:
        board = get_owned_board(db, context.user_id, board_id)
    except Exception:
        raise ConstraintViolation(
            "El token no tiene acceso al board solicitado."
        )

    enforce_board_constraint_for_board(context, board)


def enforce_board_constraint_for_board(
    context: MCPContext,
    board: models.Board,
) -> None:
    """Verifica constraints MCP sobre un board ya cargado.

    Reutiliza exactamente las mismas reglas de ``enforce_board_constraint``
    pero evita una segunda consulta cuando el board ya fue resuelto por la
    capa llamadora.
    """

    # 2. Constraints adicionales
    constraints = context.constraints
    if constraints is None:
        return

    has_studio_ids = "studio_ids" in constraints
    has_board_ids = "board_ids" in constraints

    # Si no hay ninguna constraint, no restringir más
    if not has_studio_ids and not has_board_ids:
        return

    # Verificar studio_ids
    if has_studio_ids:
        allowed_studios = constraints["studio_ids"]
        if not allowed_studios:
            raise ConstraintViolation(
                "El token no tiene acceso a ningún studio."
            )
        if board.studio_id not in allowed_studios:
            raise ConstraintViolation(
                "El token no tiene acceso al studio del board solicitado."
            )

    # Verificar board_ids
    if has_board_ids:
        allowed_boards = constraints["board_ids"]
        if not allowed_boards:
            raise ConstraintViolation(
                "El token no tiene acceso a ningún board."
            )
        if board.id not in allowed_boards:
            raise ConstraintViolation(
                "El token no tiene acceso al board solicitado."
            )
