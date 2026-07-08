# Auditoría de Huginn — Preparación para multiusuario y producción

> Proyecto: Huginn, parte de Yggdrasil Suite.
> Fecha: 6 de julio de 2026
> Contexto: Monousuario hoy. Se audita frente al patrón Muninn (producción en Railway con un único SQLite, Google OAuth, ownership vía `studios.user_id`).

---

## 1. Modelo de datos

### Studio (tabla `studios`)

```python
class Studio(Base):
    __tablename__ = "studios"
    id: str (PK)
    name: str
    color: str
    # Sin user_id, sin created_at
```

**Ausencia crítica**: No hay columna `user_id`. Según el patrón Muninn, `Studio` debe tener `user_id: str` como raíz de ownership. Toda entidad hija (Folder, Board, Node, Edge) hereda propiedad vía FK hasta llegar a Studio, sin repetir `user_id` en cada tabla.

### Estructura actual de la jerarquía

```
Studio ──┬── Folder (studio_id FK, ON DELETE CASCADE)
         │          └── Board (folder_id FK, ON DELETE SET NULL)
         └── Board (studio_id FK, ON DELETE CASCADE)
                  ├── Node (board_id FK, ON DELETE CASCADE)
                  └── Edge (board_id FK, ON DELETE CASCADE)
```

**Compatibilidad con Muninn**: La estructura es compatible en un sentido: agregar `user_id` a Studio alcanza para que Folder y Board hereden propiedad vía `studios.user_id`. Node y Edge heredan vía `boards.studio_id`. **No es necesario** agregar `user_id` a Folder, Board, Node ni Edge. Esto coincide exactamente con el patrón Muninn.

### Aspectos que asumen monousuario (implícitos)

1. **`GET /api/boards` (list_boards)**: Lista todos los boards de la base de datos sin ningún filtro por usuario. En un escenario multiusuario, cada usuario vería los boards de todos los demás.
2. **`GET /api/studios` (list_studios)**: Igual — lista todos los studios sin filtro.
3. **`POST /api/studios` (create_studio)**: No asigna ningún usuario; el studio queda huérfano de identidad.
4. **No hay concepto de "usuario actual"**: No hay dependencia de request.user, ni token JWT, ni cookie de sesión. Toda función de ruta recibe solo `db: Session = Depends(get_db)`.
5. **El frontend no tiene estado de sesión**: No hay contexto de usuario, ni token en localStorage, ni header `Authorization`.

### Columnas y constraints pendientes

- **`Studio` sin `created_at`**: Todas las demás entidades tienen timestamps. Studio no.
- **`Studio.folder_id`**: No existe una FK inversa desde Folder hacia Studio para navegación. La relación ORM existe vía `back_populates`.
- **`Folder` sin `created_at`/`updated_at`**: Solo Board los tiene.
- **`Edge` sin `created_at`**: No es crítico pero es inconsistente.

---

## 2. Endpoints existentes — validación de ownership

A continuación, el listado completo de endpoints y su estado frente a falta de validación de propiedad. **Todos los endpoints que buscan recursos por ID directo sin filtrar por usuario son vulnerables el día que haya más de un usuario.**

### Sin autenticación ni filtro de ownership (todos)

| Endpoint | Método | ¿Valida ownership? | Riesgo |
|---|---|---|---|
| `GET /api/studios` | GET | No. Lista todos los studios. | Usuario A ve studios de usuario B. |
| `POST /api/studios` | POST | No. Crea studio sin user_id. | Studio huérfano. |
| `DELETE /api/studios/{id}` | DELETE | No. Solo verifica que el studio exista. | Usuario A borra studio de usuario B. |
| `GET /api/studios/{id}/folders` | GET | Valida que el studio exista (`_get_studio`), pero no quién es dueño. | Usuario A lee carpetas de B. |
| `GET /api/studios/{id}/boards` | GET | Igual. | Usuario A lee boards de B. |
| `POST /api/folders` | POST | Valida que `studio_id` exista. | Carpeta creada en studio ajeno. |
| `DELETE /api/folders/{id}` | DELETE | Solo verifica que la folder exista. | Usuario A borra carpeta de B. |
| `GET /api/folders/{id}/boards` | GET | Solo verifica que la folder exista. | Usuario A ve boards de B (si conoce folder_id). |
| `GET /api/boards` | GET | No. Lista global. | Fuga completa de datos. |
| `POST /api/boards` | POST | Valida `studio_id`, y si `folder_id` existe, valida que pertenezca al mismo studio. | Pero no valida que el studio sea del usuario actual. |
| `GET /api/boards/{id}` | GET | Solo `_get_board`. | Usuario A lee board de B con solo adivinar el UUID. |
| `GET /api/boards/{id}/tags` | GET | Solo `_get_board`. | Ídem. |
| `PATCH /api/boards/{id}` | PATCH | Solo `_get_board`. | Usuario A renombra board de B. |
| `DELETE /api/boards/{id}` | DELETE | Solo `_get_board`. | Usuario A borra board de B. |
| `PUT /api/boards/{id}/state` | PUT | Solo `_get_board`. | Usuario A sobrescribe contenido del board de B. |
| `POST /api/boards/{id}/nodes` | POST | Solo `_get_board`. | Usuario A crea nodo en board de B. |
| `PATCH /api/nodes/{id}` | PATCH | Solo `db.get(models.Node, node_id)`. | Usuario A modifica nodo de B (no verifica board ni studio). |
| `DELETE /api/nodes/{id}` | DELETE | Solo `db.get(models.Node, node_id)`. | Usuario A borra nodo de B. |
| `POST /api/boards/{id}/edges` | POST | Solo `_get_board`. | Usuario A crea edge en board de B. |
| `PATCH /api/edges/{id}` | PATCH | Solo `db.get(models.Edge, edge_id)`. | Usuario A modifica edge de B. |
| `DELETE /api/edges/{id}` | DELETE | Solo `db.get(models.Edge, edge_id)`. | Usuario A borra edge de B. |
| `GET /api/health` | GET | — | No requiere auth. |

### Resumen

**22 endpoints de negocio** sobre unos 24 totales. **Cero** verifican propiedad. **Todos son inseguros** en un escenario multiusuario.

---

## 3. Consultas a la base de datos — joins y filtros de ownership

### Consultas que buscan solo por ID (sin join a Studio)

Cada helper `_get_X` hace un `db.get(Model, id)` simple — una consulta `SELECT * FROM X WHERE id = ?` sin ningún join. Estas son las que requerirán el patrón Muninn de "buscar uniendo hasta studios.user_id":

1. **`_get_board(db, board_id)`** (main.py:66) — Solo busca `Board` por ID. Sin join a `studios`.
2. **`_get_studio(db, studio_id)`** (main.py:73) — Solo busca `Studio` por ID. Sin filtro de `user_id`.
3. **`_get_folder(db, folder_id)`** (main.py:80) — Solo busca `Folder` por ID. Sin join a `studios`.
4. **`update_node`** (main.py:350) — `db.get(models.Node, node_id)`. Sin join a `boards` ni `studios`.
5. **`delete_node`** (main.py:368) — Ídem. Y luego busca edges por `board_id` y `node_id`.
6. **`update_edge`** (main.py:411) — `db.get(models.Edge, edge_id)`. Sin join.
7. **`delete_edge`** (main.py:429) — Ídem.
8. **`list_boards`** (main.py:163) — `select(models.Board).order_by(...)`. Sin filtro de studio ni usuario.
9. **`list_studios`** (main.py:122) — `select(models.Studio).order_by(...)`. Sin filtro de usuario.

### Consultas que ya filtran por FK (pero sin ownership)

- `list_folders` (main.py:147): `Folder.studio_id == studio_id` — correcto para filtrar por Studio, pero sin verificar que el Studio pertenezca al usuario.
- `list_studio_boards` (main.py:203): `Board.studio_id == studio_id` — igual.
- `list_folder_boards` (main.py:230): `Board.folder_id == folder_id` — filtra por folder, pero sin join a Studio.
- `list_boards` (main.py:163): ninguna restricción — es la más peligrosa.

### Patrón de migración recomendado (Muninn)

En Muninn, en lugar de:

```python
board = db.get(models.Board, board_id)
```

Se usa:

```python
board = db.scalar(
    select(models.Board)
    .join(models.Studio)
    .where(models.Board.id == board_id, models.Studio.user_id == current_user.id)
)
```

Este patrón debería aplicarse a todos los helpers (`_get_board`, `_get_studio`, `_get_folder`) y a las consultas directas de Node/Edge.

---

## 4. Manejo de errores y validaciones

### Consistencia general

- **404 vs 500**: Los helpers `_get_board`, `_get_studio`, `_get_folder` lanzan `HTTPException(404)` cuando no encuentran el recurso. Esto es correcto y consistente.
- **422**: Se usa `HTTPException(422)` en `create_board` cuando `folder.studio_id != payload.studio_id` y en `create_edge` cuando los nodos referenciados no pertenecen al board. Esto es adecuado.
- **Sin 401/403**: No hay endpoints que devuelvan 401 (no autenticado) o 403 (no autorizado), porque no hay autenticación.

### Validaciones existentes (lo que está bien)

- `create_board` valida que `folder_id` pertenezca al `studio_id` indicado (main.py:181-187). Este es un buen ejemplo de validación cruzada.
- `create_edge` valida que `from.nodeId` y `to.nodeId` existan dentro del board (main.py:390-393).
- `update_node` maneja correctamente `exclude_unset` para PATCH parcial y coacciona `tags: None` a `[]` (main.py:353-358).
- `update_edge` maneja similarmente `label: None` a `""` (main.py:416-420).
- `save_board_state` hace reemplazo atómico con flush + commit (main.py:294-323), pero **no valida que ningún nodo/edge referencie IDs externos**.

### Validaciones faltantes (lo que está mal o falta)

1. **No se valida existencia de nodos referenciados por edges en `save_board_state`**: A diferencia de `create_edge`, `save_board_state` no verifica que `from.nodeId` y `to.nodeId` existan en `payload.nodes`. Si un edge referencia un nodo inexistente, se guarda igual en la DB.
2. **No se valida unicidad de IDs de nodos dentro de un board**: `save_board_state` podría recibir dos nodos con el mismo `id`. No hay chequeo.
3. **No se valida que los puertos referenciados existan**: Tanto en `create_edge` como en `save_board_state`, se valida que los nodos existan, pero no que los `portId` existan dentro de `node.ports`. Esto podría crear edges huérfanos a nivel de puerto.
4. **`create_node` no valida tipos Pydantic**: `payload.model_dump()` se llama antes de guardar, pero la validación de Pydantic ya ocurrió en la capa de request. No hay validación extra de negocio.
5. **`delete_folder` no reasigna boards a la raíz**: Según la regla documentada en `models.py:7-9`, borrar una Folder NO debe borrar sus Boards — deben pasar a la raíz. Pero `main.py:156-158` solo hace `db.delete(_get_folder(db, folder_id))`. **ON DELETE SET NULL** en la FK `folder_id` (models.py:71-73) sí maneja esto a nivel DB, pero el modelo Folder no tiene `cascade` hacia Boards — la FK tiene `ondelete="SET NULL"`, por lo que SQLite con `PRAGMA foreign_keys=ON` pondrá `folder_id = NULL` en los boards al borrar la folder. Esto es correcto.
6. **`list_folder_boards` no valida que los boards listados pertenezcan realmente a la folder**: Filtra por `Board.folder_id == folder_id`, pero si un board tiene `folder_id` apuntando a una folder de otro Studio (inconsistencia), se listaría igual.

---

## 5. Configuración de base de datos — PRAGMA, ON DELETE, CASCADE

### PRAGMA foreign_keys

**Sí está habilitado**. En main.py:37-42:

```python
@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _):
    try:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass
```

Esto se ejecuta en cada conexión. Buen patrón. El `try/except` silent es cuestionable (un error aquí pasaría inadvertido), pero aceptable para una base embebida.

### Políticas ON DELETE

| Relación | Models | ¿Coherente? |
|---|---|---|
| `Studio → Folder` | `cascade="all, delete-orphan"` en `Studio.folders` + `ForeignKey("studios.id", ondelete="CASCADE")` en `Folder.studio_id` | **Sí**. Borrar Studio borra sus Folders. |
| `Studio → Board` | `cascade="all, delete-orphan"` en `Studio.boards` + `ForeignKey("studios.id", ondelete="CASCADE")` en `Board.studio_id` | **Sí**. Borrar Studio borra sus Boards. |
| `Folder → Board` | `ForeignKey("folders.id", ondelete="SET NULL")` en `Board.folder_id` | **Sí**. Borrar Folder pone `folder_id=NULL` en los Boards (pasan a raíz del Studio). |
| `Board → Node` | `cascade="all, delete-orphan"` en `Board.nodes` + `ForeignKey("boards.id", ondelete="CASCADE")` en `Node.board_id` | **Sí**. |
| `Board → Edge` | `cascade="all, delete-orphan"` en `Board.edges` + `ForeignKey("boards.id", ondelete="CASCADE")` en `Edge.board_id` | **Sí**. |

**Conclusión**: Las políticas de borrado son correctas y coherentes con la regla de negocio documentada (borrar Folder no borra Boards; pasan a raíz). No hay cambios necesarios.

**Pero**: `Folder.boards` tiene `relationship(..., foreign_keys="[Board.folder_id]")` pero **no tiene `cascade`**. Esto significa que si se borra un Folder vía ORM (`db.delete(folder)`), los Boards asociados NO se borran (correcto, gracias a `SET NULL` en la FK), pero la ORM no sabe que debe refrescar `folder.boards` después del borrado. Esto no causa errores porque el `SET NULL` ocurre a nivel SQL.

---

## 6. Índices actuales y faltantes

### Índices existentes

| Columna | Tabla | Definido en models.py |
|---|---|---|
| `studio_id` | `folders` | `index=True` (línea 50) |
| `studio_id` | `boards` | `index=True` (línea 69) |
| `folder_id` | `boards` | `index=True` (línea 72) |
| `board_id` | `nodes` | `index=True` (línea 92) |
| `board_id` | `edges` | `index=True` (línea 114) |

### Índices faltantes

| Columna | Tabla | ¿Por qué se necesita? |
|---|---|---|
| `user_id` | `studios` | **Crítico para multiusuario**. Todas las búsquedas de ownership empezarán por `WHERE studios.user_id = ?`. |
| `from_node` | `edges` | Se busca en `delete_node` (main.py:373-378): `WHERE from_node = ? OR to_node = ?` |
| `to_node` | `edges` | Ídem. |
| `name` | `studios` | Se ordena por `name` en `list_studios`. |
| `updated_at` | `boards` | Se ordena por `updated_at DESC` en varias listas. |
| `folder_id` → `NULL` | `boards` | El índice en `folder_id` ya existe (es índice, no único), cubre este caso. |

**Nota**: `from_node`, `to_node` y `name` no tienen índice hoy. No es crítico en monousuario con pocos registros, pero escalará mal con cientos de nodos y edges. Especialmente `delete_node` hace un `SELECT ... OR` sobre `from_node` y `to_node` — sin índices, escanea toda la tabla.

---

## 7. Variables de entorno y configuración sensible

### Estado actual

| Variable | ¿Dónde se usa? | ¿Hardcodeado? | ¿Seguro para Railway? |
|---|---|---|---|
| `NODEBOARD_DB` | `database.py:8` | Default: `sqlite:///./nodeboard.db` — leído de env var con fallback. | **Sí**, pero Railway necesita que apunte a un path persistente (`/data/nodeboard.db` o similar). |
| `VITE_API_URL` | `api.ts:8` | Default: `""` (mismo origen via proxy de Vite). | **No crítico**, pero en Railway no hay proxy de Vite; debe apuntar al dominio real del backend. |
| Orígenes CORS | `main.py:55` | **Hardcodeado**: `["http://localhost:5174", "http://127.0.0.1:5174", "http://localhost:3000"]` | **Bloqueante para producción**. Debe leerse de `CORS_ORIGINS` env var. |
| Puerto backend | — | Hardcodeado en `uvicorn.run` o CLI (puerto 8001). Debe ser configurable via `PORT` env var. | Railway asigna puerto dinámico via `$PORT`. |
| Secretos | — | No hay secretos (JWT, API keys, OAuth) porque no hay autenticación. | Se agregarán con OAuth. |

### Problemas bloqueantes para Railway

1. **CORS hardcodeado**: Sin variable de entorno, el backend rechazará requests desde el dominio de Railway.
2. **Puerto fijo**: Uvicorn debe escuchar en `$PORT` (lo asigna Railway) y no en 8001.
3. **Proxy de Vite en desarrollo**: `vite.config.ts` proxy `/api` a `127.0.0.1:8001`. En Railway no hay Vite sirviendo el frontend; se necesita un servidor estático (nginx, o servir desde FastAPI) que apunte al backend real.
4. **DB path**: `NODEBOARD_DB` debe configurarse para Railway volume persistente (`/data/`).
5. **Google OAuth**: Hoy no existe. Habrá que agregar variables para `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`.

---

## 8. Estructura de build y Docker

### Dockerfile: NO EXISTE

No hay Dockerfile ni docker-compose.yml. El monorepo tiene esta estructura:

```
huginn/
├── nodeboard-backend/          # Backend Python (FastAPI)
│   ├── app/                    # Código fuente
│   │   ├── main.py             # FastAPI app + routes
│   │   ├── models.py           # SQLAlchemy ORM
│   │   ├── schemas.py          # Pydantic schemas
│   │   ├── database.py         # DB engine + session
│   │   └── __init__.py
│   ├── tests/                  # Backend tests (pytest)
│   ├── requirements.txt        # Python deps
│   ├── pytest.ini
│   └── .venv/                  # (ignorado)
├── src/                        # Frontend React + TypeScript
│   ├── main.tsx
│   ├── NodeBoard.tsx
│   ├── api.ts
│   ├── types.ts
│   ├── components/
│   └── lib/
├── e2e/                        # Playwright tests
│   ├── *.spec.ts
│   └── helpers.ts
├── index.html                  # SPA entry
├── package.json                # Node deps + scripts
├── vite.config.ts
├── tsconfig*.json
├── playwright.config.ts
└── .gitignore
```

### Dependencias

- **Frontend**: Node.js, Vite build → `dist/` estática.
- **Backend**: Python 3.x, FastAPI, uvicorn, SQLAlchemy, Pydantic.
- **Base de datos**: SQLite (embebida, no requiere servidor externo).
- **Sin shared/ común**: No hay paquete compartido entre frontend y backend; los tipos se duplican manualmente entre `types.ts` y `schemas.py`.

### Patrón Docker sugerido (basado en Muninn)

```
Dockerfile:
  Etapa 1: Node → npm install && npm run build → dist/
  Etapa 2: Python → pip install -r requirements.txt
  Etapa final:
    - Copiar dist/ desde etapa 1
    - Copiar nodeboard-backend/ desde etapa 2
    - uvicorn app.main:app --host 0.0.0.0 --port $PORT
    - Servir dist/ como static files desde FastAPI (o con nginx)
```

**Decisión importante**: En Railway, la app corre como un solo proceso. Hay dos opciones:
1. FastAPI sirve los estáticos de `dist/` además de la API (más simple).
2. Frontend separado en Railway Static Sites (más escalable, pero requiere dos servicios).

Muninn usa FastAPI sirviendo estáticos + API en un mismo proceso. Huginn debería seguir el mismo patrón para simplicidad inicial.

---

## 9. Tests existentes — cobertura

### Backend (pytest)

| Archivo | Tests | ¿Qué cubre? |
|---|---|---|
| `tests/test_api.py` | 2 | Health endpoint + BoardStateSave schema contract. **Mínimo**. |
| `tests/test_tags_label.py` | 19 | Tags roundtrip, label roundtrip, PATCH preserve/update/null, board tags aggregation, edge creation, studio/folder CRUD, serialización JSON de ports/blocks. |

**Total backend**: 21 tests. **Cubren**: CRUD de Studio/Folder/Board/Node/Edge, tags, label, PATCH parcial, serialización.

**No cubren**: 
- Autenticación (no existe).
- Ownership (no existe).
- Endpoints de Studio/Folder/Board sin pasar por helpers de test (la mayoría se testea indirectamente).
- `list_boards` (el global).
- `delete_studio`, `delete_folder`, `delete_board`, `delete_node`, `delete_edge` (solo se testea creación).
- `save_board_state` con estado inválido (nodos duplicados, edges sin nodos).
- `create_edge` con puerto inexistente.
- Concurrencia / race conditions.
- `_get_folder` con folder_id inexistente en `create_board` (solo se testea folder de otro studio).

### Frontend (vitest)

| Archivo | Tests | ¿Qué cubre? |
|---|---|---|
| `lib/geometry.test.ts` | — | Geometría de puertos y paths. |
| `lib/filter.test.ts` | — | Filtro visual por tags. |

**Total frontend unitario**: 2 archivos de test (cantidad no contada). **No cubren**: Componentes (`NodeCard`, `Timeline`, `Block`, `TagsModal`, etc.), API client, lógica de estado del canvas, copy/paste, selección.

### E2E (Playwright)

| Archivo | Tests | ¿Qué cubre? |
|---|---|---|
| `navigation.spec.ts` | 6 | Home, creación de Studio, vista de Studio, vista de Folder, botón atrás desde board. |
| `persist.spec.ts` | 1 | Nodo creado persiste tras recargar. |
| `create-node.spec.ts` | 1 | Crear nodo card incrementa contador. |
| `connect-edge.spec.ts` | 1 | Conectar puertos crea arista visible. |
| `multi-select.spec.ts` | 5 | Shift/ctrl click, reemplazo de selección, deseleccionar, group drag, drag fuera de selección. |
| `copy-paste.spec.ts` | 2 | Ctrl+C/V simple y múltiple con posiciones relativas. |
| `tags-modal.spec.ts` | 1 | Flujo completo: crear tag, persistir, sugerir en otro nodo, filtrar, quitar. |

**Total E2E**: 17 tests. **Cubren**: Navegación Studio→Folder→Board, persistencia básica, multiselección, copy/paste, tags, conexión de puertos.

**No cubren**:
- Eliminación de nodos/edges vía teclado.
- Eliminación de Studios/Folders/Boards desde la UI.
- Filtro visual por tags.
- Resize de nodos.
- Timeline node creation/edition.
- Image blocks.
- Dark/light theme toggle.
- Zoom y pan.
- Color picker en puertos.

### Cobertura general

| Capa | Tests | Cobertura de features |
|---|---|---|
| Backend unitario | 21 | ~60% de los endpoints, ~40% de casos borde |
| Frontend unitario | Mínima | Solo geometría y filtro |
| E2E | 17 | Flujos principales (~50% de features visibles) |

---

## 10. Deuda técnica general

### 10.1 Backend

1. **Duplicación de `model_dump()`**: En `save_board_state` (main.py:304) y `create_node` (main.py:333) se llama a `dumped = payload.model_dump()` para aplanar modelos Pydantic a dicts para JSON. Esto es necesario por cómo funciona SQLAlchemy + JSON, pero el patrón podría encapsularse en un método helper.

2. **La ruta `list_boards` (GET /api/boards) hace un N+1**: Por cada board, ejecuta dos consultas adicionales para contar nodos y edges (main.py:168-173). Con 100 boards, son ~201 queries. Esto debería ser un `LEFT JOIN` con `func.count()` en una sola consulta, o al menos usar `selectinload` para eager loading.

3. **`list_studio_boards` y `list_folder_boards` tienen el mismo N+1**: Mismas consultas de conteo por board (main.py:213-218, 237-242, repetido 3 veces).

4. **`delete_node` hace limpieza manual de edges**: En lugar de confiar en `ON DELETE CASCADE` de la FK, busca edges conectados y los borra uno por uno (main.py:373-380). Esto es redundante si `PRAGMA foreign_keys=ON` está activo (y lo está).

5. **`delete_edge` no verifica que el edge pertenezca a un board accesible**: Solo verifica que el edge exista. Podría ser aceptable, pero en multiusuario es un agujero.

6. **Módulo `frontend/` duplicado**: Existe `nodeboard-backend/frontend/api.js` que parece ser un vestigio de una versión anterior. Contiene código cliente JS que replica `src/api.ts`.

7. **Comentario `app.main` en lugar de `app.main:app`**: En `database.py` no hay problema, pero `package.json` usa path explícito. No es error, pero muestra falta de consistencia histórica.

8. **`httpx` en requirements.txt**: Se agregó en `requirements.txt` pero no se usa en ninguna parte del código actual.

### 10.2 Frontend

1. **`NodeBoard.tsx` es un componente monolítico**: ~700+ líneas con toda la lógica del canvas (estado, eventos, renderizado, persistencia). Está documentado en AGENTS.md, pero debería dividirse en hooks (useCanvas, useSelection, useClipboard, etc.) para mantenibilidad.

2. **Tipos duplicados manualmente**: `types.ts` (TypeScript) y `schemas.py` (Python) definen las mismas estructuras. No hay generación automática ni un paquete compartido. Cualquier cambio requiere actualizar ambos archivos sincrónicamente.

3. **`PORT_COLORS` duplicado**: Definido en `types.ts` como array y en `schemas.py` como `PortColor = Literal[...]`. Si se agrega un color, hay que cambiar ambos.

4. **`STUDIO_COLOR_MAP` duplicado en Home.tsx**: Mapea nombres de color a hex. La información cromática está distribuida entre `types.ts`, `StudioView.tsx` y `Home.tsx`.

5. **Sin tipos Pydantic en frontend**: Las respuestas de API se tipan manualmente. No hay código generado a partir de schemas de backend.

6. **Sin tests de componentes**: `NodeCard`, `Timeline`, `Block`, `TagsModal` no tienen tests unitarios.

7. **CSS manual vs Tailwind**: Se usa CSS-in-JS con objetos `style` en casi todos los componentes, más que clases Tailwind. El `styles.css` importa Tailwind pero apenas lo usa. Esto no es un error, pero hace que los temas oscuro/claro dependan de lógica JS y no de clases CSS como `dark:`.

### 10.3 Configuración y build

1. **`package.json` usa `latest` para todas las dependencias**: `"@tailwindcss/vite": "latest"`, `"react": "latest"`, etc. Esto es peligroso porque diferentes builds pueden producir diferentes resultados. Deberían fijarse versiones.

2. **`vitest` usa `^4.1.9`**: Una versión específica, bien. Pero `typescript: "latest"` en devDependencies es volátil.

3. **No hay script de migración de DB**: SQLAlchemy `create_all` se ejecuta en startup (lifespan). No hay Alembic ni sistema de migraciones. Para agregar `user_id` a Studio, habría que o bien borrar la DB existente o escribir migración manual.

4. **No hay linter/prettier configurado**: No se encuentra `.eslintrc`, `.prettierrc`, `ruff.toml` ni similar.

### 10.4 Vault

1. **`vault/Archivos/` contiene snapshots desactualizados**: Los archivos `.md` en `vault/Archivos/` son copias de archivos fuente reales y pueden estar desactualizados (el propio AGENTS.md advierte esto). Esto puede causar confusión al hacer búsquedas.

---

## Resumen ejecutivo — 5 hallazgos más críticos

Ordenados por prioridad:

### 🔴 1. Ausencia total de autenticación y ownership (multiusuario)

**Impacto**: Bloqueante. Sin `user_id` en Studio y sin validación en ningún endpoint, el día que haya dos usuarios, cada uno verá, modificará y borrará los datos del otro sin restricción. Los 22 endpoints de negocio son vulnerables.

**Qué hacer**: Agregar `user_id` a Studio, implementar Google OAuth (siguiendo el patrón Muninn), y modificar todos los helpers `_get_*` y queries para que filtren/verifiquen ownership uniendo hasta `studios.user_id`.

### 🔴 2. CORS hardcodeado y puerto fijo (producción)

**Impacto**: Bloqueante para cualquier deploy. El backend solo acepta requests de `localhost:5174` y `localhost:3000`. Railway asigna un dominio y un puerto dinámico.

**Qué hacer**: Leer `CORS_ORIGINS` de env var, usar `$PORT` para uvicorn. También configurar `VITE_API_URL` o servir estáticos desde FastAPI para que no dependa del proxy de Vite.

### 🟠 3. Sin Dockerfile ni estrategia de build (producción)

**Impacto**: No se puede desplegar en Railway sin Dockerfile. El monorepo tiene frontend (Node build) y backend (Python) que deben combinarse en una imagen.

**Qué hacer**: Crear Dockerfile multi-stage siguiendo el patrón Muninn: build Node → dist/, luego Python con FastAPI sirviendo estáticos + API.

### 🟠 4. N+1 queries y falta de índices (escalabilidad)

**Impacto**: Tres rutas (`list_boards`, `list_studio_boards`, `list_folder_boards`) hacen consultas N+1 para contar nodos y edges. Sin índices en `from_node`/`to_node` de edges, el borrado de nodos escanea toda la tabla. Esto escala mal incluso en monousuario.

**Qué hacer**: Reemplazar con `LEFT JOIN` + `func.count()` en una sola query. Agregar índices compuestos en `edges(from_node)` y `edges(to_node)`.

### 🟠 5. Sin migraciones de DB (mantenibilidad a largo plazo)

**Impacto**: `Base.metadata.create_all()` en startup solo crea tablas nuevas. No modifica tablas existentes. Para agregar `user_id` a Studio, la DB existente en producción (con datos de usuarios) no se actualizaría automáticamente. No hay Alembic ni mecanismo de migración.

**Qué hacer**: Agregar Alembic para manejar migraciones. Para el caso inmediato de `user_id`, escribir una migración que agregue la columna con un valor por defecto (ej. un UUID de "usuario por defecto") y luego hacerla NOT NULL una vez que OAuth esté implementado.

---

*Documento generado el 6 de julio de 2026. Auditoría basada en el código fuente en `/home/diego/Projects/huginn/`. Próximo paso recomendado: reunión de priorización para decidir orden de abordaje de los hallazgos.*
