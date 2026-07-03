# Huginn Nodeboard — Vault de arquitectura

Documentación arquitectural del canvas de nodos **Huginn**: frontend Vite + React + TypeScript, backend FastAPI + SQLAlchemy + SQLite (`nodeboard-backend/`).

**Estado actual:** Frontend completo y tipado (post Fase 0, sin `@ts-nocheck`, modularizado). Backend completo con persistencia y autosave. Suite de tests: unit (vitest sobre `geometry`), API (pytest) y e2e (Playwright).

**Fase 1 en curso — modelo de datos real** (ver guía `Downloads/Huginn_Fase1_Guia.md`):
- ✅ **Paso 1 (`models.py`)**: `tags` (JSON) agregado a `nodes`, `label` (texto) agregado a `edges`; `nodeboard.db` migrado vía `ALTER TABLE` sin pérdida de datos.
- ✅ **Paso 2 (`schemas.py`)**: `tags`/`label` reflejados; `ports`/`blocks`/`stages` migrados de `dict[str, Any]` a tipos reales con discriminador por `type`. Tests de backend en verde; datos reales conforman al tipado estricto.
- ⏳ **Paso 3 (`main.py`)**: exponer/aceptar `tags` y `label` en endpoints. Pendiente.
- ⏳ **Paso 4 (frontend `types.ts`/`api.ts`)**: reflejar los campos nuevos. Pendiente.

---

## Archivos por área

### Raíz del repo — configuración
- [[Archivos/package.json.md]] — scripts (`dev`, `build`, `test`, `test:api`), dependencias React/Vite/Tailwind
- [[Archivos/vite.config.ts.md]] — dev server :5174, proxy `/api` → :8001, config de vitest
- [[Archivos/playwright.config.ts.md]] — e2e serial (workers 1), levanta API + web, DB de test aislada
- [[Archivos/index.html.md]] — HTML raíz, monta `#root` y carga `src/main.tsx`
- [[Archivos/tsconfig.app.json.md]] — TS estricto, `react-jsx`, `noEmit`

### `src/` — Frontend (React + Vite)
- [[Archivos/src/main.tsx.md]] — entrypoint React; monta `<NodeBoard />` en StrictMode
- [[Archivos/src/NodeBoard.tsx.md]] — **hub del frontend**: estado del canvas, zoom/pan/drag, selección, conexión de puertos, toolbar ← componente con más referencias entrantes
- [[Archivos/src/types.ts.md]] — **fuente de verdad del dominio**: `Node` (card|timeline), `Edge`, `Port`, `Block`, `PORT_COLORS`
- [[Archivos/src/api.ts.md]] — capa HTTP (`api`) + hook `useBoardPersistence` (carga inicial + autosave con debounce)
- [[Archivos/src/styles.css.md]] — import de Tailwind + reset base
- [[Archivos/src/vite-env.d.ts.md]] — referencia de tipos de Vite

### `src/lib/` — Utilidades puras
- [[Archivos/src/lib/geometry.ts.md]] — `portPos` y `edgePath`: posición de puertos y path SVG de aristas
- [[Archivos/src/lib/geometry.test.ts.md]] — tests unitarios (vitest) de `geometry`
- [[Archivos/src/lib/canvas-types.ts.md]] — tipos de estado de interacción (`Pending`, `Selection`, `DragState`, `ColorMenu`, `PortPos`)
- [[Archivos/src/lib/theme.ts.md]] — `THEMES` (dark/light) y la interfaz `Theme`
- [[Archivos/src/lib/id.ts.md]] — `uid()`: generador de IDs únicos del frontend

### `src/components/` — Componentes UI
- [[Archivos/src/components/NodeCard.tsx.md]] — nodo dibujado: encabezado, menú añadir, puertos, contenido ← componente más complejo
- [[Archivos/src/components/Block.tsx.md]] — bloques de card: texto, número, tabla, imagen
- [[Archivos/src/components/Timeline.tsx.md]] — nodo timeline: etapas con tags editables
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
- [[Archivos/nodeboard-backend/requirements.txt.md]] — fastapi, uvicorn, sqlalchemy, pydantic, pytest, httpx
- [[Archivos/nodeboard-backend/pytest.ini.md]] — config pytest: fija rootdir y `pythonpath` para resolver `app` desde cualquier cwd

### `e2e/` — Tests end-to-end (Playwright)
- [[Archivos/e2e/helpers.ts.md]] — helpers: `connectPorts`, `waitForBoardLoaded`, `createCardNodeAndGetId`
- [[Archivos/e2e/create-node.spec.ts.md]] — crear un nodo aumenta el conteo en uno
- [[Archivos/e2e/connect-edge.spec.ts.md]] — conectar dos puertos agrega una arista visible
- [[Archivos/e2e/persist.spec.ts.md]] — un nodo creado persiste tras recargar

---

## Flujos principales

- [[Flujos/Flujo - Carga y Autosave del Tablero.md]] — arranque: fetch inicial → estado → autosave con debounce vía PUT `/state`
- [[Flujos/Flujo - Creacion de Nodo.md]] — desde el botón/doble clic hasta el nodo persistido
- [[Flujos/Flujo - Conexion de Aristas.md]] — clic en puerto origen → clic en puerto destino → arista renderizada
- [[Flujos/Flujo - Edicion de Contenido de Nodo.md]] — bloques de card y etapas de timeline
- [[Flujos/Flujo - Interaccion del Canvas.md]] — zoom con rueda, pan, drag de nodos, selección y borrado

---

## Mantenimiento

> Regla de trabajo: cada vez que se crea o modifica un archivo del proyecto, se debe actualizar (o crear) su nota correspondiente en `vault/Archivos/...`, incluyendo sus secciones de Exporta/Importa y las referencias cruzadas afectadas ("Importado por" en los archivos relacionados), antes de cerrar la tarea. El vault solo se actualiza ante orden explícita.
