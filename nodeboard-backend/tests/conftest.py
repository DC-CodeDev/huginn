"""Infraestructura compartida de tests backend.

Python 3.14 empezó a exponer con mucha más agresividad conexiones SQLite
sin liberar. Muchos tests crean engines efímeros por caso y solo cierran
la Session; este hook rastrea esos engines y fuerza ``dispose()`` al final
de cada test para dejar la suite sin ResourceWarning.
"""

from __future__ import annotations

import pytest
import sqlalchemy
from sqlalchemy.engine import create as sqlalchemy_engine_create

_REAL_CREATE_ENGINE = sqlalchemy.create_engine
_TRACKED_ENGINES = []


def _tracking_create_engine(*args, **kwargs):
    engine = _REAL_CREATE_ENGINE(*args, **kwargs)
    _TRACKED_ENGINES.append(engine)
    return engine


sqlalchemy.create_engine = _tracking_create_engine
sqlalchemy_engine_create.create_engine = _tracking_create_engine


@pytest.fixture(autouse=True)
def _dispose_sqlalchemy_engines():
    start = len(_TRACKED_ENGINES)
    yield
    for engine in reversed(_TRACKED_ENGINES[start:]):
        try:
            engine.dispose()
        except Exception:
            pass
