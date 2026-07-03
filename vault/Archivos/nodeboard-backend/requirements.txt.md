**Ruta:** `nodeboard-backend/requirements.txt`

## Responsabilidad
Dependencias Python del backend, instaladas en el venv `nodeboard-backend/.venv`.

## Contenido
- `fastapi>=0.110` — framework de la API
- `uvicorn[standard]>=0.29` — servidor ASGI (`dev:api` lo corre en :8001)
- `sqlalchemy>=2.0` — ORM (estilo `Mapped`/`mapped_column`)
- `pydantic>=2.6` — validación de schemas
- `pytest>=8.0` — tests de backend
- `httpx>=0.27` — cliente HTTP (dependencia de test / TestClient)

## Importado por
- Setup del proyecto (README): `pip install -r nodeboard-backend/requirements.txt`
