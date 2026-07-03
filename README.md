# Huginn Nodeboard

Canvas de nodos construido con Vite, React y TypeScript, con persistencia en FastAPI, SQLAlchemy y SQLite.

## Arranque

```bash
npm install
python -m venv nodeboard-backend/.venv
nodeboard-backend/.venv/bin/pip install -r nodeboard-backend/requirements.txt
npm run dev
```

La aplicación queda en `http://127.0.0.1:5174`; la API en `http://127.0.0.1:8001` y su documentación en `/docs`.

Vite redirige `/api` al backend durante desarrollo. Para usar otra API, definí `VITE_API_URL`.
