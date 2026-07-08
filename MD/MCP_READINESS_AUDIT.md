# MCP Readiness Audit for Huginn

> Auditoría técnica de preparación del proyecto Huginn para implementar un servidor MCP (Model Context Protocol) que permita a agentes externos (Claude, ChatGPT/OpenAI Agents, OpenClaw, Codex, etc.) consultar y modificar contenido dentro de Huginn.

---

## 1. Resumen ejecutivo

| Elemento | Valor |
|----------|-------|
| **Preparación MCP estimada** | **15–20 %** |
| **Bloqueante principal** | Ausencia total de capa de servicios: toda la lógica de negocio está incrustada en rutas FastAPI |
| **Segundo bloqueante** | Autenticación exclusivamente por cookie httpOnly session — ningún cliente MCP no-browser puede autenticarse |
| **Tercer bloqueante** | Sin versionado ni control de concurrencia — el autosave del frontend sobrescribiría cambios MCP silenciosamente |
| **Cuarto bloqueante** | Sin sistema de logging/auditoría de operaciones |
| **Quinto bloqueante** | Sin operaciones transaccionales por lote ni transacciones explícitas en endpoints complejos |

**Conclusión:** Huginn **no está listo** para exponer herramientas MCP de escritura sin un refactor estructural significativo. Las herramientas de solo lectura son viables con cambios menores. Se necesita un plan por fases que comience con refactor arquitectónico (Fase 0) antes de exponer cualquier herramienta MCP de escritura.

---

## 2. Arquitectura actual

```
Cliente (navegador React)
  │ fetch() con cookie
  ▼
FastAPI route (main.py)
  │ lógica de negocio dentro del handler
  ▼
helpers inline (_get_board, _get_owned_node, etc.)
  ▼
SQLAlchemy ORM session
  ▼
SQLite (un solo archivo)
```

### 2.1 Frontend

| Elemento | Estado | Archivo | Detalle |
|----------|--------|---------|---------|
| Framework | `IMPLEMENTADO` | `src/` | React 19 + TypeScript + Vite 8 + Tailwind v4 |
| HTTP client | `IMPLEMENTADO` | `src/api.ts:29-39` | `fetch()` con `credentials: "include"` |
| Carga de boards | `IMPLEMENTADO` | `src/api.ts:117-142` | `useBoardPersistence` → `GET /api/boards/{id}` |
| Guardado | `IMPLEMENTADO` | `src/api.ts:117-161` | Autosave con debounce 800ms → `PUT /api/boards/{id}/state` |
| Tipo de guardado | `SNAPSHOT TOTAL` | `src/api.ts:148-149` | Envía `{nodes, edges}` completo cada vez |
| Creación de IDs | `IMPLEMENTADO` | `src/lib/id.ts` | `uid()` genera IDs en frontend |
| Tipos de nodos | `IMPLEMENTADO` | `src/types.ts:26-48` | `card` (con `blocks[]`) y `timeline` (con `stages[]`) |
| Conexiones | `IMPLEMENTADO` | `src/types.ts:59-65` | Edge con `from: {nodeId, portId}` y `to: {nodeId, portId}` |
| Posiciones | `IMPLEMENTADO` | `src/types.ts:29-30` | Coordenadas `x`, `y` absolutas en el mundo del canvas |
| Layout automático | `FALTANTE` | — | No existe ningún algoritmo de layout |
| Routing | `PARCIAL` | `src/main.tsx:19-23` | Estado local React, no URL-driven |

### 2.2 Backend

| Elemento | Estado | Archivo | Detalle |
|----------|--------|---------|---------|
| Framework | `IMPLEMENTADO` | `nodeboard-backend/app/main.py` | FastAPI — todo en un solo archivo (~886 líneas) |
| Separación capas | `FALTANTE` | `main.py` | **Sin capa de servicios.** Toda la lógica está en rutas. |
| Auth | `IMPLEMENTADO` | `main.py:239-261`, `auth.py` | `get_current_user` dependencia por cookie |
| Autorización | `PARCIAL` | `main.py:271-350` | Helpers `_get_board/studio/folder/node/edge` verifican ownership via FK chain |
| Transacciones | `PARCIAL` | `main.py` | Cada ruta hace `db.commit()` pero sin manejo explícito de rollback/boundaries |
| Manejo de errores | `IMPLEMENTADO` | `main.py` | HTTPExceptions con códigos estándar |
| Validación | `IMPLEMENTADO` | `schemas.py` | Pydantic v2 con discriminators |
| DTOs | `IMPLEMENTADO` | `schemas.py` | `NodeSchema`, `EdgeSchema`, `BoardState`, etc. |
| Logging | `MÍNIMO` | `database.py` | Solo logging de startup de DB. Sin logging de operaciones. |

**Estructura actual (plana):**

```
nodeboard-backend/app/
├── __init__.py
├── main.py        ← 886 líneas: auth, rutas, helpers, middlewares, SPA catch-all
├── models.py      ← ORM (User, Session, Studio, Folder, Board, Node, Edge)
├── schemas.py     ← Pydantic (NodeSchema, EdgeSchema, BoardState, etc.)
├── auth.py        ← Google OAuth verify + session management
└── database.py    ← SQLite engine, session factory, path resolution
```

### 2.3 Persistencia

| Elemento | Estado | Detalle |
|----------|--------|---------|
| Motor | `IMPLEMENTADO` | SQLite 3.x vía SQLAlchemy 2.x |
| Tablas | `IMPLEMENTADO` | `users`, `sessions`, `studios`, `folders`, `boards`, `nodes`, `edges` |
| Relaciones | `IMPLEMENTADO` | FK: Studio→User, Folder→Studio, Board→Studio/Folder, Node→Board, Edge→Board |
| Columnas JSON | `IMPLEMENTADO` | `nodes.ports`, `nodes.blocks`, `nodes.stages`, `nodes.tags` |
| Restricciones | `PARCIAL` | FKs con CASCADE, `PRAGMA foreign_keys=ON` en cada conexión |
| Índices | `IMPLEMENTADO` | `ix_*` en todas las FKs |
| Versionado | `FALTANTE` | No existe campo `version` en ninguna tabla |
| Timestamps | `PARCIAL` | `created_at`/`updated_at` en `users`, `boards`; solo `created_at` en `sessions`, `studios` |
| Soft delete | `FALTANTE` | Eliminación física siempre |
| Transacciones explícitas | `FALTANTE` | Cada ruta `commit()` individual, sin `begin()`/`rollback()` |
| Migraciones | `IMPLEMENTADO` | Alembic con 3 migraciones (schema inicial, multi-user, timezone fix) |

---

## 3. Inventario de entidades y operaciones

### 3.1 User

| Campo | Descripción |
|-------|-------------|
| **Modelo** | `models.py:36` — `class User(Base)` |
| **Identificador** | `String(32)` — `uuid4().hex` |
| **Propietario** | Es el sujeto de ownership. Todos los recursos se vinculan a `User.id` |
| **Creación** | `main.py:392-399` — dentro de `login()`, auto-creación en primer ingreso |
| **Lectura** | `main.py:433-435` — `GET /api/auth/me` |
| **Actualización** | `main.py:402-405` — name/avatar_url se actualizan en cada login |
| **Eliminación** | No hay endpoint de eliminación de usuario |
| **Validación** | Email único, auth_provider fijo |
| **Transacción** | Sí — `db.commit()` |
| **Reutilizable para MCP** | `PARCIAL` — el modelo es reutilizable, no la autenticación |
| **Riesgos** | No hay forma de desactivar cuentas. Sin rate limiting en login. |

### 3.2 Session

| Campo | Descripción |
|-------|-------------|
| **Modelo** | `models.py:57` — `class Session(Base)` |
| **Identificador** | `String(32)` — `uuid4().hex` |
| **Propietario** | `user_id` FK a User |
| **Creación** | `auth.py:105-115` — `create_session()`, llamada desde `login()` |
| **Lectura** | `auth.py:88-99` — `resolve_user_from_session()` |
| **Actualización** | No existe renovación de sesión |
| **Eliminación** | `main.py:425-430` — logout elimina la sesión; expiración automática |
| **Validación** | `expires_at` se compara con UTC ahora |
| **Transacción** | Sí |
| **Reutilizable para MCP** | `NO` — MCP no puede usar cookies del navegador |
| **Riesgos** | Sesiones de 7 días sin renovación. Una cookie robada vale 7 días. |

### 3.3 Studio

| Campo | Descripción |
|-------|-------------|
| **Modelo** | `models.py:70` — `class Studio(Base)` |
| **Identificador** | `String(32)` — `uuid4().hex` |
| **Propietario** | `user_id` FK directo a User |
| **Creación** | `main.py:441-453` — `POST /api/studios` |
| **Lectura** | `main.py:456-467` — `GET /api/studios` (lista del usuario) |
| **Actualización** | No hay endpoint de actualización |
| **Eliminación** | `main.py:470-477` — `DELETE /api/studios/{id}` |
| **Validación** | `_get_studio()` verifica ownership por `user_id` |
| **Transacción** | Sí — `db.commit()` |
| **Reutilizable para MCP** | `SÍ` — estructura simple, fácil de exponer |
| **Riesgos** | Eliminación en cascada borra folders, boards, nodes, edges |

### 3.4 Folder

| Campo | Descripción |
|-------|-------------|
| **Modelo** | `models.py:90` — `class Folder(Base)` |
| **Identificador** | `String(32)` — `uuid4().hex` |
| **Propietario** | Via `studio_id` → `Studio.user_id` |
| **Creación** | `main.py:483-494` — `POST /api/folders` |
| **Lectura** | `main.py:497-510` — `GET /api/studios/{id}/folders` |
| **Actualización** | No hay endpoint de actualización |
| **Eliminación** | `main.py:513-520` — `DELETE /api/folders/{id}` |
| **Validación** | `_get_folder()` verifica ownership via Studio |
| **Transacción** | Sí |
| **Reutilizable para MCP** | `SÍ` |
| **Riesgos** | Eliminación con `ondelete=SET NULL` en boards |

### 3.5 Board

| Campo | Descripción |
|-------|-------------|
| **Modelo** | `models.py:105` — `class Board(Base)` |
| **Identificador** | `String(32)` — `uuid4().hex` |
| **Propietario** | Via `studio_id` → `Studio.user_id` |
| **Creación** | `main.py:550-573` — `POST /api/boards` |
| **Lectura** | `main.py:631-637` — `GET /api/boards/{id}` (estado completo) |
| **Actualización** | `main.py:656-667` — `PATCH /api/boards/{id}` (rename) |
| **Eliminación** | `main.py:670-677` — `DELETE /api/boards/{id}` |
| **Validación** | `_get_board()` verifica ownership via Studio |
| **Transacción** | Sí |
| **Reutilizable para MCP** | `SÍ` para lecturas, `PARCIAL` para escrituras |
| **Riesgos** | Sin versionado, sin protección contra escrituras concurrentes |

### 3.6 Node

| Campo | Descripción |
|-------|-------------|
| **Modelo** | `models.py:133` — `class Node(Base)` |
| **Identificador** | `String(64)` — `uuid4().hex` |
| **Propietario** | Via `board_id` → `Board.studio_id` → `Studio.user_id` |
| **Creación** | `main.py:730-750` — `POST /api/boards/{id}/nodes` |
| **Lectura** | Solo via `GET /api/boards/{id}` (todos los nodos del board) |
| **Actualización** | `main.py:753-769` — `PATCH /api/nodes/{id}` (parcial) |
| **Eliminación** | `main.py:772-790` — `DELETE /api/nodes/{id}` (cascade edges) |
| **Validación** | `_get_owned_node()` verifica ownership |
| **Transacción** | Sí |
| **Reutilizable para MCP** | `SÍ` |
| **Riesgos** | No hay endpoint individual de lectura de nodo. El ID se genera en frontend. |

### 3.7 Edge

| Campo | Descripción |
|-------|-------------|
| **Modelo** | `models.py:155` — `class Edge(Base)` |
| **Identificador** | `String(64)` — `uuid4().hex` |
| **Propietario** | Via `board_id` → `Board.studio_id` → `Studio.user_id` |
| **Creación** | `main.py:796-820` — `POST /api/boards/{id}/edges` |
| **Lectura** | Solo via `GET /api/boards/{id}` |
| **Actualización** | `main.py:823-839` — `PATCH /api/edges/{id}` (curved, label) |
| **Eliminación** | `main.py:842-851` — `DELETE /api/edges/{id}` |
| **Validación** | `_get_owned_edge()` verifica ownership; valida que nodos existan |
| **Transacción** | Sí |
| **Reutilizable para MCP** | `SÍ` |
| **Riesgos** | Validación de nodos existentes solo en create. `from_` es keyword Python. |

---

## 4. Estado de la capa de servicios

### 4.1 Diagnóstico

**NO EXISTE una capa de servicios.**

Toda la lógica de negocio — desde validación de ownership hasta creación de entidades y serialización — está dentro de los handlers de ruta FastAPI.

Lo que existe son helpers internos en `main.py`:

| Helper | Línea | Propósito |
|--------|-------|-----------|
| `get_current_user()` | 239-261 | Resuelve usuario desde cookie |
| `_get_board()` | 271-284 | Board + ownership |
| `_get_studio()` | 287-300 | Studio + ownership |
| `_get_folder()` | 303-316 | Folder + ownership |
| `_get_owned_node()` | 319-333 | Node + ownership |
| `_get_owned_edge()` | 336-350 | Edge + ownership |
| `_node_to_schema()` | 353-354 | Node → NodeSchema |
| `_edge_to_schema()` | 357-364 | Edge → EdgeSchema |
| `_board_state()` | 367-374 | Board completo → BoardState |
| `_uid()` | 267-268 | Genera ID |

Estos helpers NO constituyen una capa de servicios porque:
- No son invocables desde fuera de `main.py` (prefijo `_`)
- No encapsulan transacciones
- No tienen testing unitario directo
- Están mezclados con lógica HTTP (cookies, responses, status codes)

### 4.2 Lo que hay que extraer

Cada endpoint de negocio tiene lógica reutilizable incrustada. Por ejemplo:

**`create_node`** (`main.py:730-750`):
```python
board = _get_board(db, board_id, current_user)           # autorización
dumped = payload.model_dump()                              # serialización
node = models.Node(id=..., board_id=..., ...)              # creación
db.add(node)
board.updated_at = models._now()                           # actualización timestamp
db.commit()
db.refresh(node)
return _node_to_schema(node)                               # serialización salida
```

**`save_board_state`** (`main.py:680-724`): lógica de reemplazo total que borra y recrea nodos/edges en un `flush()` antes de `commit()`. Esta lógica DEBERÍA estar en un servicio.

### 4.3 Estructura propuesta

```
nodeboard-backend/app/
├── __init__.py
├── main.py                    ← Solo rutas (delgadas), middlewares, static serving
├── database.py                ← Sin cambios
├── models.py                  ← Sin cambios
├── schemas.py                 ← Sin cambios (expandir)
├── auth.py                    ← Expandir: token MCP + session
│
├── services/                  ← NUEVO — lógica de negocio reutilizable
│   ├── __init__.py
│   ├── studios.py             ← create_studio, list_studios, delete_studio
│   ├── folders.py             ← create_folder, list_folders, delete_folder
│   ├── boards.py              ← create_board, get_board, save_board_state, etc.
│   ├── nodes.py               ← create_node, update_node, delete_node
│   ├── edges.py               ← create_edge, update_edge, delete_edge
│   └── auth.py                ← token management, scope verification
│
├── repositories/              ← NUEVO — acceso a datos (opcional, puede ser services directo)
│   └── ...
│
├── mcp/                       ← NUEVO — servidor MCP
│   ├── __init__.py
│   ├── server.py              ← FastMCP / MCPServer montable
│   ├── auth.py                ← Token validation middleware MCP
│   ├── context.py             ← User/session resolution for MCP tools
│   └── tools/                 ← Herramientas MCP organizadas
│       ├── studios.py
│       ├── boards.py
│       ├── nodes.py
│       └── edges.py
│
└── tests/
    ├── test_api.py            ← Actual + nuevos tests de rutas
    ├── test_services.py       ← NUEVO — tests unitarios de servicios
    ├── test_mcp.py            ← NUEVO — tests del servidor MCP
    └── ...
```

**Justificación:** los servicios contienen lógica de negocio pura (sin HTTP, sin cookies, sin responses). Las rutas FastAPI y las herramientas MCP llaman a los mismos servicios. Las rutas se encargan de HTTP (status codes, cookies, headers), los servicios se encargan del dominio.

---

## 5. Estado de autenticación

### 5.1 Autenticación actual (frontend → backend)

```
1. Usuario hace login con Google OAuth
2. Google redirige a /auth/callback?code=...
3. Frontend envía code a POST /api/auth/login
4. Backend verifica con Google, crea sesión (7 días)
5. Backend setea cookie httpOnly: session=<id>
6. Cada request envía cookie automáticamente
7. get_current_user() resuelve: Cookie → Session.id → User
```

**Características de la cookie actual:**
| Atributo | Valor |
|----------|-------|
| Nombre | `session` |
| httpOnly | `true` |
| secure | `true` en producción (controlado por `COOKIE_SECURE` / `ENVIRONMENT`) |
| sameSite | `lax` |
| path | `/` |
| maxAge | 7 días |

### 5.2 Por qué NO es viable para MCP

1. **Cliente no-browser**: Claude Desktop, Claude Code, OpenAI Agents no manejan cookies del navegador.
2. **SameSite lax**: Incluso si pudiera, el cliente MCP haría requests cross-origin.
3. **Sin API key**: No existe ningún mecanismo de autenticación alternativo.
4. **Sin OAuth para MCP**: MCP soporta OAuth 2.0 (authorization code flow con PKCE), pero Huginn no lo implementa.

### 5.3 Cambios necesarios

Crear tabla `mcp_tokens`:

```sql
mcp_tokens
├── id          String(32) PK      -- uuid4().hex
├── user_id     String(32) FK      -- → users.id
├── name        String(200)         -- nombre descriptivo del token
├── token_hash  String(128)         -- SHA-256 del token
├── scopes      JSON                -- ["boards:read", "nodes:write", ...]
├── constraints JSON                -- opcional: {"studio_ids": ["..."], "board_ids": ["..."]}
├── created_at  DateTime
├── last_used_at DateTime
├── expires_at  DateTime            -- opcional
├── revoked_at  DateTime            -- si no NULL, token revocado
```

**Flujo:**
1. Usuario genera token desde UI de integraciones (nuevo endpoint)
2. Backend muestra token **una sola vez** (texto plano)
3. Backend almacena solo `SHA-256(token)`
4. Cliente MCP envía token vía header `Authorization: Bearer <token>`
5. Middleware MCP resuelve token → user → scopes

**Scopes propuestos para MVP (Fase 1):**

| Scope | Descripción |
|-------|-------------|
| `studios:read` | Listar studios |
| `folders:read` | Listar carpetas |
| `boards:read` | Leer boards y su estado completo |
| `nodes:read` | Leer nodos individuales |
| `boards:create` | Crear boards (vacío) |
| `boards:update` | Renombrar boards |
| `boards:delete` | Eliminar boards |
| `nodes:create` | Crear nodos |
| `nodes:update` | Actualizar nodos (incluyendo posición) |
| `nodes:delete` | Eliminar nodos |
| `edges:create` | Crear aristas |
| `edges:delete` | Eliminar aristas |
| `layouts:execute` | Ejecutar auto-layout |

**Scopes para MVP solo lectura (Fase 1):** `studios:read`, `folders:read`, `boards:read`, `nodes:read`

---

## 6. Viabilidad de herramientas MCP

### 6.1 Lectura

| Herramienta | Viable ahora | Cambios necesarios | Riesgo | Scope requerido | MVP |
|-------------|-------------|--------------------|--------|-----------------|-----|
| `list_studios` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Bajo | `studios:read` | ✅ |
| `list_folders` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Bajo | `folders:read` | ✅ |
| `list_boards` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Bajo | `boards:read` | ✅ |
| `get_board` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Bajo | `boards:read` | ✅ |
| `get_board_summary` | `IMPLEMENTABLE AHORA` | Token auth + servicio, sería nuevo endpoint | Bajo | `boards:read` | ✅ |
| `get_node` | `IMPLEMENTABLE AHORA` | No existe GET individual de nodo. Crear servicio. | Bajo | `nodes:read` | ✅ |
| `search_nodes` | `IMPLEMENTABLE CON REFACTOR` | No existe búsqueda. Requiere endpoint nuevo con filtros. | Bajo | `nodes:read` | ⬜ |

### 6.2 Escritura

| Herramienta | Viable ahora | Cambios necesarios | Riesgo | Scope requerido | MVP |
|-------------|-------------|--------------------|--------|-----------------|-----|
| `create_studio` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Medio (creación sin límite) | `studios:create` | ⬜ |
| `create_folder` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Medio | `folders:create` | ⬜ |
| `create_board` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Medio | `boards:create` | ✅ |
| `create_node` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Medio | `nodes:create` | ✅ |
| `update_node` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Medio | `nodes:update` | ✅ |
| `move_node` | `IMPLEMENTABLE AHORA` | Es un `update_node` con x/y. | Medio | `nodes:update` | ✅ |
| `delete_node` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Alto (pérdida de datos) | `nodes:delete` | ⬜ |
| `create_edge` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Medio | `edges:create` | ✅ |
| `delete_edge` | `IMPLEMENTABLE AHORA` | Token auth + servicio | Alto (pérdida de conexión) | `edges:delete` | ⬜ |

### 6.3 Operaciones por lote

| Herramienta | Viable ahora | Cambios necesarios | Riesgo | Scope requerido | MVP |
|-------------|-------------|--------------------|--------|-----------------|-----|
| `create_nodes_batch` | `IMPLEMENTABLE CON REFACTOR` | Servicio batch + transacción | Alto (payload grande) | `nodes:create` | ✅ |
| `create_edges_batch` | `IMPLEMENTABLE CON REFACTOR` | Servicio batch + transacción | Alto | `edges:create` | ✅ |
| `move_nodes_batch` | `IMPLEMENTABLE CON REFACTOR` | Servicio batch | Alto (conflictos) | `nodes:update` | ⬜ |
| `delete_nodes_batch` | `IMPLEMENTABLE CON REFACTOR` | Servicio batch + transacción | Alto (pérdida masiva) | `nodes:delete` | ⬜ |
| `apply_board_patch` | `REQUIERE CAMBIO DE MODELO` | Versionado + locking + transacción | Crítico | Múltiples | ⬜ |

### 6.4 Alto nivel

| Herramienta | Viable ahora | Cambios necesarios | Riesgo | Scope requerido | MVP |
|-------------|-------------|--------------------|--------|-----------------|-----|
| `create_board_from_outline` | `REQUIERE CAMBIO DE MODELO` | Algoritmo de creación de nodos desde texto | Bajo (solo creación) | `boards:create`, `nodes:create`, `edges:create` | ⬜ |
| `create_mind_map` | `REQUIERE CAMBIO DE MODELO` | Algoritmo de layout tree + creación batch | Medio | `boards:create`, `nodes:create`, `edges:create`, `layouts:execute` | ⬜ |
| `create_timeline` | `REQUIERE CAMBIO DE MODELO` | Algoritmo de layout timeline | Medio | Múltiples | ⬜ |
| `create_flowchart` | `REQUIERE CAMBIO DE MODELO` | Algoritmo de layout | Medio | Múltiples | ⬜ |
| `layout_board` | `REQUIERE CAMBIO DE MODELO` | Algoritmo de auto-arrastre | Medio | `layouts:execute` | ⬜ |
| `duplicate_board` | `IMPLEMENTABLE CON REFACTOR` | Servicio de copia profunda | Medio | `boards:create`, `nodes:read` | ⬜ |
| `archive_board` | `REQUIERE CAMBIO DE MODELO` | No existe soft-delete ni archivado | Bajo | `boards:update` | ⬜ |
| `export_board` | `IMPLEMENTABLE CON REFACTOR` | Serialización a JSON/Markdown | Bajo | `boards:read` | ⬜ |

---

## 7. Concurrencia y versionado

### 7.1 Estado actual

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| Versionado de boards | `FALTANTE` | No hay campo `version` |
| `updated_at` | `PARCIAL` | Board tiene `updated_at` pero no se usa para concurrencia |
| Optimistic locking | `FALTANTE` | No existe `IF-Match` / `ETag` |
| Last-writer-wins | `SI` (implícito) | `save_board_state` reemplaza todo sin verificar estado anterior |
| Transacciones SQLite | `PARCIAL` | Cada ruta es una transacción implícita, pero no hay transacciones multi-operación |
| WAL mode | `FALTANTE` | No se configura explícitamente |
| SQLite concurrencia | `LIMITADA` | SQLite serializa escrituras; una sola réplica en Railway |

### 7.2 Escenario crítico: frontend + MCP escribiendo simultáneamente

```
1. Usuario abre frontend → carga Board v1 (versión implícita por snapshot)
2. MCP crea "Nodo A" → Board v2 (nuevo nodo en DB)
3. Frontend hace autosave después de mover "Nodo B" → envía snapshot completo
4. ⚠️ El snapshot del frontend NO incluye "Nodo A" (creado por MCP)
5. PUT /state reemplaza todo → "Nodo A" desaparece
```

**Este es el riesgo más crítico de todo el plan MCP.**

### 7.3 Mínimo necesario antes de escritura MCP

| Elemento | Prioridad | Descripción |
|----------|-----------|-------------|
| Campo `version` en Board | **CRÍTICA** | Entero incremental, se incrementa en cada cambio |
| `updated_at` preciso | **CRÍTICA** | Actualmente se actualiza bien, pero no se usa para detección |
| Optimistic locking | **CRÍTICA** | `UPDATE boards SET version = version + 1 WHERE id = X AND version = Y` |
| `apply_board_patch` con versión | **ALTA** | Operaciones incrementales en lugar de snapshots |
| Migración del frontend a patches | **ALTA** | El frontend debe usar el mismo mecanismo o al menos verificar versión |
| Detección de conflicto | **ALTA** | Si version mismatch → error, no sobrescribir |
| UI de conflicto | **MEDIA** | Notificar al usuario que hubo cambios externos y recargar |
| WAL mode en SQLite | **MEDIA** | `PRAGMA journal_mode=WAL` para mejor concurrencia lectura/escritura |

### 7.4 Clasificación de riesgos de concurrencia

| Riesgo | Severidad | Descripción |
|--------|-----------|-------------|
| Frontend sobrescribe cambios MCP | **CRÍTICO** | El autosave por snapshot completo destruye cambios externos |
| Dos agentes MCP escriben simultáneamente | **ALTO** | Sin versionado, el último en escribir gana silenciosamente |
| Múltiples pestañas del frontend | **MEDIO** | Mismo problema que frontend+MCP pero entre pestañas |
| Request duplicado por timeout | **BAJO** | Sin idempotency keys, un reintento podría duplicar operaciones |
| SQLite bloqueante en escritura intensiva | **BAJO** | SQLite serializa, aceptable para uso personal |

---

## 8. Diseño de `apply_board_patch`

### 8.1 Viability

`apply_board_patch` es la herramienta MCP más importante y la más riesgosa. Requiere:

| Requisito | Estado actual | Necesario |
|-----------|--------------|-----------|
| Transacción única | `PARCIAL` | Sí, todo el patch en una transacción SQLite |
| Versionado | `FALTANTE` | `expected_version` para optimistic locking |
| Validación previa | `FALTANTE` | Verificar nodes/edges existen antes de crear edges |
| Referencias client_id | `FALTANTE` | Permitir referencias a nodos creados en el mismo patch |
| Rollback completo | `PARCIAL` | SQLite permite rollback si se maneja bien la sesión |
| Límite de operaciones | `FALTANTE` | Máximo 100-500 operaciones por patch |
| Idempotencia | `FALTANTE` | client_id + idempotency key |
| Dry-run | `FALTANTE` | Validar sin ejecutar |

### 8.2 Formato propuesto

```json
{
  "board_id": "abc123",
  "expected_version": 14,
  "idempotency_key": "uuid-v4",
  "dry_run": false,
  "operations": [
    {
      "op": "create_node",
      "client_id": "node-a",
      "node": {
        "type": "card",
        "title": "Nuevo nodo",
        "x": 100, "y": 200
      }
    },
    {
      "op": "update_node",
      "node_id": "existing-node-1",
      "changes": { "x": 300, "y": 400 }
    },
    {
      "op": "create_edge",
      "client_id": "edge-1",
      "source": "node-a",
      "target": "existing-node-1"
    },
    {
      "op": "delete_node",
      "node_id": "obsolete-node"
    }
  ]
}
```

### 8.3 Ejecución segura

```
1. BEGIN TRANSACTION
2. Verificar board existe y versión coincide
3. BLOQUEAR escritura (SELECT ... FOR UPDATE o version check)
4. FASE 1 — Validación (sin escribir):
   a. Resolver todas las referencias (client_id → real_id)
   b. Verificar que todos los recursos existen
   c. Validar límites (máx nodos, tamaño, etc.)
   d. Si dry_run → ROLLBACK + devolver resultado
5. FASE 2 — Ejecución:
   a. Incrementar version
   b. Ejecutar operaciones en orden
   c. Registrar en audit_log
6. COMMIT
7. Si error en cualquier paso → ROLLBACK
```

### 8.4 Interacción frontend + MCP (crítico)

```text
FRONTEND ABIERTO                MCP                           RESULTADO
─────────────────────────────────────────────────────────────────────
autosave (snapshot v5)
                                apply_board_patch (v5)
                                → crea nodo Z
                                → version = 6
autosave (snapshot sin nodo Z)
→ PUT /state con nodos v5      ⚠️ SOBREESCRIBE: nodo Z
  (sin incluir Z)                desaparece silenciosamente
```

**Solución:**
1. El frontend **nunca** debe usar `PUT /state` si MCP está activo
2. El frontend debe migrar a patches incrementales o al menos verificar `version` antes de guardar
3. Si version mismatch → recargar board desde servidor + notificar conflicto
4. Alternativa inicial: que MCP solo opere en boards marcados como "managed by MCP"

---

## 9. Recursos MCP

### 9.1 Propuesta

| URI | Datos | Acceso | Tamaño esperado | MVP |
|-----|-------|--------|-----------------|-----|
| `huginn://studios` | Lista de studios del usuario | `studios:read` | < 10 KB | ✅ |
| `huginn://studios/{id}` | Studio individual | `studios:read` | < 1 KB | ✅ |
| `huginn://folders/{id}` | Folder con boards | `folders:read` | < 5 KB | ✅ |
| `huginn://boards/{id}` | Estado completo (nodes + edges) | `boards:read` | 1 KB – 1 MB | ✅ |
| `huginn://boards/{id}/summary` | Nombre, fechas, counts | `boards:read` | < 1 KB | ✅ |
| `huginn://boards/{id}/nodes` | Solo nodos del board | `nodes:read` | 1 KB – 500 KB | ✅ |

**Excluir del recurso:**
- Contenido de imágenes base64 (puede ser enorme) — reemplazar por metadata + tamaño
- Datos de otros usuarios (validación por token)

**Riesgo:** boards con muchas imágenes base64 pueden producir recursos de varios MB. Establecer límite de 5 MB por recurso.

**Recomendación:** Usar **tools** en lugar de resources para la primera versión. Los resources MCP tienen semántica de suscripción que no aporta valor aquí y añade complejidad.

---

## 10. Prompts MCP

Los prompts MCP tendrían sentido para guiar a agentes sobre cómo usar las herramientas, pero la lógica de negocio debe residir en herramientas, no en prompts.

| Prompt | Utilidad | ¿Debe implementarse en backend? |
|--------|----------|--------------------------------|
| Crear mapa conceptual | Guía para agente sobre cómo combinar herramientas | NO — es instrucción + combinación de tools |
| Generar timeline | Guía para agente | NO |
| Organizar un board | Guía + llamada a `layout_board` | PARCIAL — `layout_board` sí es herramienta |
| Resumir un board | Guía para agente | NO |

**Recomendación:** Implementar solo las herramientas subyacentes. Los prompts pueden definirse en la documentación MCP o en el cliente, no en el servidor.

---

## 11. Layouts y posicionamiento

### 11.1 Estado actual

**NO EXISTE ningún algoritmo de layout.** Los nodos se posicionan donde el usuario los coloca manualmente.

### 11.2 Lo que se necesitaría

| Algoritmo | Dónde implementar | Dependencia | Prioridad |
|-----------|-------------------|-------------|-----------|
| Grid layout | Backend (servicio) | Ninguna | MVP (básico) |
| Tree layout | Backend | Algoritmo propio | Fase 3 |
| Timeline layout | Backend | Algoritmo propio | Fase 3 |
| Radial layout | Backend | Algoritmo propio | Fase 3 |
| Force-directed | Backend | Librería externa | Fase 4 |

**Grid layout básico** se puede implementar sin dependencias: ordenar nodos por conexiones y ubicarlos en filas/columnas con spacing configurable.

**Recomendación:** Grid layout en Fase 0/1, algoritmos más complejos en fases posteriores.

---

## 12. Integración con FastAPI

### 12.1 Opciones comparadas

#### Opción A (RECOMENDADA): MCP montado dentro de FastAPI

```
/api/auth/*                          ← endpoints actuales
/api/studios/*, /api/boards/*, ...   ← endpoints actuales
/mcp                                 ← servidor MCP (Streamable HTTP)
```

| Aspecto | Evaluación |
|---------|------------|
| Ventajas | Mismo proceso, mismo puerto, misma autenticación (token), misma sesión DB, mismo lifecycle, mismo despliegue |
| Desventajas | Riesgo de que una herramienta MCP bloqueé el event loop (usar `run_in_executor`) |
| Complejidad | Baja — usar `FastMCP` con mount |
| Autenticación | Middleware Starlette que verifica `Authorization: Bearer <token>` |
| Despliegue | Sin cambios — Railway sigue sirviendo un solo contenedor |
| Riesgos con SQLite | Mínimos — misma DB, misma conexión pool |

#### Opción B: Servidor separado mismo contenedor

| Aspecto | Evaluación |
|---------|------------|
| Ventajas | Aislamiento de carga |
| Desventajas | Dos procesos compitiendo por SQLite, más memoria, más complejidad de despliegue |
| Recomendación | **No recomendada** mientras SQLite sea el motor |

#### Opción C: Servicio independiente en Railway

| Aspecto | Evaluación |
|---------|------------|
| Ventajas | Escalamiento independiente |
| Desventajas | Dos servicios Railway = dos facturas. Acceso compartido a SQLite imposible (archivo único). Requeriría migrar a Postgres. |
| Recomendación | **No recomendada** — rompe la arquitectura de un solo archivo SQLite |

### 12.2 Configuración para Streamable HTTP

```python
# mcp/server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Huginn MCP Server",
    description="MCP server for Huginn Nodeboard",
)

# En main.py:
from app.mcp.server import mcp
app.mount("/mcp", mcp.sse_app())  # o Streamable HTTP
```

**O con FastMCP directamente:**
```python
# El SDK MCP soporta montaje en ASGI/Starlette
from starlette.routing import Mount
app.add_route("/mcp", mcp_app)
```

### 12.3 Consideraciones técnicas

| Elemento | Detalle |
|----------|---------|
| SDK MCP | `mcp[cli] >= 1.0.0` (SDK oficial Python) |
| Transporte | Streamable HTTP (recomendado para remoto) o SSE |
| Sesiones DB | Reutilizar `get_db` de FastAPI |
| Timeouts | 60s por defecto, configurable |
| Healthcheck | MCP tiene su propio health o se reusa `/api/health` |
| Railway | Sin cambios de infraestructura |
| Catch-all conflict | `/mcp` NUNCA debe caer en el catch-all SPA — registrarlo antes del bloque de static |

---

## 13. Seguridad

### 13.1 Matriz de riesgos

| Riesgo | Tipo | Severidad | Descripción | Mitigación MVP |
|--------|------|-----------|-------------|----------------|
| Frontend sobrescribe cambios MCP | Concurrencia | **CRÍTICO** | Autosave por snapshot destruye cambios de agentes | Versionado + frontend verifica versión |
| IDOR (acceso a datos de otro usuario) | Autorización | **ALTO** | Sin validación de ownership, un token podría acceder a recursos ajenos | `_get_board` etc. verifican ownership; replicar en MCP |
| Token filtrado | Confidencialidad | **ALTO** | Token en logs, HTTP, o repos | Hash en DB, mostrar una vez, HTTPS siempre |
| Borrado accidental | Integridad | **ALTO** | `delete_board` o `delete_node` sin confirmación | Scopes separados, confirmación en tools destructivas (dry-run) |
| Payload enorme | Disponibilidad | **MEDIO** | Board con 10,000 nodos o imágenes base64 gigantes | Límite de 500 nodos por operación, 5 MB por payload |
| DoS por operaciones batch | Disponibilidad | **ALTO** | 10,000 operaciones en un solo patch | Límite de 100 operaciones por patch, rate limiting |
| Prompt injection almacenada | Integridad | **MEDIO** | Nodo con contenido malicioso que el agente ejecuta | Documentar riesgo, no ejecutar contenido de nodos como instrucciones |
| SQL injection | Integridad | **BAJO** | SQLAlchemy escapa parámetros | No concatenar strings SQL |
| Logs con secretos | Confidencialidad | **ALTO** | Token en logs de auditoría | No loguear tokens, solo hash parcial |
| Rate limiting | Disponibilidad | **FALTANTE** | No existe limitación actual | Añadir middleware de rate limiting |

### 13.2 Límites concretos propuestos

| Límite | Valor | Justificación |
|--------|-------|---------------|
| Máximo nodos por board | 1,000 | Rendimiento en SQLite + canvas |
| Máximo edges por board | 2,000 | Relación 2:1 edge:node típica |
| Máximo operaciones por patch | 100 | Evitar timeouts SQLite |
| Máximo tamaño payload | 5 MB | Imágenes base64 incluidas |
| Máximo longitud texto en nodo | 50,000 caracteres | Prevenir abuse |
| Máximo tags por nodo | 50 | UI y rendimiento |
| Rate limit (por token) | 60 requests/min | Uso personal |
| Token expiration | 90 días (default) | Balance seguridad/experiencia |
| Confirmación destructiva | `delete_*` requiere confirmación explícita | Evitar pérdida accidental |

### 13.3 Diferenciación de riesgos

| Tipo | Presente en API normal | Introducido por MCP |
|------|----------------------|---------------------|
| IDOR | Parcial (validado en cada ruta) | Mismo riesgo, misma mitigación |
| Borrado accidental | Sí (un click) | Mayor (agente autónomo) |
| Payload enorme | Sí (POST/body size) | Mayor (batch operations) |
| Concurrencia | Bajo (solo frontend) | **Crítico** (frontend + agentes) |
| Token leak | No (session cookie) | **Nuevo** (Bearer token) |
| Prompt injection | No aplica | **Nuevo** (agente ejecuta tools basado en contenido) |

---

## 14. Auditoría y trazabilidad

### 14.1 Estado actual

**NO EXISTE logging de operaciones.** Solo hay logging de startup de base de datos en `database.py`.

### 14.2 Tabla propuesta

```sql
mcp_audit_log
├── id              String(32) PK
├── user_id         String(32) FK → users.id
├── token_id        String(32) FK → mcp_tokens.id   (nullable)
├── client_name     String(200)                      (opcional, auto-reportado)
├── tool_name       String(100)                      -- "create_node", etc.
├── resource_type   String(50)                       -- "board", "node", "edge"
├── resource_id     String(64)                       (nullable)
├── request_id      String(64)                       -- correlation ID
├── idempotency_key String(64)                       (nullable)
├── summary         String(500)                      -- "Created node 'foo' at (100, 200)"
├── status          String(20)                       -- "success", "error", "rejected"
├── error_message   String(500)                      (nullable)
├── affected_count  Integer                          -- cuántos objetos
├── duration_ms     Integer
├── created_at      DateTime
└── ip_address      String(45)                       (opcional, propósito de rate limiting)
```

**Qué NO registrar:**
- Tokens completos ni parciales
- Contenido completo de nodos (solo summary descriptivo)
- Secretos de autenticación

**Qué registrar:**
- `summary`: "Created node 'Nuevo concepto' (card) at (100, 200) in board 'Mi Tablero'"
- `error_message`: "Node ID 'abc123' not found in board 'xyz'"
- `duration_ms`: para monitoreo de rendimiento

### 14.3 Correlation ID

Cada request MCP debe tener un `X-Request-ID` (generado por el servidor si el cliente no lo envía). Este ID debe propagarse a:
- Logs de aplicación
- Log de auditoría
- Respuestas HTTP (header)
- Errores reportados al cliente

---

## 15. Dependencias

### 15.1 Dependencias actuales

| Dependencia | Versión | Uso actual |
|-------------|---------|------------|
| fastapi | >=0.110 | Framework web |
| uvicorn | >=0.29 | Servidor ASGI |
| sqlalchemy | >=2.0 | ORM |
| pydantic | >=2.6 | Validación |
| alembic | >=1.13 | Migraciones |
| google-auth | >=2.29 | OAuth Google |
| requests | >=2.31 | HTTP para Google OAuth |
| python-dotenv | >=1.0 | Variables de entorno |
| pytest | >=8.0 | Testing |
| httpx | >=0.27 | Testing (cliente HTTP async) |

### 15.2 Dependencias MCP propuestas

| Dependencia | Uso | Necesaria | Alternativa | Riesgo |
|-------------|-----|-----------|-------------|--------|
| `mcp[cli] >= 1.0` | SDK oficial MCP para Python | **SÍ** | Ninguna | Bajo — SDK oficial mantenido por Anthropic |
| `httpx >= 0.27` | Ya existe — HTTP async | **SÍ** (ya presente) | — | Bajo |
| `slowapi >= 0.1` | Rate limiting | **RECOMENDADA** | Propio middleware | Bajo — librería madura |
| `pytest-asyncio` | Testing async MCP | **RECOMENDADA** | Ninguna | Bajo |
| `passlib` | Hashing de tokens | **ALTERNATIVA** | `hashlib` nativo | Bajo — `hashlib` es suficiente para SHA-256 |

**Total dependencias nuevas mínimas:** 1 (`mcp`)

---

## 16. Testing

### 16.1 Tests existentes

| Archivo | Tipo | Cobertura |
|---------|------|-----------|
| `tests/test_api.py` | Contrato | Rutas existen, schema validation, catch-all ordering |
| `tests/test_tags_label.py` | E2E | Tags/label roundtrip, propagación |
| `tests/test_multi_user.py` | Aislamiento | Usuario A no accede a recursos de B |
| `tests/test_database.py` | Unitario | Path resolution, producción validación |

**Cobertura actual:** Buena para el tamaño del proyecto. Tests de aislamiento multi-usuario son excelentes.

### 16.2 Tests nuevos necesarios para MCP

#### Unitarios
| Test | Prioridad |
|------|-----------|
| Validación de scopes | **CRÍTICA** |
| Hashing y verificación de tokens | **CRÍTICA** |
| Autorización por usuario en MCP | **CRÍTICA** |
| Herramientas de lectura (list_studios, get_board, etc.) | **ALTA** |
| Herramientas de escritura (create_node, etc.) | **ALTA** |
| Operaciones por lote (batch create) | **ALTA** |
| Rollback en error de patch | **ALTA** |
| Dry-run devuelve resultados sin persistir | **ALTA** |
| Version conflict rejection | **ALTA** |
| Límites (payload size, max operations) | **MEDIA** |

#### Integración
| Test | Prioridad |
|------|-----------|
| Cliente MCP real (con SDK) | **ALTA** |
| Conexión Streamable HTTP | **ALTA** |
| Autenticación (token válido/ inválido/ expirado/ revocado) | **CRÍTICA** |
| `tools/list` devuelve herramientas correctas por scope | **ALTA** |
| Ejecución de tool | **ALTA** |
| Error estructurado MCP | **MEDIA** |
| Acceso cruzado entre usuarios (IDOR) | **CRÍTICA** |
| Railway-like environment (DATA_PATH, PORT) | **MEDIA** |

#### Seguridad
| Test | Prioridad |
|------|-----------|
| IDOR en todas las herramientas de escritura | **CRÍTICA** |
| Payload oversized rechazado | **ALTA** |
| Operations limit excedido | **ALTA** |
| Malformed patch rechazado | **ALTA** |
| Acción destructiva sin scope | **ALTA** |
| Token revocado rechazado | **ALTA** |

---

## 17. Compatibilidad por cliente

### 17.1 Claude Desktop / Claude Code

| Aspecto | Detalle |
|---------|---------|
| Transporte | Streamable HTTP (recomendado) o SSE |
| Autenticación | `Authorization: Bearer <token>` vía headers personalizados |
| Configuración esperada | `claude_desktop_config.json` con `"mcpServers"` apuntando a URL pública del servidor |
| Restricciones | Claude Code requiere conexión HTTPS. Para desarrollo local, `ngrok` o similar. |

### 17.2 OpenAI Agents SDK

| Aspecto | Detalle |
|---------|---------|
| Transporte | Streamable HTTP (compatible) |
| Headers | `Authorization`, `OpenAI-Beta: tools=v1` |
| Compatibilidad | OpenAI Agents SDK soporta MCP remoto desde versiones recientes |

### 17.3 ChatGPT

| Aspecto | Detalle |
|---------|---------|
| **NOTA** | ChatGPT actualmente no soporta MCP remoto de forma nativa. El soporte está en desarrollo por OpenAI. |
| Alternativa | Usar OpenAI Agents SDK como intermediario o esperar soporte oficial. |

### 17.4 OpenClaw

| Aspecto | Detalle |
|---------|---------|
| Registro | MCP estándar — configurar URL del servidor |
| Autenticación | Headers `Authorization` |
| Prueba | `tools/list` y ejecución de herramientas individuales |

---

## 18. Integración con Railway

### 18.1 Estado actual en Railway

```
Railway Service (1 réplica)
  └── Contenedor Docker (python:3.12-slim)
       ├── uvicorn app.main:app (port ${PORT:-8001})
       ├── SQLite: /data/nodeboard.db (con DATA_PATH=/data)
       └── static/ (frontend build)
```

### 18.2 Con MCP

```
Railway Service (1 réplica, sin cambios de infraestructura)
  └── Contenedor Docker
       ├── uvicorn app.main:app
       │    ├── /api/*          ← FastAPI routes
       │    └── /mcp            ← MCP server (Streamable HTTP)
       ├── SQLite: /data/nodeboard.db
       └── static/
```

### 18.3 Cambios necesarios

| Elemento | Cambio | Prioridad |
|----------|--------|-----------|
| `railway.toml` | Crear con healthcheck y volumen | **RECOMENDADO** (actualmente no existe) |
| `DATA_PATH` | Asegurar que está configurado en Railway | **CRÍTICO** (ver RAILWAY_DATA_LOSS_AUDIT.md) |
| Puerto | Sin cambios — MCP comparte el mismo puerto | ✅ |
| Volumen persistente | Railway Volume montado en `/data` | **CRÍTICO** |
| Healthcheck | Usar `/api/health` existente | ✅ |
| HTTPS | Railway lo maneja automáticamente | ✅ |

### 18.4 Railway.toml propuesto

```toml
[build]
builder = "nixpacks"
buildCommand = ""

[deploy]
startCommand = "/app/entrypoint.sh"
healthcheckPath = "/api/health"
healthcheckTimeout = 10

[[volumes]]
mountPath = "/data"
```

---

## 19. Plan de implementación por fases

### Fase 0 — Refactor previo (1–2 semanas)

**Objetivo:** Preparar el código base para soportar MCP sin cambiar comportamiento existente.

| Tarea | Archivos afectados | Esfuerzo |
|-------|-------------------|----------|
| Extraer servicios de `main.py` | `main.py` → `services/*.py` | 3-4 días |
| Centralizar verificación de autorización | `services/auth.py` | 1 día |
| Agregar campo `version` a Board | `models.py`, migración Alembic | 1 día |
| Agregar optimistic locking | `services/boards.py` | 1 día |
| Migrar `save_board_state` a usar versión | `services/boards.py`, `api.ts` | 2 días |
| Configurar WAL mode en SQLite | `database.py` | 0.5 día |
| Crear `railway.toml` | Raíz del proyecto | 0.5 día |
| Tests de servicios | `tests/test_services.py` | 2 días |

**Criterio de aceptación:** Todos los tests existentes pasan. Los servicios existen y son llamados desde rutas. Board tiene versión. El autosave verifica versión.

### Fase 1 — MCP de solo lectura (1 semana)

**Objetivo:** Exponer herramientas de consulta sin riesgo de escritura concurrente.

| Tarea | Archivos afectados | Esfuerzo |
|-------|-------------------|----------|
| Crear tabla `mcp_tokens` | `models.py`, migración Alembic | 1 día |
| Crear endpoints de gestión de tokens | `main.py` o `routes/auth.py` | 1 día |
| Implementar middleware de token MCP | `mcp/auth.py` | 1 día |
| Montar servidor MCP básico | `mcp/server.py`, `main.py` | 1 día |
| Implementar tools de lectura | `mcp/tools/*.py` | 1 día |
| Tests (tokens, lectura, IDOR) | `tests/test_mcp.py` | 1 día |

**Herramientas:** `list_studios`, `list_folders`, `list_boards`, `get_board`, `get_board_summary`, `get_node`

**Criterio de aceptación:** Token se crea, se muestra una vez, se verifica por hash. Tools de lectura devuelven datos correctos. IDOR tests pasan.

### Fase 2 — Escritura limitada (1–2 semanas)

**Objetivo:** Exponer herramientas de escritura con límites seguros.

| Tarea | Archivos afectados | Esfuerzo |
|-------|-------------------|----------|
| Implementar `create_board` tool | `mcp/tools/boards.py` | 0.5 día |
| Implementar `create_node`, `update_node`, `move_node` tools | `mcp/tools/nodes.py` | 1 día |
| Implementar `create_nodes_batch` | `mcp/tools/nodes.py` | 1 día |
| Implementar `create_edges_batch` | `mcp/tools/edges.py` | 1 día |
| Implementar auditoría MCP | `mcp/audit.py` | 1 día |
| Rate limiting | Middleware | 1 día |
| Tests de escritura | `tests/test_mcp.py` | 1 día |

**Scopes necesarios:** `boards:create`, `nodes:create`, `nodes:update`, `edges:create`

**Criterio de aceptación:** Creación de boards, nodos y edges funciona desde MCP. Auditoría registra cada operación. Rate limiting activo.

### Fase 3 — Patches transaccionales (2 semanas)

**Objetivo:** Implementar `apply_board_patch` con versionado y detección de conflictos.

| Tarea | Archivos afectados | Esfuerzo |
|-------|-------------------|----------|
| Implementar `apply_board_patch` con transacción | `mcp/tools/patch.py`, `services/board_patches.py` | 3-4 días |
| Idempotency keys | `mcp/tools/patch.py` | 1 día |
| Dry-run | `mcp/tools/patch.py` | 1 día |
| Detección y reporte de conflictos | `services/board_patches.py` | 1 día |
| Actualizar frontend para manejar conflictos | `src/api.ts`, `NodeBoard.tsx` | 2-3 días |
| Notificación de conflictos en UI | Componentes frontend | 1 día |
| Tests de patches | `tests/test_mcp.py` | 2 días |

**Criterio de aceptación:** `apply_board_patch` ejecuta transaccionalmente. Conflictos se detectan y reportan. Idempotency previene duplicados.

### Fase 4 — Layout y operaciones avanzadas (2–3 semanas)

**Objetivo:** Algoritmos de layout y herramientas de alto nivel.

| Tarea | Esfuerzo |
|-------|----------|
| Grid layout algorithm | 2 días |
| Timeline layout algorithm | 2 días |
| `layout_board` tool | 1 día |
| `create_board_from_outline` tool | 3 días |
| `duplicate_board` tool | 1 día |
| `export_board` tool (JSON/Markdown) | 1 día |
| Tests de layout | 2 días |

### Fase 5 — Endurecimiento y uso externo (1 semana)

**Objetivo:** Preparar para producción con agentes reales.

| Tarea | Esfuerzo |
|-------|----------|
| Panel de integraciones en UI | 2 días |
| Rotación de tokens | 1 día |
| Documentación MCP (tools, scopes, auth) | 1 día |
| Monitoreo y alertas | 1 día |
| Pruebas con Claude Desktop | 1 día |
| Pruebas con OpenAI Agents SDK | 1 día |
| Pruebas con OpenClaw | 1 día |

---

## 20. Archivos que probablemente habría que modificar

### Modificar

| Archivo | Cambio |
|---------|--------|
| `nodeboard-backend/app/main.py` | Extraer lógica a servicios, montar MCP, registrar rutas de tokens |
| `nodeboard-backend/app/models.py` | Agregar `mcp_tokens`, agregar `version` a Board, agregar `mcp_audit_log` |
| `nodeboard-backend/app/schemas.py` | Agregar schemas para tokens, audit log, patches, versión |
| `nodeboard-backend/app/auth.py` | Agregar manejo de tokens MCP |
| `nodeboard-backend/app/database.py` | Configurar WAL mode |
| `nodeboard-backend/requirements.txt` | Agregar `mcp[cli]`, posiblemente `slowapi` |
| `src/api.ts` | Actualizar autosave para verificar versión |
| `src/NodeBoard.tsx` | Manejar conflictos de versión, recargar UI |
| `Dockerfile` | Sin cambios (montaje dentro del mismo proceso) |

### Crear

| Archivo | Propósito |
|---------|-----------|
| `nodeboard-backend/app/services/__init__.py` | Paquete de servicios |
| `nodeboard-backend/app/services/studios.py` | Lógica de Studios |
| `nodeboard-backend/app/services/folders.py` | Lógica de Folders |
| `nodeboard-backend/app/services/boards.py` | Lógica de Boards (con versionado) |
| `nodeboard-backend/app/services/nodes.py` | Lógica de Nodes |
| `nodeboard-backend/app/services/edges.py` | Lógica de Edges |
| `nodeboard-backend/app/services/auth.py` | Token management, scope verification |
| `nodeboard-backend/app/mcp/__init__.py` | Paquete MCP |
| `nodeboard-backend/app/mcp/server.py` | Servidor MCP |
| `nodeboard-backend/app/mcp/auth.py` | Token validation middleware |
| `nodeboard-backend/app/mcp/context.py` | User/context resolution |
| `nodeboard-backend/app/mcp/tools/__init__.py` | Paquete de tools |
| `nodeboard-backend/app/mcp/tools/studios.py` | Tools de studios |
| `nodeboard-backend/app/mcp/tools/boards.py` | Tools de boards |
| `nodeboard-backend/app/mcp/tools/nodes.py` | Tools de nodes |
| `nodeboard-backend/app/mcp/tools/edges.py` | Tools de edges |
| `nodeboard-backend/app/mcp/tools/patch.py` | Apply board patch |
| `nodeboard-backend/app/mcp/audit.py` | Auditoría logger |
| `nodeboard-backend/tests/test_services.py` | Tests de servicios |
| `nodeboard-backend/tests/test_mcp.py` | Tests de MCP |
| `railway.toml` | Configuración Railway declarativa |

---

## 21. Migraciones de base de datos probables

# migración 1 — versionado de boards
ALTER TABLE boards ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

# migración 2 — tokens MCP
CREATE TABLE mcp_tokens (
    id VARCHAR(32) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    scopes JSON NOT NULL DEFAULT '[]',
    constraints JSON,
    created_at DATETIME NOT NULL,
    last_used_at DATETIME,
    expires_at DATETIME,
    revoked_at DATETIME
);
CREATE INDEX ix_mcp_tokens_user_id ON mcp_tokens(user_id);
CREATE INDEX ix_mcp_tokens_token_hash ON mcp_tokens(token_hash);

# migración 3 — auditoría MCP
CREATE TABLE mcp_audit_log (
    id VARCHAR(32) PRIMARY KEY,
    user_id VARCHAR(32) REFERENCES users(id),
    token_id VARCHAR(32) REFERENCES mcp_tokens(id),
    client_name VARCHAR(200),
    tool_name VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(64),
    request_id VARCHAR(64),
    idempotency_key VARCHAR(64),
    summary VARCHAR(500),
    status VARCHAR(20) NOT NULL,
    error_message VARCHAR(500),
    affected_count INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    ip_address VARCHAR(45),
    created_at DATETIME NOT NULL
);
CREATE INDEX ix_mcp_audit_log_created_at ON mcp_audit_log(created_at);
CREATE INDEX ix_mcp_audit_log_user_id ON mcp_audit_log(user_id);
CREATE INDEX ix_mcp_audit_log_request_id ON mcp_audit_log(request_id);

---

## 22. Riesgos críticos (ordenados)

| # | Riesgo | Severidad | ¿Por qué? | Mitigación necesaria antes de MCP |
|---|--------|-----------|-----------|-----------------------------------|
| 1 | Frontend sobrescribe cambios MCP | **CRÍTICO** | Autosave envía snapshot completo sin versionado | Versionado + frontend verifica versión |
| 2 | Sin capa de servicios | **ALTO** | Lógica duplicada entre rutas y MCP, difícil de testear | Refactor Fase 0 |
| 3 | Sin autenticación para MCP | **ALTO** | Cookies no funcionan para clientes no-browser | Tabla mcp_tokens + Bearer auth |
| 4 | Sin control de concurrencia | **ALTO** | Last-writer-wins entre frontend y MCP | Versionado + optimistic locking |
| 5 | Sin límites en operaciones | **MEDIO** | Batch operations pueden saturar SQLite | Rate limiting + límites de payload |

---

## 23. Criterios de aceptación para el MVP MCP

| Criterio | Descripción |
|----------|-------------|
| **✅** | Servicios extraídos y testeables independientemente de HTTP |
| **✅** | Board tiene `version` y se incrementa en cada cambio |
| **✅** | Token MCP se crea, se muestra una vez, se almacena hasheado |
| **✅** | Token expira, se revoca, tiene scopes |
| **✅** | Tools de solo lectura funcionan (list, get) |
| **✅** | Tools de batch creation funcionan en transacción |
| **✅** | Frontend no sobrescribe cambios MCP |
| **✅** | Conflicto de versión genera error en lugar de sobrescritura silenciosa |
| **✅** | Cada operación MCP queda registrada en audit_log |
| **✅** | Rate limiting activo |
| **✅** | Railway despliega sin cambios de infraestructura |
| **✅** | Tests de seguridad (IDOR, payload, scopes) pasan |

---

## 24. Recomendación final

**No comenzar directamente con MCP.** El orden correcto es:

```
Fase 0 (Refactor) → Fase 1 (Solo lectura) → Fase 2 (Escritura limitada)
```

### Por qué no saltar a MCP directamente

1. **El autosave actual rompería cualquier cambio MCP** silenciosamente sin versionado. Este es un problema de diseño, no de configuración.
2. **Las rutas actuales no son reutilizables** porque mezclan lógica HTTP con lógica de negocio. Cualquier tool MCP terminaría duplicando la lógica de `main.py`.
3. **No hay un mecanismo de autenticación para MCP.** Implementar tokens sin refactor previo agregaría más deuda técnica.
4. **Los tests existentes prueban rutas, no lógica de negocio.** Sin servicios, no hay forma de testear las tools MCP en aislamiento.

### MVP recomendado (Fases 0 + 1)

Alcance: servidor MCP de solo lectura montado en el mismo proceso FastAPI, con autenticación por token Bearer.

Herramientas:

| Herramienta | Scope |
|-------------|-------|
| `list_studios` | `studios:read` |
| `list_folders` | `folders:read` |
| `list_boards` | `boards:read` |
| `get_board` | `boards:read` |
| `get_board_summary` | `boards:read` |
| `get_node` | `nodes:read` |

Sin escritura hasta que:
- Board tenga versionado
- Frontend verifique versión antes de autosave
- Servicio de `apply_board_patch` esté implementado con transacciones

### Tiempo estimado

| Fase | Duración | Resultado |
|------|----------|-----------|
| Fase 0 — Refactor | 1-2 semanas | Servicios, versionado, WAL |
| Fase 1 — Solo lectura MCP | 1 semana | Tokens, tools de lectura, auditoría |
| Fase 2 — Escritura limitada | 1-2 semanas | Batch create, límites |
| Fase 3 — Patches | 2 semanas | apply_board_patch, conflictos |
| Fase 4 — Layout avanzado | 2-3 semanas | Algoritmos, tools de alto nivel |
| Fase 5 — Endurecimiento | 1 semana | Panel, docs, pruebas externas |

**Total estimado:** 8-11 semanas para MCP completo con herramientas de escritura. 2-3 semanas para MVP de solo lectura.
