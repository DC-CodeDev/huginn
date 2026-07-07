"""Autenticación con Google OAuth.

Flujo:
  1. Frontend redirige al usuario a Google para obtener un authorization code.
  2. Frontend envía el code al backend (POST /api/auth/login).
  3. verify_google_token(code) intercambia el code por tokens y extrae la identidad.
  4. Backend crea/finds el usuario en la tabla users, crea una sesión de 7 días,
     y envía una cookie httpOnly con el id de sesión.

Variables de entorno requeridas:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_CALLBACK_URL
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


class GoogleIdentity:
    """Identidad devuelta por Google tras verificar el token."""
    email: str
    name: str
    avatar_url: str


def verify_google_token(authorization_code: str) -> GoogleIdentity:
    """Intercambia el authorization code por tokens con Google y devuelve la identidad.

    Usa google.oauth2.id_token.verify_oauth2_token para validar el ID token
    directamente, sin necesidad de un cliente HTTP propio — la librería oficial
    de Google maneja el intercambio internamente.

    Lanza ValueError si el code es inválido o el token no corresponde al
    cliente configurado.
    """
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    callback_url = os.environ["GOOGLE_CALLBACK_URL"]

    # La librería google-auth intercambia el code por tokens usando
    # el flujo estándar de OAuth2 (authorization code → access + id token).
    # Necesitamos crear un request de intercambio manualmente.
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import AuthorizedSession

    # Construir la solicitud de intercambio de code por tokens
    token_url = "https://oauth2.googleapis.com/token"
    import requests as std_requests

    response = std_requests.post(
        token_url,
        data={
            "code": authorization_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": callback_url,
            "grant_type": "authorization_code",
        },
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    token_data = response.json()

    # Extraer y verificar el ID token incluido en la respuesta
    raw_id_token = token_data.get("id_token")
    if not raw_id_token:
        raise ValueError("No se recibió id_token de Google")

    info = id_token.verify_oauth2_token(
        raw_id_token,
        google_requests.Request(),
        client_id,
    )

    identity = GoogleIdentity()
    identity.email = info.get("email", "")
    identity.name = info.get("name", "")
    identity.avatar_url = info.get("picture", "")
    return identity


def resolve_user_from_session(db: Session, session_id: str) -> Optional[models.User]:
    """Busca una sesión por ID, valida que no esté expirada, y devuelve el usuario."""
    session = db.get(models.Session, session_id)
    if not session:
        return None
    if session.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        # expires_at es naive UTC (convención del proyecto)
        db.delete(session)
        db.commit()
        return None
    user = db.get(models.User, session.user_id)
    return user


SESSION_DURATION_DAYS = 7


def create_session(db: Session, user: models.User) -> models.Session:
    """Crea una nueva sesión para el usuario con expiración a 7 días."""
    session = models.Session(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=SESSION_DURATION_DAYS),
        # expires_at es naive UTC (convención del proyecto)
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
