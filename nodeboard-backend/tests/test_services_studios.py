"""Tests unitarios del servicio de Studios.

Cubre: creación, listado (propio/ajeno), eliminación (propia/ajena/inexistente),
cascada, y verificación de que las lecturas no hacen commit.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Studio, User
from app.schemas import StudioCreate
from app.services.errors import ResourceNotFound
from app.services.studios import (
    create_studio,
    delete_studio,
    list_studios,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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


# ------------------------------------------------------------------
# create_studio
# ------------------------------------------------------------------


def test_create_studio_for_user(db):
    u = _user(db)
    s = create_studio(db, u.id, StudioCreate(name="Mi Studio", color="azul"))
    assert s.name == "Mi Studio"
    assert s.color == "azul"
    assert s.user_id == u.id
    assert s.id is not None


def test_created_studio_persisted(db):
    u = _user(db)
    s = create_studio(db, u.id, StudioCreate(name="Persist", color="verde"))
    db.expire_all()
    loaded = db.get(Studio, s.id)
    assert loaded is not None
    assert loaded.name == "Persist"
    assert loaded.user_id == u.id


# ------------------------------------------------------------------
# list_studios
# ------------------------------------------------------------------


def test_list_studios_returns_own(db):
    u = _user(db)
    create_studio(db, u.id, StudioCreate(name="A", color="azul"))
    create_studio(db, u.id, StudioCreate(name="B", color="verde"))
    results = list_studios(db, u.id)
    assert len(results) == 2
    assert {r.name for r in results} == {"A", "B"}


def test_list_studios_excludes_others(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    create_studio(db, a.id, StudioCreate(name="Solo A", color="azul"))
    results_b = list_studios(db, b.id)
    assert len(results_b) == 0


def test_list_studios_ordering(db):
    u = _user(db)
    create_studio(db, u.id, StudioCreate(name="Zeta", color="azul"))
    create_studio(db, u.id, StudioCreate(name="Alfa", color="verde"))
    create_studio(db, u.id, StudioCreate(name="Beta", color="dorado"))
    names = [s.name for s in list_studios(db, u.id)]
    assert names == ["Alfa", "Beta", "Zeta"]


# ------------------------------------------------------------------
# delete_studio
# ------------------------------------------------------------------


def test_delete_own_studio(db):
    u = _user(db)
    s = create_studio(db, u.id, StudioCreate(name="A borrar", color="azul"))
    delete_studio(db, u.id, s.id)
    assert list_studios(db, u.id) == []


def test_delete_other_studio_raises_not_found(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    s = create_studio(db, a.id, StudioCreate(name="De A", color="azul"))
    with pytest.raises(ResourceNotFound) as exc:
        delete_studio(db, b.id, s.id)
    assert exc.value.resource_type == "Studio"
    # Aún existe para A
    assert len(list_studios(db, a.id)) == 1


def test_delete_nonexistent_studio_raises_not_found(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        delete_studio(db, u.id, "no-such-id")


# ------------------------------------------------------------------
# cascade
# ------------------------------------------------------------------


def test_delete_studio_cascades_to_folders_and_boards(db):
    """Verifica que eliminar un studio también elimina folders y boards asociados."""
    from app.models import Board, Folder

    u = _user(db)
    s = create_studio(db, u.id, StudioCreate(name="Cascade", color="azul"))

    # Crear folder y board dentro del studio manualmente
    f = Folder(id=uuid.uuid4().hex, name="Carpeta", studio_id=s.id)
    db.add(f)
    db.commit()

    b = Board(id=uuid.uuid4().hex, name="Board", studio_id=s.id, folder_id=f.id)
    db.add(b)
    db.commit()

    delete_studio(db, u.id, s.id)
    assert db.get(Studio, s.id) is None
    assert db.get(Folder, f.id) is None
    assert db.get(Board, b.id) is None


# ------------------------------------------------------------------
# sin efectos secundarios en lecturas
# ------------------------------------------------------------------


def test_list_studios_does_not_commit(db):
    u = _user(db)
    create_studio(db, u.id, StudioCreate(name="Original", color="azul"))
    # La lectura no debería hacer commit de nada
    list_studios(db, u.id)
    db.rollback()
    # rollback no debería afectar — la lectura no hizo commit
    assert len(list_studios(db, u.id)) == 1
