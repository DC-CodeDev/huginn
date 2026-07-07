# Huginn Nodeboard — Agent Guide

A visual node-based canvas for building workflows (node-graph editor).
Frontend: Vite + React + TypeScript + Tailwind CSS v4.
Backend: FastAPI + SQLAlchemy 2.x + SQLite (Python).
E2E: Playwright. Unit: Vitest (frontend), pytest (backend).

## Essential commands

```bash
npm install                        # frontend deps + e2e deps
python -m venv nodeboard-backend/.venv
nodeboard-backend/.venv/bin/pip install -r nodeboard-backend/requirements.txt

npm run dev             # starts backend (:8001) + frontend (:5174) concurrently
npm run dev:web         # frontend only (vite)
npm run dev:api         # backend only (uvicorn --reload --port 8001)

npm test                # vitest unit tests (src/**/*.test.ts)
npm run test:api        # pytest (nodeboard-backend/tests)

npx playwright test     # e2e tests (or `npx playwright test --ui`)
npm run build           # tsc --noEmit + vite build
```

Backend DB location defaults to `sqlite:///./nodeboard-backend/nodeboard.db`.
Override with env `NODEBOARD_DB`. E2E tests use `NODEBOARD_DB=sqlite:///./e2e/.db/nodeboard.test.db`.

## Project structure

```
huginn/
├── src/                          # Frontend source
│   ├── main.tsx                  # React entry point, auth gating, view routing
│   ├── NodeBoard.tsx             # Main canvas component — all state, interactions, rendering
│   ├── api.ts                    # REST client + useBoardPersistence hook (autosave)
│   ├── types.ts                  # Shared domain types (Node, Edge, Port, Block, etc.)
│   ├── styles.css                # Tailwind import + minimal resets
│   ├── lib/
│   │   ├── auth-context.tsx      # AuthProvider + useAuth (user, loading, login, logout)
│   │   ├── canvas-types.ts       # Interaction state types (DragState, Pending, ColorMenu, PortPos)
│   │   ├── geometry.ts           # portPos(), edgePath() — SVG position math
│   │   ├── geometry.test.ts      # Unit tests for geometry
│   │   ├── id.ts                 # Unique ID generator (uid())
│   │   ├── theme-context.ts      # Theme context for dark/light
│   │   └── theme.ts              # Dark/light theme definitions
│   └── components/
│       ├── NodeCard.tsx          # Renders a single node (card or timeline wrapper)
│       ├── Timeline.tsx          # Timeline node content (stages with tags)
│       ├── Block.tsx             # Renders block variants: text, number, table, image
│       ├── TagsModal.tsx         # Tag management modal per node
│       ├── Login.tsx             # Login page + AuthLoader spinner
│       ├── ProfileMenu.tsx       # User menu with real name/email + logout
│       ├── ToolBtn.tsx, Sep.tsx, MiniBtn.tsx, MenuItem.tsx  # Small UI primitives
├── e2e/                          # Playwright e2e tests
│   ├── helpers.ts                # Shared test utilities (connectPorts, waitForBoardLoaded, dragNodeBy, etc.)
│   ├── create-node.spec.ts
│   ├── connect-edge.spec.ts
│   ├── persist.spec.ts
│   ├── multi-select.spec.ts
│   ├── copy-paste.spec.ts
│   └── tags-modal.spec.ts
├── nodeboard-backend/
│   ├── app/
│   │   ├── main.py               # FastAPI routes (boards, nodes, edges, tags)
│   │   ├── models.py             # SQLAlchemy ORM (Board, Node, Edge)
│   │   ├── schemas.py            # Pydantic schemas (mirrors frontend types.ts)
│   │   └── database.py           # SQLite engine + session factory + get_db dependency
│   ├── tests/
│   │   ├── test_api.py           # Route existence + schema contract tests
│   │   └── test_tags_label.py    # Tags/label propagation + edge case tests
│   ├── pytest.ini
│   └── requirements.txt
├── package.json, tsconfig*.json, vite.config.ts, playwright.config.ts
├── index.html                    # SPA shell
└── vault/                        # Obsidian vault with design docs & file snapshots (not part of build)
```

## Architecture & data flow

### Authentication (frontend)

- **AuthProvider** (`src/lib/auth-context.tsx`) wraps the entire app. On mount, calls `GET /api/auth/me` with `credentials: "include"` to check for an existing session cookie.
- While loading, shows a centered spinner (`AuthLoader`). If no session, shows `Login`. If authenticated, renders the normal app.
- **Login** triggers full-browser redirect to Google OAuth. Google redirects back to `/auth/callback?code=...` on the frontend. The `CallbackHandler` posts the code to `POST /api/auth/login`, the backend sets a httpOnly cookie, and the auth context updates → app shows Home.
- `VITE_GOOGLE_CLIENT_ID` env var is required. The `redirect_uri` is constructed dynamically from `window.location.origin`.
- ProfileMenu shows real user name/email and calls `logout()` from context ("Cerrar sesión").

### State model

The domain is defined in `src/types.ts` (frontend) and mirrored in `nodeboard-backend/app/schemas.py` (backend):

- **Node**: Has `type: "card"|"timeline"`, position (`x`, `y`), `w` (width), `title`, `tags[]`, `ports[]`, plus type-specific content (`blocks[]` for card, `stages[]` for timeline).
- **Edge**: Connects two ports via `from.nodeId + from.portId` → `to.nodeId + to.portId`. Has `curved: boolean` and `label: string`.
- **Port**: `id`, `side: "left"|"right"`, `color` (one of 6 palette colors), `label`.
- **Block** (card nodes only): Union discriminated by `type` — `"text"`, `"number"`, `"table"`, `"image"`.
- **TimelineStage**: `id`, `title`, `tags[]` — stages inside a timeline node.

### Persistence (critical flow)

1. On mount, `useBoardPersistence` in `src/api.ts:39` fetches `/api/boards` → gets first board or creates one → loads full state via `GET /api/boards/{id}`.
2. Every change to `nodes` or `edges` state triggers a debounced (800ms) `PUT /api/boards/{id}/state` that sends the **entire board state**.
3. The backend receives a full replacement: deletes all existing nodes/edges for the board, inserts the new ones (`main.py:159-200`).
4. The frontend never calls PATCH endpoints directly — only `PUT /state` for persistence, and `GET /tags` for the tags modal.

**Implication**: When adding features that change node/edge data, you only need to update `types.ts`, `schemas.py`, and `models.py` JSON columns. The autosave mechanism handles persistence automatically.

### Canvas interaction

- **Pan**: mousedown on empty canvas → drag to pan. Zoom: scroll wheel (clamped 0.25x–2.5x).
- **Node drag**: mousedown on node header → drag moves the node. If multiple nodes are selected and the dragged node is in the selection, all selected nodes move together (group drag).
- **Port connections**: **click-based**, NOT drag. Click a port dot to start pending connection, click another port to complete. Right-click a port dot opens a color picker popup.
- **Selection**: Click node → select (replaces). Shift/Ctrl+click → toggle. Click canvas → deselect.
- **Delete**: Delete/Backspace key (when no input is focused) deletes selected nodes/edges.
- **Copy/paste**: Ctrl+C/V copies selected nodes with +20px cumulative offset. All IDs are regenerated.
- **Double-click canvas**: creates a new card node at mouse position.

### Port position calculation

`portPos()` in `src/lib/geometry.ts:15` computes absolute pixel positions. Y-position = `node.y + PORT_Y0(56) + index_within_same_side * PORT_DY(26)`. X-position = `node.x` (left) or `node.x + node.w` (right). **Important**: the index is per-side, not global array position.

### Tags system

- Tags live on nodes (`tags: string[]`) and also on timeline stages (`stages[i].tags`).
- `GET /api/boards/{id}/tags` returns deduplicated, case-insensitive sorted tags from all nodes on the board — used by the TagsModal for suggestions.
- The TagsModal combines server tags + local board tags so newly created tags appear immediately before the autosave fires.
- Tags assigned on timeline stages are **not** aggregated by the tags endpoint (they're a separate concept).

## Testing conventions

### E2E (Playwright)

- **Serial execution** (workers: 1) because tests share a single SQLite DB. Each test checks its own delta, not absolute counts.
- Playwright auto-starts backend + frontend via `webServer` config. Backend uses isolated `e2e/.db/` — no interference with dev DB.
- **Always wait for autosave before reloading**: `waitForBoardLoaded(page)` waits for save-status to show "guardado". For explicit PUT waits, use `page.waitForResponse` matching `/state` PUT.
- Node creation: use `createCardNodeAndGetId()` helper — it diffs the DOM to find the new node's `data-testid`, robust against DB state accumulation.
- Node selection in tests: **click the header dot** (`span.rounded-full`), not an input, or keyboard shortcuts won't fire (the handler skips when an input is focused).
- Port connection: use `connectPorts()` helper — two sequential clicks, not drag.

### Backend tests (pytest)

- Use in-memory SQLite with `check_same_thread=False`. No ASGI bootstrap — tests call route functions directly with a db session fixture.
- Schema validation uses `model_validate()` (Pydantic v2).
- `pythonpath = .` in `pytest.ini` so imports work from `nodeboard-backend/` as root.

### Frontend unit tests (vitest)

- Only `src/lib/geometry.test.ts` exists. Vitest configured with `environment: "node"`, includes `src/**/*.test.ts`.

## Gotchas & non-obvious patterns

1. **Edge `from` is a Python reserved keyword**: In schemas, `EdgeSchema` uses `from_` with `Field(alias="from")` and `populate_by_name=True`. When constructing from Python code, use `PortRef(nodeId=..., portId=...)` with keyword `from_=...`. The API sends/receives `"from"` in JSON.

2. **SQLite foreign keys**: SQLite doesn't enforce FK constraints by default. The backend registers an `Engine.connect` event listener to run `PRAGMA foreign_keys=ON` on every connection (`main.py:37-42`).

3. **Node render position**: Nodes are positioned absolutely using `left: node.x, top: node.y` in the transformed world layer — these are world coordinates, not screen coordinates. The world layer has `transform: translate(view.x, view.y) scale(view.z)`.

4. **No drag-to-connect ports**: Port dots use `onClick`, not drag events. The pending connection line follows the mouse in screen space via `mouseWorld` state, but the final edge is created on the second click.

5. **Node `updateNode` pattern**: `NodeBoard.tsx:249` — `updateNode(id, fn) => setNodes(ns => ns.map(n => n.id === id ? fn(n) : n))`. All mutations flow through this. Components receive an `update` callback that wraps this for their specific sub-structure.

6. **Block image storage**: Image blocks store files as base64 data URIs in the `src` field. These are persisted in the JSON column and sent via the autosave PUT. No separate file storage.

7. **Timeline node width**: `TIMELINE_W = 360` vs card `CARD_W = 280` — hardcoded constants in `NodeBoard.tsx:21-22`.

8. **Backend JSON columns**: `ports`, `blocks`, `stages`, and `tags` are SQLAlchemy `JSON` columns. When writing to them, Pydantic models must be converted via `.model_dump()` to get plain dicts/lists. When reading, `model_validate()` reconstructs them from attributes.

9. **Vite config uses `vitest/config`**: The vite config imports `defineConfig` from `vitest/config`, not `vite`, because it includes the `test` section. This is important — don't switch it to `vite` import.

10. **Vault directory**: `vault/` is an Obsidian vault with design documentation and file snapshot mirrors. It's tracked in git but not part of the build/test process. Snapshots in `vault/Archivos/` mirror source files and may be outdated — the source files are authoritative.

11. **Board lifecycle**: The frontend always loads the first board from the list or creates one. There's no board selector UI — single-board operation. Deleting via `useEffect` cleanup on `boardId` change clears the clipboard to prevent cross-board paste.

12. **Node state update pattern for group drag**: `groupDragMovedRef` tracks whether the mouse actually moved during a group drag. If no movement on mouseup, it means the user just clicked an already-selected node → selection is replaced to just that node.
