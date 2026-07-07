# Huginn Nodeboard — Vault de arquitectura

Documentación arquitectural del canvas de nodos **Huginn**: frontend Vite + React + TypeScript, backend FastAPI + SQLAlchemy + SQLite (`nodeboard-backend/`).

**Estado actual:** Frontend completo y tipado (post Fase 0, sin `@ts-nocheck`, modularizado). Backend completo con persistencia y autosave. Suite de tests: unit (vitest sobre `geometry`), API (pytest) y e2e (Playwright, 6 specs / 12 tests en verde).

**Fase 1 — modelo de datos real:**
- ✅ **Paso 1 (`models.py`)**: `tags` (JSON) agregado a `nodes`, `label` (texto) agregado a `edges`; `nodeboard.db` migrado vía `ALTER TABLE` sin pérdida de datos.
- ✅ **Paso 2 (`schemas.py`)**: `tags`/`label` reflejados; `ports`/`blocks`/`stages` migrados de `dict[str, Any]` a tipos reales con discriminador por `type`. Tests de backend en verde; datos reales conforman al tipado estricto.
- ✅ **Paso 3 (`main.py`)**: exponer/aceptar `tags` y `label` en endpoints.
- ✅ **Paso 4 (frontend `types.ts`/`api.ts`)**: reflejar los campos nuevos.

**Fase 2 — interacciones avanzadas:**
- ✅ **Tags modal**: menú contextual del nodo → modal para añadir/quitar tags; persistido vía autosave.
- ✅ **Copy/paste de nodo** (Ctrl+C / Ctrl+V): copia datos a estado interno (no OS clipboard); pega con offset +20px acumulado; sin edges; persiste vía autosave.
- ✅ **Multi-selección de nodos** (shift+click / ctrl+click): `selectedNodeIds: string[]` reemplaza el antiguo `selection.type === "node"`; click simple reemplaza la selección; click con modificador la alterna; click en canvas la vacía; `Selection` eliminado de `canvas-types.ts`.
- ✅ **Copy/paste multi-nodo**: Ctrl+C con N nodos seleccionados copia el array completo; Ctrl+V pega todos con el mismo delta acumulado (+20,+20 por paste), preservando posiciones relativas; sin edges entre las copias; grupo pegado queda seleccionado.
- ✅ **Arrastre de grupo**: plain mousedown sobre un nodo de multi-selección inicia group drag; todos los nodos seleccionados se mueven con el mismo delta calculado desde la posición inicial (no acumulado); plain click sin arrastrar reemplaza selección al nodo clickeado; shift/ctrl+click siempre usa path individual.
- ✅ **Filtro visual por tags**: panel fijo en canvas (top-right) con checkboxes de tags únicos del board, selector Amplio/Estricto; atenúa a 75% los nodos no coincidentes; no oculta ni afecta interacción. Tests: 11 unitarios. [[Flujos/Flujo - Filtro Visual por Tags.md]]

**Fase 3 — Studios y Carpetas:**
- ✅ **Modelos**: `Studio` (id, nombre, color enum de 6 valores), `Folder` (id, nombre, FK a Studio), `Board` extendido con `studio_id` (FK obligatoria) y `folder_id` (FK opcional).
- ✅ **Endpoints**: `POST /api/studios`, `GET /api/studios`, `POST /api/folders`, `GET /api/studios/{id}/folders`, `GET /api/studios/{id}/boards` (separa root de folder boards), `GET /api/folders/{id}/boards`.
- ✅ **Validaciones**: color de Studio contra enum cerrado, existencia de Studio/Folder, consistencia studio_id ↔ folder_id.
- ✅ **Frontend**: Home con grilla de Studios y modal de creación, StudioView con recientes y carpetas, FolderView con boards de carpeta, navegación jerárquica completa, botón atrás desde canvas respeta la jerarquía real.
- ✅ **Tests**: 6 tests e2e de navegación nuevos + 12 tests backend de Studios/Folders. Suite completa: 29 backend + 7 vitest + 18 e2e = 54 tests en verde.

**Etapa 3 — Migración a Railway:**
- ✅ **CORS por env**: `CORS_ORIGINS` variable de entorno (separado por comas) con fallback a localhost para desarrollo local. [[RESUMEN_ETAPA3.md]]
- ✅ **Frontend estático desde FastAPI**: montaje condicional de `StaticFiles` en `/assets` + catch-all `/{full_path:path}` que sirve `index.html` para SPA, registrado **después** de todos los endpoints `/api/*` (orden crítico documentado en comentario). [[RESUMEN_ETAPA3.md]]
- ✅ **Entrypoint script** (`nodeboard-backend/entrypoint.sh`): corre `alembic upgrade head` y arranca uvicorn con `exec` leyendo `$PORT` (fallback 8001).
- ✅ **Dockerfile multi-stage** (raíz del proyecto): builder node:22-alpine → `npm ci && npm run build`; final python:3.12-slim → pip install + copia build a `app/static/` + `mkdir -p /data` + build args `BUILD_COMMIT`/`BUILD_TIMESTAMP`/`VITE_GOOGLE_CLIENT_ID`. En Railway se setea `DATA_PATH=/data` y se monta un Volume en `/data`. [[RESUMEN_ETAPA3.md]]
- ✅ **Logout automático por 401**: `registerUnauthorizedHandler` en `api.ts` + registro de `logout` en `AuthProvider`. Cuando cualquier llamada HTTP recibe 401, `request()` dispara el handler antes del throw — `setUser(null)` → gate global en `AppInner` → muestra Login, sin recargar la página. [[RESUMEN_LOGOUT_AUTO.md]]
- ✅ **Tests de orden de rutas**: `test_catch_all_source_ordering` (parsea `main.py` y verifica que el catch-all sea el último decorador) + `test_catch_all_ordering_at_runtime` (recorre `app.routes` si el build de frontend existe). Suite: 35 backend (34 pass + 1 xfail), 18 vitest.
- ✅ **Documentación de ruteo**: [[PATHS_ETAPA3.md]] — inventario completo de los 25 endpoints HTTP. [[RESUMEN_ROUTING_ETAPA3.md]] — análisis de CORS, routers, StaticFiles, puerto y estructura. [[RESUMEN_ETAPA3.md]] — resumen de cambios. [[RESUMEN_LOGOUT_AUTO.md]] — patrón del callback de 401.

**Preparación Etapa 2 — Alembic:**
- ✅ **Alembic instalado e inicializado**: migraciones versionadas reemplazan `Base.metadata.create_all()`. Baseline generada con autogenerate, diff vacío verificado. Ejecución automática vía `alembic upgrade head` en el lifespan de FastAPI. Documentado en [[Archivos/nodeboard-backend/migrations/env.py.md]], [[Archivos/nodeboard-backend/alembic.ini.md]], y [[Archivos/nodeboard-backend/migrations/versions/e10b08b208d0_initial_schema.py.md]].

---

## Archivos por área

### Raíz del repo — configuración
- [[Archivos/package.json.md]] — scripts (`dev`, `build`, `test`, `test:api`), dependencias React/Vite/Tailwind
- [[Archivos/vite.config.ts.md]] — dev server :5174, proxy `/api` → :8001, config de vitest
- [[Archivos/playwright.config.ts.md]] — e2e serial (workers 1), levanta API + web, DB de test aislada
- [[Archivos/index.html.md]] — HTML raíz, monta `#root` y carga `src/main.tsx`
- [[Archivos/tsconfig.app.json.md]] — TS estricto, `react-jsx`, `noEmit`

### `src/` — Frontend (React + Vite)
- [[Archivos/src/main.tsx.md]] — **entrypoint + navegación**: monta `<App />` con 4 vistas (Home, Studio, Folder, Board) manejadas por estado
- [[Archivos/src/NodeBoard.tsx.md]] — **hub del canvas**: estado del canvas, zoom/pan/drag, selección, conexión de puertos, toolbar — ahora recibe `boardId` y `onBack` como props
- [[Archivos/src/types.ts.md]] — **fuente de verdad del dominio**: `Node` (card|timeline), `Edge`, `Port`, `Block`, `PORT_COLORS`, `StudioColor`, `Studio`, `Folder`, `BoardSummary`
- [[Archivos/src/api.ts.md]] — capa HTTP (`api`) + hook `useBoardPersistence` (ahora recibe `boardId` en vez de auto-crear)
- [[Archivos/src/styles.css.md]] — import de Tailwind + reset base
- [[Archivos/src/vite-env.d.ts.md]] — referencia de tipos de Vite

### `src/lib/` — Utilidades puras
- [[Archivos/src/lib/geometry.ts.md]] — `portPos` y `edgePath`: posición de puertos y path SVG de aristas
- [[Archivos/src/lib/geometry.test.ts.md]] — tests unitarios (vitest) de `geometry`
- [[Archivos/src/lib/canvas-types.ts.md]] — tipos de estado de interacción (`Pending`, `DragState`, `ColorMenu`, `PortPos`); `Selection` eliminado en Fase 2
- [[Archivos/src/lib/theme.ts.md]] — `THEMES` (dark/light) y la interfaz `Theme`
- [[Archivos/src/lib/id.ts.md]] — `uid()`: generador de IDs únicos del frontend

### `src/components/` — Componentes UI
- [[Archivos/src/components/Home.tsx.md]] — **grilla de Studios**: fetch real, estados carga/vacío/grid, modal de creación
- [[Archivos/src/components/StudioView.tsx.md]] — **vista de Studio**: boards recientes (máx 6), grid de carpetas, crear board/carpeta
- [[Archivos/src/components/FolderView.tsx.md]] — **vista de Carpeta**: boards de la carpeta, volver al Studio padre
- [[Archivos/src/components/CreateStudioModal.tsx.md]] — modal: nombre + 6 swatches de color (enum cerrado StudioColor)
- [[Archivos/src/components/CreateFolderModal.tsx.md]] — modal: solo nombre (sin color)
- [[Archivos/src/components/NodeCard.tsx.md]] — nodo dibujado: encabezado, menú añadir, puertos, contenido ← componente más complejo
- [[Archivos/src/components/Block.tsx.md]] — bloques de card: texto, número, tabla, imagen
- [[Archivos/src/components/Timeline.tsx.md]] — nodo timeline: etapas con tags editables
- [[Archivos/src/components/TagsModal.tsx.md]] — modal de tags: input + chips de sugerencias + filtro en vivo
- [[Archivos/src/components/MenuItem.tsx.md]] — ítem del menú "añadir" del nodo
- [[Archivos/src/components/MiniBtn.tsx.md]] — botón chico (controles de tabla)
- [[Archivos/src/components/ToolBtn.tsx.md]] — botón de la barra de herramientas
- [[Archivos/src/components/Sep.tsx.md]] — separador vertical de la toolbar

### `nodeboard-backend/app/` — Backend (FastAPI)
- [[Archivos/nodeboard-backend/app/main.py.md]] — **hub del backend**: todos los endpoints REST, traducción modelo↔schema de `Edge`
- [[Archivos/nodeboard-backend/app/models.py.md]] — modelos ORM: `Board`, `Node` (con `tags`), `Edge` (con `label`) ← fuente de verdad persistida
- [[Archivos/nodeboard-backend/app/schemas.py.md]] — schemas Pydantic del contrato de API
- [[Archivos/nodeboard-backend/app/database.py.md]] — engine SQLite, `SessionLocal`, `Base`, dependencia `get_db`
- [[Archivos/nodeboard-backend/app/__init__.py.md]] — marca `app` como paquete Python (vacío)

### `nodeboard-backend/` — Tests y deps del backend
- [[Archivos/nodeboard-backend/tests/test_api.py.md]] — pytest: salud, rutas y contrato de `BoardStateSave`
- [[Archivos/nodeboard-backend/tests/test_tags_label.py.md]] — pytest e2e: propagación de `tags` (Node) y `label` (Edge)
- [[Archivos/nodeboard-backend/requirements.txt.md]] — fastapi, uvicorn, sqlalchemy, pydantic, pytest, httpx, alembic
- [[Archivos/nodeboard-backend/pytest.ini.md]] — config pytest: fija rootdir y `pythonpath` para resolver `app` desde cualquier cwd
- [[Archivos/nodeboard-backend/alembic.ini.md]] — config de Alembic (URL vía `NODEBOARD_DB`)
- [[Archivos/nodeboard-backend/migrations/env.py.md]] — entorno Alembic: apunta a `Base.metadata` y lee `NODEBOARD_DB`
- [[Archivos/nodeboard-backend/migrations/versions/e10b08b208d0_initial_schema.py.md]] — baseline del esquema (creación de las 5 tablas)

### Raíz — Deploy
- `Dockerfile` — multi-stage: builder Node 22 + runtime Python 3.12-slim. Build args `BUILD_COMMIT`, `BUILD_TIMESTAMP`.
- `nodeboard-backend/entrypoint.sh` — `alembic upgrade head` + `exec uvicorn` en `$PORT`.
- `.github/workflows/ci.yml` — CI en GitHub Actions: build frontend → copia build a `static/` → `vitest` → `pytest --runxfail`. El flag `--runxfail` asegura que `test_catch_all_ordering_at_runtime` falle si el build de frontend no está presente.

### `e2e/` — Tests end-to-end (Playwright)
- [[Archivos/e2e/helpers.ts.md]] — helpers: `connectPorts`, `waitForBoardLoaded`, `openTagsModal`, `dragNodeBy`, `createCardNodeAndGetId`, **`setupStudioAndBoard`**, **`setupStudioFolderAndBoard`**
- [[Archivos/e2e/create-node.spec.ts.md]] — crear un nodo aumenta el conteo en uno
- [[Archivos/e2e/connect-edge.spec.ts.md]] — conectar dos puertos agrega una arista visible
- [[Archivos/e2e/persist.spec.ts.md]] — un nodo creado persiste tras recargar
- [[Archivos/e2e/copy-paste.spec.ts.md]] — Ctrl+C/V crea nodo con mismo contenido, sin edges, en posición offset acumulado
- [[Archivos/e2e/multi-select.spec.ts.md]] — shift/ctrl+click agrega/quita nodos; click simple reemplaza; canvas vacío deselecciona; arrastre de grupo
- [[Archivos/e2e/tags-modal.spec.ts.md]] — crear/persistir/sugerir/filtrar/quitar tags
- [[Archivos/e2e/navigation.spec.ts.md]] — **navegación Studios/Carpetas**: Home muestra Studios, crear Studio, Studio separa recientes/carpetas, Carpeta no muestra sección Carpetas, botón atrás jerárquico

---

## Flujos principales

- [[Flujos/Flujo - Carga y Autosave del Tablero.md]] — arranque: fetch inicial → estado → autosave con debounce vía PUT `/state`
- [[Flujos/Flujo - Creacion de Nodo.md]] — desde el botón/doble clic hasta el nodo persistido
- [[Flujos/Flujo - Conexion de Aristas.md]] — clic en puerto origen → clic en puerto destino → arista renderizada
- [[Flujos/Flujo - Edicion de Contenido de Nodo.md]] — bloques de card y etapas de timeline
- [[Flujos/Flujo - Interaccion del Canvas.md]] — zoom con rueda, pan, drag de nodos, selección y borrado
- [[Flujos/Flujo - Copy Paste de Nodo.md]] — Ctrl+C copia 1..N nodos a estado interno; Ctrl+V pega todos con offset acumulado, preservando posiciones relativas, sin edges
- [[Flujos/Flujo - Navegacion Studios y Carpetas.md]] — Home → Studio → Carpeta → Board → atrás jerárquico
- [[Flujos/Flujo - Filtro Visual por Tags.md]] — panel de filtro por tags: modo Amplio/Estricto, atenuación visual

---

## Deuda técnica

### CI/CD — GitHub Actions (pendiente)

El proyecto no tiene integración continua. No existe `.github/workflows/` ni ningún archivo de CI. Esto implica:

- **Sin verificación automática en PRs**: los tests (35 backend + 18 vitest + 18 e2e) y el typecheck (`tsc --noEmit`) solo se ejecutan localmente. No hay guardas para evitar merges con tests rotos.
- **Sin linting automatizado**: no hay jobs de ESLint, Prettier, ni validación de formato.
- **Sin build check**: nadie confirma que `npm run build` compile exitosamente hasta el deploy.
- **Sin Docker build test**: el `Dockerfile` multi-stage no se valida en ningún lado hasta el deploy a Railway.
- **Sin caché de dependencias**: cada build en Railway parte de cero sin capas cacheadas de `pip install` ni `npm ci`, alargando los deploys.

**Mínimo recomendado para un pipeline inicial:**

| Job | Trigger | Comandos | Tiempo estimado |
|-----|---------|----------|----------------|
| `lint-typecheck` | push a PR, push a main | `tsc --noEmit` | ~30s |
| `test-backend` | push a PR, push a main | `pytest nodeboard-backend/tests` | ~10s |
| `test-frontend` | push a PR, push a main | `vitest run` | ~5s |
| `build` | push a main (post-merge) | `npm run build` + validar Dockerfile build | ~2m |
| `deploy` | push a main (post-build) | Deploy automático a Railway via Railway CLI o GitHub integration | ~3m |

La dependencia de Railway para el deploy es el habilitador principal: una vez que Railway está conectado al repo, el job `build` puede producir la imagen y `deploy` solo necesita triggerear un nuevo deployment.

> **Decisión técnica**: el pipeline más valioso para arrancar es `test-backend + test-frontend + lint-typecheck` en PRs. El deploy automatizado suma valor pero no es bloqueante — Railway permite deploy manual desde su dashboard mientras tanto.

> Regla de trabajo: cada vez que se crea o modifica un archivo del proyecto, se debe actualizar (o crear) su nota correspondiente en `vault/Archivos/...`, incluyendo sus secciones de Exporta/Importa y las referencias cruzadas afectadas ("Importado por" en los archivos relacionados), antes de cerrar la tarea. El vault solo se actualiza ante orden explícita.

---

## Documentos de sesión (RESUMEN)

Estos documentos se generan por sesión de trabajo y no se mantienen en sincronía
con el código fuente — son instantáneas para revisión externa.

- [[RESUMEN_ROUTING_ETAPA3.md]] — inventario de ruteo antes de la Etapa 3 (CORS, routers, StaticFiles, puerto, estructura)
- [[PATHS_ETAPA3.md]] — lista completa de los 25 paths HTTP en main.py
- [[RESUMEN_ETAPA3.md]] — cambios realizados en la Etapa 3 (CORS por env, StaticFiles, catch-all, entrypoint.sh, Dockerfile)
- [[RESUMEN_LOGOUT_AUTO.md]] — logout automático por sesión expirada vía callback de 401
