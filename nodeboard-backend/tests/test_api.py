import re

import pytest
from pathlib import Path

from app.main import app, health
from app.schemas import BoardStateSave


def test_health_and_routes():
    assert health() == {"status": "ok"}
    paths = {route.path for route in app.routes}
    assert "/api/boards" in paths
    assert "/api/boards/{board_id}/state" in paths


def test_state_contract():
    state = BoardStateSave.model_validate({
        "nodes": [{
            "id": "node-1", "type": "card", "x": 10, "y": 20,
            "w": 280, "title": "Nodo", "ports": [], "blocks": [], "stages": [],
        }],
        "edges": [],
        "expected_version": 1,
    })
    assert state.nodes[0].title == "Nodo"


def test_catch_all_source_ordering():
    """Verifica en el código fuente que el catch-all SPA es lo último.

    Starlette resuelve rutas por orden de registro. Si alguien agrega un
    endpoint @app.* DESPUÉS del catch-all /{full_path:path} en main.py,
    esa ruta quedaría tapada silenciosamente por index.html sin que el
    error sea obvio.

    Este test parsea el archivo fuente buscando decoradores de ruta en
    orden y confirmando que el último es el catch-all. Así funciona
    incluso sin el build de frontend (sin depender de app.routes).

    Si falla: mové el nuevo endpoint a ANTES del bloque comentado
    '# Frontend estático — orden crítico' al final de main.py.
    """
    main_py = Path(__file__).resolve().parent.parent / "app" / "main.py"
    lines = main_py.read_text().splitlines()

    # Recorrer líneas buscando @app.get/post/put/patch/delete("...")
    # y recolectar el path de cada ruta en orden de aparición.
    route_pattern = re.compile(r'@app\.(?:get|post|put|patch|delete|api_route)\("([^"]+)"')

    found_routes: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        m = route_pattern.search(line)
        if m:
            found_routes.append((lineno, m.group(1)))

    assert len(found_routes) > 0, "No se encontraron rutas @app.* en main.py"

    last_path = found_routes[-1][1]
    assert last_path == "/{full_path:path}", (
        f"La última ruta registrada en main.py es '{last_path}' (línea {found_routes[-1][0]}), "
        f"no el catch-all '/{{full_path:path}}'. "
        f"Si agregaste un endpoint, movelo antes del bloque "
        f"'# Frontend estático — orden crítico' al final de main.py."
    )

    # Doble check: ninguna ruta /api/* después del catch-all
    catch_all_idx = None
    for i, (_, p) in enumerate(found_routes):
        if p == "/{full_path:path}":
            catch_all_idx = i
            break

    for i in range(catch_all_idx + 1, len(found_routes)):
        lineno, path = found_routes[i]
        if path.startswith("/api"):
            pytest.fail(
                f"Ruta '{path}' (línea {lineno}) registrada después del catch-all "
                f"en main.py — quedará tapada por index.html sin error visible."
            )


def test_catch_all_ordering_at_runtime():
    """Verifica en app.routes que el catch-all sea la última ruta.

    Solo corre si el build de frontend está presente (static/ existe),
    ya que el catch-all se registra condicionalmente. En entornos sin
    build (desarrollo local) este test se omite con xfail.
    """
    # Buscar el catch-all en app.routes
    catch_all_idx = None
    for i, route in enumerate(app.routes):
        if getattr(route, "path", None) == "/{full_path:path}":
            catch_all_idx = i
            break

    if catch_all_idx is None:
        # El catch-all no está registrado — típicamente porque no hay
        # build de frontend (static/ no existe). Marcar como fail
        # esperado para que el desarrollador sepa que no puede confiar
        # en este test sin el build, pero sin romper la suite.
        pytest.xfail("catch-all no registrado (sin build de frontend)")

    # Verificar que ningún endpoint /api/* quede después
    for route in app.routes[catch_all_idx + 1:]:
        route_path = getattr(route, "path", "")
        if route_path.startswith("/api"):
            pytest.fail(
                f"Se encontró la ruta '{route_path}' registrada después del "
                "catch-all SPA — quedará tapada silenciosamente por index.html. "
                "Registrala antes del bloque de StaticFiles/catch-all al final "
                "de main.py."
            )
