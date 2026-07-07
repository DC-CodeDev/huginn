# Resumen de Ruteo HTTP — Backend Huginn (nodeboard-backend)

> Estado: inventario para Etapa 3 (CORS + Dockerfile + frontend estático desde FastAPI).
> No modificar archivos fuente. Generado el 2026-07-07.

---

## 1. Instancia de FastAPI y middlewares

**Archivo:** `nodeboard-backend/app/main.py`

- **Creación de la instancia** — línea 84:

  ```python
  app = FastAPI(title="Nodeboard API", version="1.0.0", lifespan=lifespan)
  ```

- **`lifespan`** — línea 77-81: ejecuta `alembic upgrade head` al arrancar.

- **CORSMiddleware** — líneas 86-92:

  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=[
          "http://localhost:5174",
          "http://127.0.0.1:5174",
          "http://localhost:3000",
      ],
      allow_methods=["*"],
      allow_headers=["*"],
      allow_credentials=True,
  )
  ```

  - **Orígenes hardcodeados.** Solo permite desarrollo local (Vite :5174 y :3000).
  - **No hay variable de entorno** para `allow_origins`. Para Railway habrá que parametrizarlo.

- **No hay otros middlewares registrados.** No hay `TrustedHostMiddleware`, `GZipMiddleware`, `SessionMiddleware`, etc.

---

## 2. Routers (`app.include_router`)

**No existe ningún `app.include_router()` en todo el backend** (el grep no encontró coincidencias).

Todas las rutas están definidas directamente como decoradores `@app.get/post/put/patch/delete` en `main.py`. No hay módulos separados de router (`routers/` o similar).

---

## 3. Rutas sueltas en main.py (sin router)

Lista completa en orden de definición:

| Línea | Método | Ruta | Función | Auth |
|-------|--------|------|---------|------|
| 239 | POST | `/api/auth/login` | `login` | No |
| 279 | POST | `/api/auth/logout` | `logout` | Cookie |
| 294 | GET | `/api/auth/me` | `me` | Sí |
| 302 | POST | `/api/studios` | `create_studio` | Sí |
| 317 | GET | `/api/studios` | `list_studios` | Sí |
| 331 | DELETE | `/api/studios/{studio_id}` | `delete_studio` | Sí |
| 344 | POST | `/api/folders` | `create_folder` | Sí |
| 358 | GET | `/api/studios/{studio_id}/folders` | `list_folders` | Sí |
| 374 | DELETE | `/api/folders/{folder_id}` | `delete_folder` | Sí |
| 387 | GET | `/api/boards` | `list_boards` | Sí |
| 411 | POST | `/api/boards` | `create_board` | Sí |
| 437 | GET | `/api/studios/{studio_id}/boards` | `list_studio_boards` | Sí |
| 467 | GET | `/api/folders/{folder_id}/boards` | `list_folder_boards` | Sí |
| 492 | GET | `/api/boards/{board_id}` | `get_board` | Sí |
| 501 | GET | `/api/boards/{board_id}/tags` | `board_tags` | Sí |
| 517 | PATCH | `/api/boards/{board_id}` | `rename_board` | Sí |
| 531 | DELETE | `/api/boards/{board_id}` | `delete_board` | Sí |
| 541 | PUT | `/api/boards/{board_id}/state` | `save_board_state` | Sí |
| 591 | POST | `/api/boards/{board_id}/nodes` | `create_node` | Sí |
| 614 | PATCH | `/api/nodes/{node_id}` | `update_node` | Sí |
| 633 | DELETE | `/api/nodes/{node_id}` | `delete_node` | Sí |
| 657 | POST | `/api/boards/{board_id}/edges` | `create_edge` | Sí |
| 684 | PATCH | `/api/edges/{edge_id}` | `update_edge` | Sí |
| 703 | DELETE | `/api/edges/{edge_id}` | `delete_edge` | Sí |
| 718 | GET | `/api/health` | `health` | No |

**No hay catch-all** (`/{path_name}`), ni rutas para `index.html`, ni manejo de 404.

Todas las rutas comparten el prefijo `/api/` pero **no hay un router `/api`** — se definen individualmente.

---

## 4. StaticFiles / app.mount / frontend estático

**No existe nada.** No hay:

- `StaticFiles` ni `app.mount("/", ...)`
- `app.mount("/assets", ...)`
- Referencias a `dist/`, `build/`, ni al frontend de Vite
- Comentarios ni código legacy sobre servir frontend desde FastAPI

El directorio `nodeboard-backend/frontend/api.js` existe pero es un **cliente REST legacy del prototipo** (sin uso, marcado como histórico). No es un build de frontend.

El frontend real está en `src/` (raíz del proyecto), se sirve con Vite dev server en :5174 y en producción se espera que Vite genere el build estático — pero el backend **nunca** lo sirve actualmente.

---

## 5. Puerto de escucha

**Hardcodeado a 8001** en todos lados:

- **`package.json`** línea 9 — script `dev:api`:
  ```bash
  uvicorn app.main:app --reload --port 8001 --app-dir nodeboard-backend
  ```
- **Comentario en `main.py`** línea 38:
  ```python
  # uvicorn app.main:app --reload --port 8001
  ```
- **No hay** `if __name__ == "__main__"` con `uvicorn.run()`.
- **No hay** lectura de variable de entorno `$PORT`.

Para Railway esto es crítico: la plataforma inyecta `$PORT` y espera que el servidor escuche ahí.

---

## 6. Estructura de carpetas (2 niveles)

```
nodeboard-backend/
├── .env                        # GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_CALLBACK_URL
├── .venv/                      # Entorno virtual Python
├── README.md
├── alembic.ini                 # Config de migraciones
├── app/
│   ├── __init__.py
│   ├── auth.py                 # verify_google_token(), create_session()
│   ├── database.py             # engine + SessionLocal + get_db
│   ├── main.py                 # FastAPI app + todas las rutas
│   ├── models.py               # SQLAlchemy ORM (User, Session, Studio, Folder, Board, Node, Edge)
│   └── schemas.py              # Pydantic schemas
├── frontend/
│   └── api.js                  # ❌ Histórico, no usar
├── migrations/
│   ├── README
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── nodeboard.db                # SQLite (gitignored)
├── pytest.ini
├── requirements.txt
└── tests/
    ├── test_api.py
    ├── test_multi_user.py
    └── test_tags_label.py
```

No hay directorio `routers/`, ni `config/`, ni `middleware/`. Todo vive en `app/main.py`.

---

## Resumen de acciones necesarias para Etapa 3 (Railway)

| Ítem | Estado actual | Acción necesaria |
|------|--------------|------------------|
| CORS | Orígenes hardcodeados (`localhost:5174`) | Leer `ALLOWED_ORIGINS` de env, incluir dominio de Railway |
| Puerto | Hardcodeado `8001` | Leer `$PORT` del env, fallback a 8001 |
| Servir frontend | No existe | Montar `StaticFiles` desde `../dist/` (build de Vite) |
| Catch-all SPA | No existe | Agregar ruta catch-all que sirva `index.html` |
| Dockerfile | No existe | Crear `Dockerfile` con Python + Vite build + uvicorn |
