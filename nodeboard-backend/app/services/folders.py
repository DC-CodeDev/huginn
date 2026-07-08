"""Servicio de dominio para Folders.

Operaciones: listar, crear y eliminar folders, todas con
verificación de ownership y sin dependencia de FastAPI.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..schemas import FolderCreate
from .authorization import get_owned_folder, get_owned_studio


def list_folders(
    db: Session, user_id: str, studio_id: str
) -> list[models.Folder]:
    """Retorna los folders de un studio, previa verificación de ownership."""
    get_owned_studio(db, user_id, studio_id)
    return list(
        db.scalars(
            select(models.Folder)
            .where(models.Folder.studio_id == studio_id)
            .order_by(models.Folder.name)
        ).all()
    )


def create_folder(
    db: Session, user_id: str, payload: FolderCreate
) -> models.Folder:
    """Crea un folder dentro de un studio, verificando ownership del studio."""
    get_owned_studio(db, user_id, payload.studio_id)
    folder = models.Folder(
        id=uuid.uuid4().hex,
        name=payload.name,
        studio_id=payload.studio_id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(db: Session, user_id: str, folder_id: str) -> None:
    """Elimina un folder verificando que pertenece al usuario.

    Los boards asociados mantienen su folder_id (SET NULL por FK).
    """
    folder = get_owned_folder(db, user_id, folder_id)
    db.delete(folder)
    db.commit()
