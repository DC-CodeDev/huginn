"""Configuración de la base de datos (SQLite + SQLAlchemy 2.x)."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# La BD vive junto al proyecto; se puede sobreescribir con la variable de entorno
DATABASE_URL = os.getenv("NODEBOARD_DB", "sqlite:///./nodeboard.db")

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
