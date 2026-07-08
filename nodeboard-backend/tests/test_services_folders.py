"""Tests unitarios del servicio de Folders.

Cubre: creación (propio/ajeno/inexistente), listado (propio/ajeno),
eliminación (propia/ajena/inexistente), SET NULL en boards asociados,
y verificación de que las lecturas no hacen commit.
"""
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, Folder, Studio, User
from app.schemas import FolderCreate
from app.services.errors import ResourceNotFound
from app.services.folders import (
    create_folder,
    delete_folder,
    list_folders,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _user(db, email=None) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email=email or f"{uuid.uuid4().hex}@example.com",
        name="Test",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


def _studio(db, user, name="Studio") -> Studio:
    st = Studio(id=uuid.uuid4().hex[:16], name=name, color="azul", user_id=user.id)
    db.add(st)
    db.commit()
    return st


# ------------------------------------------------------------------
# create_folder
# ------------------------------------------------------------------


def test_create_folder_in_own_studio(db):
    u = _user(db)
    st = _studio(db, u)
    f = create_folder(db, u.id, FolderCreate(name="Mi Carpeta", studio_id=st.id))
    assert f.name == "Mi Carpeta"
    assert f.studio_id == st.id
    assert f.id is not None


def test_create_folder_in_other_studio_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    with pytest.raises(ResourceNotFound):
        create_folder(db, b.id, FolderCreate(name="Hack", studio_id=st.id))


def test_create_folder_in_nonexistent_studio_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        create_folder(db, u.id, FolderCreate(name="F", studio_id="no-such-id"))


# ------------------------------------------------------------------
# list_folders
# ------------------------------------------------------------------


def test_list_folders_returns_studio_folders(db):
    u = _user(db)
    st = _studio(db, u)
    create_folder(db, u.id, FolderCreate(name="A", studio_id=st.id))
    create_folder(db, u.id, FolderCreate(name="B", studio_id=st.id))
    results = list_folders(db, u.id, st.id)
    assert len(results) == 2
    assert {r.name for r in results} == {"A", "B"}


def test_list_folders_other_studio_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    with pytest.raises(ResourceNotFound):
        list_folders(db, b.id, st.id)


# ------------------------------------------------------------------
# delete_folder
# ------------------------------------------------------------------


def test_delete_own_folder(db):
    u = _user(db)
    st = _studio(db, u)
    f = create_folder(db, u.id, FolderCreate(name="A borrar", studio_id=st.id))
    delete_folder(db, u.id, f.id)
    assert list_folders(db, u.id, st.id) == []


def test_delete_other_folder_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    f = create_folder(db, a.id, FolderCreate(name="De A", studio_id=st.id))
    with pytest.raises(ResourceNotFound):
        delete_folder(db, b.id, f.id)
    # Aún existe para A
    assert len(list_folders(db, a.id, st.id)) == 1


def test_delete_nonexistent_folder_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        delete_folder(db, u.id, "no-such-id")


# ------------------------------------------------------------------
# SET NULL en boards asociados
# ------------------------------------------------------------------


def test_delete_folder_sets_board_folder_id_null(db):
    """Al eliminar un folder, los boards que lo referencian quedan con folder_id=NULL."""
    u = _user(db)
    st = _studio(db, u)
    f = create_folder(db, u.id, FolderCreate(name="Carpeta", studio_id=st.id))
    b = Board(id=uuid.uuid4().hex, name="Board", studio_id=st.id, folder_id=f.id)
    db.add(b)
    db.commit()

    delete_folder(db, u.id, f.id)

    db.expire_all()
    loaded = db.get(Board, b.id)
    assert loaded is not None, "El board no debe eliminarse"
    assert loaded.folder_id is None, "folder_id debe ser NULL tras eliminar la carpeta"


# ------------------------------------------------------------------
# sin efectos secundarios en lecturas
# ------------------------------------------------------------------


def test_list_folders_does_not_commit(db):
    u = _user(db)
    st = _studio(db, u)
    create_folder(db, u.id, FolderCreate(name="Original", studio_id=st.id))
    list_folders(db, u.id, st.id)
    db.rollback()
    assert len(list_folders(db, u.id, st.id)) == 1
