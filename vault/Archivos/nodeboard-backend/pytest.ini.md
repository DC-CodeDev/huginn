**Ruta:** `nodeboard-backend/pytest.ini`

## Responsabilidad
Configuración de pytest del backend. Existe para resolver el `ModuleNotFoundError: No module named 'app'` que aparecía al correr pytest desde la raíz del repo.

## Causa del problema
El paquete `app` vive en `nodeboard-backend/app/`, pero los tests lo importan como `from app.main import ...`. Sin archivo de config, pytest fija el `rootdir` en la raíz del repo (`~/Projects/huginn`) y ese directorio queda en `sys.path`, no `nodeboard-backend/`. Por eso `app` sólo se resolvía si se invocaba pytest desde adentro de `nodeboard-backend/`.

## Solución
Al colocar `pytest.ini` en `nodeboard-backend/`, pytest fija el `rootdir` en ese directorio sin importar desde dónde se lo invoque (siempre que el path de tests apunte ahí). Las claves:
- `pythonpath = .` — agrega `nodeboard-backend/` (el rootdir) a `sys.path`, así `app` se resuelve.
- `testpaths = tests` — al correr `pytest` sin args desde `nodeboard-backend/`, colecta `tests/`.

Verificado: pasan `test_health_and_routes` y `test_state_contract` corriendo desde la raíz del repo (`pytest nodeboard-backend/tests`), desde `nodeboard-backend/` (`pytest`), y vía `npm run test:api`.

## Importado por
- Motor de pytest (auto-descubierto por ubicación del rootdir)
- [[tests/test_api.py.md]] — se apoya en este pythonpath para importar `app`
