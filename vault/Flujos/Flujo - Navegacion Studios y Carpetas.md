# Flujo — Navegación Studios y Carpetas

## Jerarquía de vistas
```
Home (/) — grilla de Studios
  └─ Studio (studioId) — header + boards recientes + carpetas
       ├─ Board (boardId) — canvas de nodos
       └─ Carpeta (folderId) — header + boards de la carpeta
            └─ Board (boardId) — canvas de nodos
```

## Navegación hacia adelante
1. **Home → Studio**: click en card de Studio → `onStudioClick(id)` → `setView({ kind: "studio", studioId: id })`
2. **Home → Studio → Board (raíz)**: desde StudioView, click en board card o "+ Nuevo Board" → `navigateBoard(boardId, view)` → `setView({ kind: "board", boardId, backView })` donde `backView = { kind: "studio", studioId }`
3. **Studio → Carpeta**: click en card de carpeta → `navigateFolder(folderId, studioId)` → `setView({ kind: "folder", folderId, studioId })`
4. **Carpeta → Board**: click en board card o "+ Nuevo Board" → `navigateBoard(boardId, view)` donde `backView = { kind: "folder", folderId, studioId }`

## Navegación hacia atrás (botón Volver en canvas)
1. **Board con folder_id nulo**: `backView.kind === "studio"` → `navigateStudio(studioId)`
2. **Board con folder_id no nulo**: `backView.kind === "folder"` → `navigateFolder(folderId, studioId)`

## Creación de entidades
- **Studio**: modal sobre Home → `POST /api/studios` → agrega al estado local
- **Carpeta**: modal sobre StudioView → `POST /api/folders` → agrega al estado local + cierra modal
- **Board (raíz)**: botón "+ Nuevo Board" en StudioView → `POST /api/boards { studio_id }` → navega al canvas
- **Board (carpeta)**: botón "+ Nuevo Board" en FolderView → `POST /api/boards { studio_id, folder_id }` → navega al canvas

## Estado de navegación
Manejado en `main.tsx` con `useState<View>` donde `View` es un union discriminado. `backView` guarda la vista anterior sin el board actual, permitiendo volver atrás correctamente sin perder el contexto jerárquico.

## Diseño de referencia
Las pantallas 1c (Home con Estudios) y 1d (Home vacío) toman como fuente oficial de diseño `huginn_standalone.html`. Paleta, tipografía (Plus Jakarta Sans), espaciado y layout deben replicarse fielmente desde ese archivo. Consultar ese HTML como reference canónica antes de modificar cualquier pantalla de la Suite.

## Componentes involucrados
- `Home.tsx` — topbar con título "Huginn" + user pill, search-create bar, grilla de studio cards con color al 15%/35%, estado vacío (1d)
- `StudioView.tsx` — recientes (máx 6), carpetas, crear board/carpeta
- `FolderView.tsx` — boards de la carpeta, crear board
- `CreateStudioModal.tsx` — nombre + 6 swatches de color, estilos del reference design
- `CreateFolderModal.tsx` — solo nombre
- `NodeBoard.tsx` — canvas (recibe `boardId`, `onBack`)
