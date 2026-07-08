"""Contexto MCP reutilizable.

``MCPContext`` es un dataclass inmutable que representa un token
autenticado.  No contiene el token completo, el hash ni el modelo ORM.
Es serializable e inspeccionable en tests.

``mcp_context_var`` es un ``ContextVar`` que transporta el contexto
de la request HTTP a las tools MCP sin usar estado global mutable.
``get_context()`` es la función helper para recuperarlo desde cualquier
tool o middleware.

Dependencia FastAPI ``get_mcp_context`` para usar en rutas que acepten
autenticación Bearer.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db as _get_db
from .auth import authenticate_mcp_token, extract_bearer_token
from .errors import (
    ExpiredMCPToken,
    InvalidBearerToken,
    MCPAuthenticationError,
    MissingBearerToken,
    RevokedMCPToken,
)

# ContextVar para propagar el MCPContext desde el middleware ASGI
# hasta las tools sin exponer estado global.
mcp_context_var: ContextVar["MCPContext"] = ContextVar("mcp_context")


def get_context() -> "MCPContext":
    """Recupera el ``MCPContext`` de la request HTTP actual.

    Llamada desde cualquier tool MCP para obtener el token autenticado,
    sus scopes y constraints.

    Returns
    -------
    MCPContext
        Contexto de la request actual.

    Raises
    ------
    RuntimeError
        Si no hay contexto disponible (llamada fuera de una request HTTP).
    """
    try:
        return mcp_context_var.get()
    except LookupError:
        raise RuntimeError("No hay contexto MCP disponible en esta operación.")


@dataclass(frozen=True)
class MCPContext:
    """Contexto de autenticación MCP — inmutable y seguro.

    No incluye:
    - token completo
    - token_hash
    - modelo ORM
    - session cookie
    - email del usuario
    """

    user_id: str
    token_id: str
    scopes: frozenset[str]
    constraints: dict[str, list[str]] | None
    token_prefix: str
    expires_at: datetime
    client_name: str | None = None
    request_id: str | None = None

    def __repr__(self) -> str:
        return (
            f"MCPContext(user_id=***, token_id={self.token_id}, "
            f"scopes={sorted(self.scopes)}, constraints=***, "
            f"token_prefix={self.token_prefix}, "
            f"expires_at={self.expires_at.isoformat()})"
        )


def get_mcp_context(
    request: Request,
    db: Session = Depends(_get_db),
) -> MCPContext:
    """FastAPI Depends: extrae y valida un Bearer MCP.

    Convierte errores de autenticación a HTTP 401 genérico.
    No acepta sesión web como alternativa — solo Bearer.
    """
    authorization = request.headers.get("Authorization")
    try:
        raw_token = extract_bearer_token(authorization)
        ctx = authenticate_mcp_token(db, raw_token, update_last_used=True)
    except (MissingBearerToken, InvalidBearerToken):
        raise HTTPException(
            status_code=401,
            detail="Credenciales MCP inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (ExpiredMCPToken, RevokedMCPToken):
        raise HTTPException(
            status_code=401,
            detail="Credenciales MCP inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except MCPAuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="Credenciales MCP inválidas.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return ctx
