"""Configuración de la base de datos (SQLite + SQLAlchemy 2.x)."""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def get_database_url() -> str:
    """Construye la URL de conexión.

    Orden de precedencia:
      1. DATA_PATH (variable canónica de la Suite) — ruta absoluta
      2. NODEBOARD_DB (override legacy, desarrollo local)
      3. Default relativo ``sqlite:///./nodeboard.db``
    """
    data_path = os.getenv("DATA_PATH")
    if data_path:
        return f"sqlite:///{Path(data_path) / 'nodeboard.db'}"
    return os.getenv("NODEBOARD_DB", "sqlite:///./nodeboard.db")


DATABASE_URL = get_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # necesario solo para SQLite
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependencia de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
