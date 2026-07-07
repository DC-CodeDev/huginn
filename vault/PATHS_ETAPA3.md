# Inventario de Paths HTTP — main.py

> Archivo: `nodeboard-backend/app/main.py`
> Propósito: preparar Etapa 3 (CORS + Dockerfile + frontend estático desde FastAPI).
> Total: **25 endpoints**.

---

## Prefijo común

**Todos los paths comienzan con `/api`** — hay consistencia total.

No existe ningún path con prefijo distinto, ni rutas en `/` raíz, ni wildcards/catch-all (`/{path:path}`).

---

## Lista completa (orden de definición en el archivo)

### Auth (3 endpoints)

| Línea | Método | Path exacto |
|-------|--------|-------------|
| 239 | `POST` | `/api/auth/login` |
| 279 | `POST` | `/api/auth/logout` |
| 294 | `GET` | `/api/auth/me` |

### Studios (3 endpoints)

| Línea | Método | Path exacto |
|-------|--------|-------------|
| 302 | `POST` | `/api/studios` |
| 317 | `GET` | `/api/studios` |
| 331 | `DELETE` | `/api/studios/{studio_id}` |

### Folders (3 endpoints)

| Línea | Método | Path exacto |
|-------|--------|-------------|
| 344 | `POST` | `/api/folders` |
| 358 | `GET` | `/api/studios/{studio_id}/folders` |
| 374 | `DELETE` | `/api/folders/{folder_id}` |

### Boards (8 endpoints)

| Línea | Método | Path exacto |
|-------|--------|-------------|
| 387 | `GET` | `/api/boards` |
| 411 | `POST` | `/api/boards` |
| 437 | `GET` | `/api/studios/{studio_id}/boards` |
| 467 | `GET` | `/api/folders/{folder_id}/boards` |
| 492 | `GET` | `/api/boards/{board_id}` |
| 501 | `GET` | `/api/boards/{board_id}/tags` |
| 517 | `PATCH` | `/api/boards/{board_id}` |
| 531 | `DELETE` | `/api/boards/{board_id}` |
| 541 | `PUT` | `/api/boards/{board_id}/state` |

### Nodes (3 endpoints)

| Línea | Método | Path exacto |
|-------|--------|-------------|
| 591 | `POST` | `/api/boards/{board_id}/nodes` |
| 614 | `PATCH` | `/api/nodes/{node_id}` |
| 633 | `DELETE` | `/api/nodes/{node_id}` |

### Edges (3 endpoints)

| Línea | Método | Path exacto |
|-------|--------|-------------|
| 657 | `POST` | `/api/boards/{board_id}/edges` |
| 684 | `PATCH` | `/api/edges/{edge_id}` |
| 703 | `DELETE` | `/api/edges/{edge_id}` |

### Health (1 endpoint, sin auth)

| Línea | Método | Path exacto |
|-------|--------|-------------|
| 718 | `GET` | `/api/health` |

---

## Path params / wildcards

Todos los `{param}` son **path params simples con tipo `str` implícito** (FastAPI default).

| Path param | Aparece en |
|-----------|------------|
| `{studio_id}` | `/api/studios/{studio_id}`, `/api/studios/{studio_id}/folders`, `/api/studios/{studio_id}/boards` |
| `{folder_id}` | `/api/folders/{folder_id}`, `/api/folders/{folder_id}/boards` |
| `{board_id}` | `/api/boards/{board_id}`, `/api/boards/{board_id}/tags`, `/api/boards/{board_id}/state`, `/api/boards/{board_id}/nodes`, `/api/boards/{board_id}/edges` |
| `{node_id}` | `/api/nodes/{node_id}` |
| `{edge_id}` | `/api/edges/{edge_id}` |

**No hay** wildcards de tipo `:path`, ni rutas de catch-all, ni `/{algo}` sueltos, ni `/`.

---

## Lo que NO existe (relevante para Etapa 3)

- ❌ Ruta `/` raíz
- ❌ Catch-all `/{path:path}` para SPA
- ❌ `StaticFiles` montado
- ❌ `app.mount(...)` de ningún tipo
- ❌ Rutas fuera del prefijo `/api`
- ❌ `app.include_router()`
