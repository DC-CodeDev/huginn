"""Servicio de dominio para Studios.

Operaciones: listar, crear y eliminar studios, todas con
verificación de ownership y sin dependencia de FastAPI.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import StudioCreate
from .authorization import get_owned_studio


def list_studios(db: Session, user_id: str) -> list[models.Studio]:
    """Retorna los studios pertenecientes a *user_id*, ordenados por nombre."""
    return list(
        db.scalars(
            select(models.Studio)
            .where(models.Studio.user_id == user_id)
            .order_by(models.Studio.name)
        ).all()
    )


def create_studio(
    db: Session, user_id: str, payload: StudioCreate
) -> models.Studio:
    """Crea un studio para el usuario y lo persiste."""
    studio = models.Studio(
        id=uuid.uuid4().hex,
        name=payload.name,
        color=payload.color,
        user_id=user_id,
    )
    db.add(studio)
    db.commit()
    db.refresh(studio)
    return studio


def delete_studio(db: Session, user_id: str, studio_id: str) -> None:
    """Elimina un studio verificando que pertenece al usuario.

    La eliminación en cascada (folders, boards, nodes, edges) es
    gestionada por las relaciones ORM de SQLAlchemy.
    """
    studio = get_owned_studio(db, user_id, studio_id)
    db.delete(studio)
    db.commit()
