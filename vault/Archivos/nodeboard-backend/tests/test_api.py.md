**Ruta:** `nodeboard-backend/tests/test_api.py`

## Responsabilidad
Tests de humo del backend con pytest: verifican que la app registre sus rutas clave y que el contrato de `BoardStateSave` valide correctamente. Se corren con `npm run test:api` (`pytest nodeboard-backend/tests`).

## Exporta (casos de test)
- `test_health_and_routes` — `health()` responde `{"status": "ok"}` y las rutas `/api/boards` y `/api/boards/{board_id}/state` están registradas en `app.routes`
- `test_state_contract` — `BoardStateSave.model_validate(...)` con un nodo card parsea y conserva `title`

## Importa
- [[../../../Archivos/nodeboard-backend/app/main.py.md]] — `app`, `health`
- [[../../../Archivos/nodeboard-backend/app/schemas.py.md]] — `BoardStateSave`

## Importado por
- (ninguno) — suite de tests, no se importa
