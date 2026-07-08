# Review técnico de Huginn

## 1. Resumen ejecutivo

Huginn, en su estado actual, es una aplicación de pizarra basada en nodos con un frontend React/Vite funcional a nivel de interacción básica y un backend FastAPI/SQLite funcional a nivel de persistencia simple.

Clasificación actual:

- Implementado: aplicación parcialmente funcional
- Implementado: frontend con backend real
- Implementado: persistencia real en SQLite vía API REST
- Implementado: módulo técnicamente separable e integrable
- Inferido: experimento de UI acelerado y luego conectado a persistencia
- No confirmado: integración real con la Yggdrasil Suite
- No confirmado: madurez suficiente para uso productivo

Conclusión crítica: hoy Huginn no es solo un mock visual, pero tampoco es una aplicación de pizarra completa. Tiene un canvas funcional básico con nodos, puertos, conexiones, edición inline, timeline y autosave completo del tablero. A la vez, concentra casi toda la lógica en un único componente, carece de tipos fuertes en frontend, no tiene selección múltiple, no tiene import/export, no tiene modelo semántico de relaciones, no tiene autenticación, no tiene versionado, no tiene validación de integridad fuerte en frontend y muestra varias señales de prototipo rápido.

## 2. Propósito actual del proyecto

Según el código, Huginn intenta resolver una pizarra visual editable con:

- nodos tipo tarjeta
- nodos tipo línea temporal
- puertos laterales
- conexiones entre puertos
- edición inline del contenido
- guardado automático del tablero

Idea principal:

- una superficie visual libre donde el usuario crea nodos, los mueve, les agrega contenido y los conecta

Tipo de aplicación:

- editor visual tipo canvas 2D con persistencia de tablero

Relación con nodos y conexiones:

- los nodos almacenan contenido flexible (`blocks`, `stages`, `ports`)
- las conexiones unen puertos por referencia `nodeId` + `portId`

Posible rol dentro de Yggdrasil Suite:

- Inferido: editor/visor de grafos conceptuales o de trabajo para investigación, diseño o flujos
- Inferido: posible superficie visual para organizar entidades, etapas, documentos o relaciones semánticas

Relación con Yggdrasil RAG:

- Implementado: no aparece integración real
- Documentado: no aparece
- Inferido: podría servir como capa visual para representar grafos semánticos o nodos derivados de documentos
- No confirmado: cualquier uso real con RAG, Muninn o Heimdall

## 3. Mapa general de arquitectura

### Frontend

- Framework: React + Vite + TypeScript
- Entrada: [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx)
- Componente principal único: [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx)
- Persistencia cliente: [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts)
- Estilos globales: [`src/styles.css`](/home/diego/Projects/huginn/src/styles.css)

Responsabilidades reales del frontend:

- render del canvas
- render de nodos
- render de conexiones SVG
- drag de nodos
- pan y zoom
- selección simple
- edición inline
- creación/eliminación de nodos y conexiones
- autosave vía hook

### Backend

- Existe backend real
- Framework: FastAPI
- ORM: SQLAlchemy
- Base de datos: SQLite
- Entrada backend: [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py)
- Modelos: [`nodeboard-backend/app/models.py`](/home/diego/Projects/huginn/nodeboard-backend/app/models.py)
- Schemas: [`nodeboard-backend/app/schemas.py`](/home/diego/Projects/huginn/nodeboard-backend/app/schemas.py)
- DB config: [`nodeboard-backend/app/database.py`](/home/diego/Projects/huginn/nodeboard-backend/app/database.py)

### Persistencia

- Implementado: SQLite real en [`nodeboard-backend/nodeboard.db`](/home/diego/Projects/huginn/nodeboard-backend/nodeboard.db)
- Implementado: guardado completo del tablero por `PUT /api/boards/{board_id}/state`
- No implementado: `localStorage`
- No implementado: exportación/importación de archivos
- No implementado: sincronización incremental desde el frontend actual
- Mock/documentado pero no usado por el frontend actual: cliente duplicado en [`nodeboard-backend/frontend/api.js`](/home/diego/Projects/huginn/nodeboard-backend/frontend/api.js)

Diagrama textual:

Usuario → `src/NodeBoard.tsx` → estado local React (`nodes`, `edges`, `selection`, `view`) → `useBoardPersistence()` en `src/api.ts` → API FastAPI (`/api/boards`, `/api/boards/{id}`, `/api/boards/{id}/state`) → SQLAlchemy → SQLite

## 4. Estructura del proyecto

| Ruta | Rol | Qué contiene | Estado | Observaciones |
| --- | --- | --- | --- | --- |
| `package.json` | Config frontend/dev | scripts, dependencias, arranque conjunto | implementado | Lanza web y API con `concurrently` |
| `vite.config.ts` | Config dev server | Vite + proxy `/api` a backend | implementado | Proxy a `127.0.0.1:8001` |
| `src/main.tsx` | Entrada frontend | monta `NodeBoard` | implementado | no hay router |
| `src/NodeBoard.tsx` | Núcleo UI | canvas, nodos, edges, edición, toolbar | implementado | concentra demasiada lógica |
| `src/api.ts` | Cliente API + hook | fetch y autosave | implementado | único punto real de persistencia frontend |
| `src/styles.css` | CSS global | reset mínimo + import Tailwind | implementado | Tailwind v4 vía `@import "tailwindcss"` |
| `index.html` | HTML host | root app | implementado | simple |
| `README.md` | doc raíz | arranque general | documentado | resume frontend + backend |
| `nodeboard-backend/app/main.py` | API REST | endpoints boards/nodes/edges/health | implementado | backend funcional |
| `nodeboard-backend/app/models.py` | ORM | `Board`, `Node`, `Edge` | implementado | `ports/blocks/stages` como JSON |
| `nodeboard-backend/app/schemas.py` | contratos API | Pydantic schemas | implementado | contratos relativamente claros |
| `nodeboard-backend/app/database.py` | DB setup | engine, session, dependency | implementado | SQLite por env `NODEBOARD_DB` |
| `nodeboard-backend/tests/test_api.py` | tests backend | health + contrato mínimo | implementado | cobertura muy baja |
| `nodeboard-backend/frontend/api.js` | cliente duplicado | cliente JS de ejemplo | no usado | duplicado de `src/api.ts` |
| `nodeboard-backend/README.md` | doc backend | endpoints y ejemplo de integración | documentado | menciona `nodeboard.jsx`, no coincide exactamente con repo actual |
| `nodeboard-backend/nodeboard.db` | datos | SQLite | implementado | persistencia real encontrada |

## 5. Frontend actual

Frontend actual:

- React con JSX/TSX
- Vite
- TypeScript configurado en modo estricto, pero anulado parcialmente por `// @ts-nocheck` en [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx)
- Tailwind presente como plugin Vite y por clases utility en JSX

Arquitectura real del frontend:

- una sola pantalla
- sin rutas
- sin layouts separados
- sin stores globales
- sin carpetas de componentes separadas
- sin hooks propios adicionales salvo `useBoardPersistence`

Componentes principales dentro de un mismo archivo:

- `NodeBoard`
- `NodeCard`
- `Block`
- `Timeline`
- `ToolBtn`
- `MiniBtn`
- `MenuItem`
- `Sep`

UI presente:

- toolbar superior izquierda
- menú contextual de color de puertos
- barra inferior para acciones de selección
- ayuda textual inferior izquierda

UI no encontrada:

- sidebar real
- panel lateral de propiedades
- inspector
- menú global de tableros
- navegación entre tableros
- login
- responsive dedicado

Crítica:

- Implementado: la UI principal funciona
- Implementado: los controles visibles principales tienen lógica
- Inferido: fue generada para parecer resuelta visualmente desde el principio
- Implementado: varias piezas están conectadas
- No confirmado: comportamiento en pantallas pequeñas

## 6. Canvas / pizarra

La pizarra está implementada manualmente en React, no usa librerías especializadas como React Flow, Konva o similar.

Evidencia:

- transformación manual con `translate(...) scale(...)` en [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx)
- aristas renderizadas con SVG manual
- drag/pan con listeners `mousemove` y `mouseup` globales

Funcionalidades del canvas:

- Pan:
  - Implementado
  - clic y arrastre sobre fondo
  - estado en `view.x` y `view.y`

- Zoom:
  - Implementado
  - rueda del mouse con listener no pasivo
  - límites: `0.25` a `2.5`
  - botones de zoom y reset en toolbar

- Grid:
  - Implementado visualmente
  - grid de puntos por `radial-gradient`
  - no participa en alineación o snapping

- Drag and drop de nodos:
  - Implementado
  - se calcula offset inicial y se actualiza `node.x` / `node.y`

- Selección:
  - Implementado: selección simple de nodo o arista
  - No implementado: selección múltiple
  - No implementado: marquee/lasso

- Creación de nodos:
  - Implementado
  - botón toolbar
  - doble clic en canvas para crear tarjeta
  - botón toolbar para timeline

- Edición de nodos:
  - Implementado inline
  - título editable
  - bloques editables
  - etapas timeline editables
  - labels de puertos editables

- Conexión entre nodos:
  - Implementado
  - por click en un puerto origen y luego click en un puerto destino
  - muestra línea temporal punteada mientras la conexión está pendiente

- Eliminación:
  - Implementado
  - borrar nodo elimina aristas asociadas en estado local
  - borrar arista desde selección
  - tecla Delete/Backspace

- Reordenamiento visual / z-index:
  - No implementado explícitamente
  - No hay bring-to-front/send-to-back

- Límites del canvas:
  - No implementado
  - se puede desplazar libremente

- Mouse:
  - Implementado para drag/pan/zoom/conectar

- Teclado:
  - Implementado: Delete, Backspace, Escape
  - No implementado: shortcuts avanzados

- Performance:
  - Inferido: aceptable para pocos nodos
  - No confirmado: escalabilidad con tableros grandes
  - Riesgo: rerender completo del árbol en cada cambio

Qué es funcional y qué es solo visual:

- Funcional:
  - pan
  - zoom
  - drag nodos
  - selección simple
  - creación/eliminación de nodos
  - conexiones básicas
  - edición inline
  - cambio de color de puerto
  - cambio curvo/recto de arista

- Solo visual o incompleto:
  - grid sin snapping
  - colores sin semántica formal
  - timeline sin relación semántica con grafo
  - estado visual atractivo pero sin modelo rico detrás

## 7. Modelo de nodos

No existe contrato formal de nodo en el frontend dentro de `src/NodeBoard.tsx`. El frontend trabaja con objetos implícitos y `@ts-nocheck`.

Estructura observada en frontend:

- `id`
- `type`
- `x`
- `y`
- `w`
- `title`
- `ports`
- `blocks`
- `stages`

Estructura formal en backend:

- `NodeSchema` en [`nodeboard-backend/app/schemas.py`](/home/diego/Projects/huginn/nodeboard-backend/app/schemas.py)

Campos:

| Campo | Estado | Observación |
| --- | --- | --- |
| `id` | implementado | string opcional en schema |
| `type` | implementado | `card` o `timeline` |
| `x` | implementado | posición horizontal |
| `y` | implementado | posición vertical |
| `w` | implementado | ancho |
| `title` | implementado | editable |
| `ports` | implementado | lista flexible JSON |
| `blocks` | implementado | lista flexible JSON |
| `stages` | implementado | lista flexible JSON |

No se observan en nodo:

- altura persistida
- color de nodo
- relevancia formal
- metadata tipada
- estado `selected` persistente
- owner / source / timestamps en frontend

Tipos de nodo reales:

- `card`
- `timeline`

Bloques de `card` observados:

- `text`
- `number`
- `table`
- `image`

Campos opcionales o flexibles:

- `ports[].label`
- `ports[].color`
- `blocks[].label`
- `blocks[].src`
- `blocks[].data`
- `stages[].tags`

Campos no usados o ausentes:

- tamaño alto
- collapsed
- locked
- tags de nodo
- agrupación/burbuja
- relevancia tipada

## 8. Modelo de conexiones / relaciones

Contrato formal en backend:

- `EdgeSchema` en [`nodeboard-backend/app/schemas.py`](/home/diego/Projects/huginn/nodeboard-backend/app/schemas.py)

Campos implementados:

- `id`
- `from.nodeId`
- `from.portId`
- `to.nodeId`
- `to.portId`
- `curved`

Representación real:

- la relación une puertos, no nodos directamente
- el color de la línea se deriva del puerto origen en render

Campos no implementados:

- label de conexión
- tipo de relación
- peso
- dirección semántica explícita más allá de `from`/`to`
- flechas visuales
- metadata
- relevancia

Curvas o líneas:

- Implementado: `curved: boolean`
- Implementado: path recto o bezier simple

Edición:

- Implementado: alternar `curved`
- No implementado: editar endpoints arrastrando
- No implementado: editar label o tipo

Eliminación:

- Implementado

Persistencia:

- Implementado en backend

Conclusión:

- Implementado: conexiones funcionales básicas
- No confirmado: integridad total entre `portId` y puertos existentes al guardar estado completo
- Incompleto: no hay modelo de relación suficientemente rico para una pizarra semántica seria

## 9. Estado global y manejo de datos

Manejo actual:

- `useState` local dentro de `NodeBoard`
- `useRef` para canvas, drag y view
- `useEffect` para eventos globales y autosave indirecto
- hook `useBoardPersistence` en [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts)

Estados principales:

- `nodes`
- `edges`
- `selection`
- `pending`
- `mouseWorld`
- `menuNode`
- `colorMenu`
- `defaultCurved`
- `view`
- `theme`

No existe:

- Context
- Redux
- Zustand
- store externo
- máquina de estados

Sincronización con persistencia:

- al montar:
  - lista tableros
  - abre el primero o crea uno
  - reemplaza `nodes` y `edges`

- luego:
  - cada cambio en `nodes` o `edges` dispara autosave con debounce

Datos mock / iniciales:

- `initialNodes`
- `initialEdges`

Estado real de esos datos:

- Implementado como demo inicial
- Reemplazados por datos del backend si la carga resulta exitosa
- Si el backend falla, quedan visibles y pueden confundir como si fueran persistidos

## 10. Persistencia actual

Persistencia real:

- Implementado en SQLite
- DB por defecto: `sqlite:///./nodeboard.db` en backend, sobreescrita por `NODEBOARD_DB`
- script `dev:api` usa `sqlite:///./nodeboard-backend/nodeboard.db`

Dónde guarda:

- backend SQLite

Cómo carga:

- `GET /api/boards`
- luego `GET /api/boards/{id}` o `POST /api/boards`

Cuándo guarda:

- tras cambios en `nodes` o `edges`
- debounce por defecto: `800ms`

Formato:

- tablero completo con `nodes` y `edges`

Auto-save:

- Implementado

Importación/exportación:

- No implementado

Manejo de errores:

- Implementado de forma mínima
- `console.error`
- `status = "error"`
- no hay UI de recuperación ni retry explícito

Qué ocurre al recargar:

- si API y DB están disponibles, carga el primer tablero
- si no existen tableros, crea uno
- si falla la API, la UI conserva demo local visible

Qué ocurre al cerrar:

- depende de que el debounce haya alcanzado a persistir antes de cerrar
- no hay `beforeunload` ni flush garantizado

Qué datos se pierden:

- potencialmente cambios recientes dentro de la ventana de debounce
- todo si el backend no responde y el usuario trabajó sobre el estado demo no guardado

## 11. Flujos actuales

### Crear nodo

- Punto de entrada:
  - botón “Nuevo nodo”
  - doble clic en canvas
  - botón “Línea temporal”
- Componentes:
  - `NodeBoard`
- Funciones:
  - `addNode`
- Estado modificado:
  - `nodes`
- Persistencia:
  - autosave posterior por `useBoardPersistence`
- Resultado:
  - nodo agregado al estado local
- Estado:
  - completo para caso básico

### Mover nodo

- Punto de entrada:
  - `onMouseDown` sobre `NodeCard`
- Funciones:
  - `onStartDrag`
  - handler global `move`
- Estado:
  - `dragRef`
  - `nodes[].x/y`
- Persistencia:
  - autosave posterior
- Estado:
  - completo para drag simple

### Editar nodo

- Punto de entrada:
  - inputs/textarea dentro de `NodeCard`, `Block`, `Timeline`
- Funciones:
  - `updateNode`
  - `update(...)` locales
- Estado:
  - mutación inmutable del nodo
- Persistencia:
  - autosave posterior
- Estado:
  - completo para edición inline básica

### Conectar nodos

- Punto de entrada:
  - click en puerto
- Funciones:
  - `onPortClick`
- Estado:
  - `pending`
  - luego `edges`
- Persistencia:
  - autosave posterior
- Resultado:
  - arista agregada
- Estado:
  - parcial

Observaciones:

- no valida sentido lógico entrada/salida
- permite conectar por secuencia de clicks simple
- no hay prevención visible de duplicados

### Borrar nodo

- Punto de entrada:
  - botón basura del nodo
  - tecla Delete/Backspace con nodo seleccionado
- Funciones:
  - `onDelete`
  - `deleteSelection`
- Estado:
  - `nodes`
  - `edges`
- Persistencia:
  - autosave posterior
- Estado:
  - completo para caso básico

### Borrar conexión

- Punto de entrada:
  - click en arista, luego barra inferior o Delete
- Funciones:
  - `deleteSelection`
- Estado:
  - `edges`
- Persistencia:
  - autosave posterior
- Estado:
  - completo para caso básico

### Guardar tablero

- Punto de entrada:
  - automático
- Funciones:
  - `useBoardPersistence`
  - `api.saveState`
- Estado:
  - `status`
- Persistencia:
  - sí
- Estado:
  - completo pero rudimentario

### Cargar tablero

- Punto de entrada:
  - `useEffect` en `useBoardPersistence`
- Funciones:
  - `api.listBoards`
  - `api.getBoard`
  - `api.createBoard`
- Estado:
  - `nodes`, `edges`, `boardId`, `status`
- Estado:
  - completo para “primer tablero”

Limitación:

- no hay selector de tablero

### Cambiar color/relevancia

- Implementado:
  - cambio de color de puertos
- No implementado:
  - relevancia formal del nodo
  - relevancia de conexión
- Estado:
  - parcial / solo visual

### Crear agrupaciones o burbujas

- No implementado
- No documentado
- No confirmado

### Zoom / pan

- Implementado
- completo para caso básico

### Seleccionar varios nodos

- No implementado

## 12. Backend actual

Sí existe backend funcional para Huginn.

Framework:

- FastAPI

Endpoints encontrados:

- `GET /api/boards`
- `POST /api/boards`
- `GET /api/boards/{board_id}`
- `PATCH /api/boards/{board_id}`
- `DELETE /api/boards/{board_id}`
- `PUT /api/boards/{board_id}/state`
- `POST /api/boards/{board_id}/nodes`
- `PATCH /api/nodes/{node_id}`
- `DELETE /api/nodes/{node_id}`
- `POST /api/boards/{board_id}/edges`
- `PATCH /api/edges/{edge_id}`
- `DELETE /api/edges/{edge_id}`
- `GET /api/health`

Persistencia:

- SQLite con SQLAlchemy

Modelos:

- `Board`
- `Node`
- `Edge`

Validaciones:

- existencia de tablero
- existencia de nodo/arista al actualizar o borrar
- al crear arista granular, valida que los nodos existan en el tablero

Limitaciones:

- `save_board_state` recrea todo el tablero y no valida fuerte la integridad puerto-a-puerto
- `ports`, `blocks`, `stages` se guardan como JSON libre
- no hay autenticación
- no hay usuarios
- no hay control de concurrencia
- no hay migraciones formales visibles

## 13. API / contratos

### Frontend → Backend

Contrato real de lectura:

- `GET /api/boards` → lista de `BoardSummary`
- `GET /api/boards/{id}` → `BoardState`

Contrato real de guardado:

- `PUT /api/boards/{id}/state`
- input:
  - `name?`
  - `nodes[]`
  - `edges[]`
- output:
  - `BoardState`

Campos obligatorios:

- para nodos: `type`, `x`, `y`, `w`, `title`, `ports`, `blocks`, `stages`
- para edges: `from`, `to`, `curved`

Errores posibles:

- 404 tablero inexistente
- errores HTTP genéricos por validación

Nivel de certeza:

- alto

### Canvas → Store local

- `NodeBoard` usa estado local React
- no existe contrato formal ni tipos explícitos en el canvas

Nivel de certeza:

- alto

### Nodo → Componente visual

- input: objeto implícito `node`
- output: render editable + callbacks

Nivel de certeza:

- medio-alto

### Conexión → Componente visual

- input: edge con `from`, `to`, `curved`
- output: paths SVG

Nivel de certeza:

- alto

### Tablero → Persistencia

- el tablero se guarda como reemplazo total
- no hay patch incremental en frontend actual

Nivel de certeza:

- alto

### Importación/exportación

- No implementado

## 14. Tipos y schemas

Tipos frontend en [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts):

- `SaveStatus`
- `Entity`
- `Board`
- `BoardSummary`
- `PersistenceOptions`

Problemas:

- son demasiado genéricos
- `nodes` y `edges` son `Entity[]`
- no reflejan estructura real del canvas

Schemas backend en [`nodeboard-backend/app/schemas.py`](/home/diego/Projects/huginn/nodeboard-backend/app/schemas.py):

- `NodeSchema`
- `NodeUpdate`
- `PortRef`
- `EdgeSchema`
- `EdgeUpdate`
- `BoardCreate`
- `BoardRename`
- `BoardSummary`
- `BoardState`
- `BoardStateSave`

Estado de alineación:

- backend y frontend coinciden razonablemente en forma de datos
- frontend no aprovecha esa estructura con tipos fuertes

Duplicaciones:

- cliente duplicado entre `src/api.ts` y `nodeboard-backend/frontend/api.js`

Tipos implícitos:

- casi todo `src/NodeBoard.tsx`

Uso de `any`:

- no hay `any` explícito dominante, pero `@ts-nocheck` anula el control real

## 15. Diseño visual

Paleta:

- modo dark y light definidos en `THEMES` en [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx)

Dark mode:

- fondo oscuro
- tarjetas oscuras
- bordes suaves
- acento terracota para selección

Light mode:

- fondo claro
- tarjetas blancas

Accent colors / puertos:

- `#C4847A`
- `#4ADE80`
- `#F87171`
- `#60A5FA`
- `#C084FC`
- `#E8EBF0`

Colores de relevancia:

- No implementados formalmente
- Los colores existen, pero asociados a puertos y etapas, no a una taxonomía de relevancia documentada

Nodos neutros / rojos / verdes / amarillos:

- solo de forma implícita por color de puertos

Grid:

- implementado como patrón de puntos

Sombras, bordes, animaciones:

- sí
- visualmente bastante pulido para un prototipo

Consistencia visual con Yggdrasil Suite:

- No confirmada
- Inferido: estética oscura/clean puede alinearse con una suite técnica

Partes visuales bien resueltas:

- toolbar
- estados de selección
- puertos
- aristas curvas
- timeline visual

Partes visuales que son mock o semánticamente débiles:

- timeline sin integración con relaciones reales
- color como semántica no formalizada
- nodos ricos pero sin modelo fuerte

## 16. Integración con Yggdrasil Suite

### Implementado

- no se encontró integración real con Yggdrasil Suite

### Documentado

- no se encontró documentación específica sobre Muninn, Heimdall o Yggdrasil RAG

### Inferido

- Huginn podría convertirse en:
  - editor de grafo semántico
  - tablero de entidades derivadas de documentos
  - visor de conexiones para RAG o workflows

### No confirmado

- parser universal
- documentos comunes de suite
- exportación de grafo para RAG
- ingestión de nodos derivados de documentos
- acoplamiento con Muninn o Heimdall

## 17. Tests actuales

Tests encontrados:

| Ruta | Qué cubren | Tipo | Estado |
| --- | --- | --- | --- |
| `nodeboard-backend/tests/test_api.py` | `health()` y existencia de rutas; validación mínima de `BoardStateSave` | unitario muy básico | ejecutable en principio |

No se encontraron tests para:

- canvas
- nodos frontend
- conexiones frontend
- drag/drop
- autosave frontend
- persistencia end-to-end
- import/export

Conclusión:

- cobertura actual extremadamente baja

## 18. Configuración

Variables de entorno:

- `VITE_API_URL` en frontend
- `NODEBOARD_DB` en backend

Vite/React:

- [`vite.config.ts`](/home/diego/Projects/huginn/vite.config.ts)
- host `127.0.0.1`
- puerto `5174`
- proxy `/api` → `127.0.0.1:8001`

Tailwind:

- presente por plugin `@tailwindcss/vite`
- no se encontró `tailwind.config.*`
- configuración mínima / implícita

TypeScript:

- `strict: true` en [`tsconfig.app.json`](/home/diego/Projects/huginn/tsconfig.app.json)
- contradicción práctica por `@ts-nocheck` en el archivo principal

ESLint:

- no se encontró configuración propia del proyecto

Tests:

- script `test:api`
- sin Vitest/Jest configurados para frontend

Build:

- `tsc -b && vite build`

Scripts `package.json`:

- `dev`
- `dev:web`
- `dev:api`
- `build`
- `preview`
- `test:api`

## 19. Código muerto, mocks y prototipos

Identificados:

- `initialNodes` y `initialEdges` en [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx)
  - Estado: demo inicial / prototipo visual

- `nodeboard-backend/frontend/api.js`
  - Estado: duplicado no usado por el frontend actual

- `src/api.ts` tipos `Entity`, `Board`, `BoardSummary`
  - Estado: implementados pero poco precisos

- señales de prototipo:
  - `// @ts-nocheck`
  - lógica masiva en un solo archivo
  - ausencia de tipado real del canvas

Botones o handlers sin función:

- no se detectaron muchos botones completamente muertos en la UI principal
- sí se detectan funciones y endpoints granulares que el frontend actual no usa

Endpoints existentes pero no conectados por flujo principal:

- `PATCH /api/boards/{id}`
- `DELETE /api/boards/{id}`
- `POST /api/boards/{id}/nodes`
- `PATCH /api/nodes/{id}`
- `DELETE /api/nodes/{id}`
- `POST /api/boards/{id}/edges`
- `PATCH /api/edges/{id}`
- `DELETE /api/edges/{id}`

El frontend actual prefiere guardar el estado completo por `PUT /state`.

## 20. Problemas encontrados

| Problema | Ruta relacionada | Impacto | Severidad | Bloquea |
| --- | --- | --- | --- | --- |
| Lógica principal concentrada en un único archivo grande | `src/NodeBoard.tsx` | dificulta mantenimiento, pruebas y evolución | alta | funcionalidad real futura |
| Tipado anulado en el corazón de la app | `src/NodeBoard.tsx` | eleva riesgo de bugs silenciosos | alta | calidad real |
| Frontend sin contrato formal de nodo/arista | `src/NodeBoard.tsx`, `src/api.ts` | evolución frágil | alta | escalado funcional |
| Demo inicial visible aunque falle la API | `src/NodeBoard.tsx`, `src/api.ts` | puede engañar sobre persistencia real | alta | comprensión y confiabilidad |
| Sin multi-selección | `src/NodeBoard.tsx` | limita uso de pizarra real | media | UX real |
| Sin import/export | proyecto completo | impide interoperabilidad | alta | funcionalidad real |
| Sin modelo semántico de relaciones | `src/NodeBoard.tsx`, `nodeboard-backend/app/schemas.py` | conexiones pobres para uso serio | alta | funcionalidad real |
| Persistencia por reemplazo total | `nodeboard-backend/app/main.py` | simple pero ineficiente y frágil | media | escalado |
| Endpoints granulares no aprovechados | frontend vs backend | duplicidad conceptual | media | limpieza y evolución |
| Sin tests frontend | frontend completo | alto riesgo de regresiones | alta | estabilización |
| Sin autenticación/usuarios/tableros seleccionables | backend/frontend | no apto para producto multiusuario | crítica | producto real |
| Sin validación fuerte de puertos en guardado completo | `save_board_state` | posible inconsistencia lógica | media | integridad |

## 21. Qué se puede rescatar

### Canvas base manual

- Qué es: implementación de pan/zoom/drag/conexiones
- Por qué sirve: ya resuelve la mecánica mínima
- Integración: alta
- Riesgo al tocarla: medio-alto

### Modelo `Board` / `Node` / `Edge` del backend

- Qué es: persistencia clara y simple
- Por qué sirve: separa bien tablero, nodos y aristas
- Integración: alta
- Riesgo: medio

### Hook `useBoardPersistence`

- Qué es: carga inicial + autosave
- Por qué sirve: resuelve persistencia mínima end-to-end
- Integración: alta
- Riesgo: medio

### Sistema de bloques dentro de nodos

- Qué es: `text`, `number`, `table`, `image`
- Por qué sirve: da flexibilidad de contenido
- Integración: media-alta
- Riesgo: medio

### Nodo `timeline`

- Qué es: tipo especial visual
- Por qué sirve: puede convertirse en artefacto útil de planificación
- Integración: media
- Riesgo: medio

## 22. Qué habría que rehacer

### Tipado y modelo frontend

- Qué es: definición implícita actual en `NodeBoard.tsx`
- Por qué está mal: `@ts-nocheck` + ausencia de contratos reales
- Dependencias: casi todo el frontend
- Reemplazo aislado: parcialmente

### Arquitectura del componente único

- Qué es: `src/NodeBoard.tsx`
- Por qué está mal: acoplamiento excesivo
- Dependencias: todo el frontend
- Reemplazo aislado: no completamente, pero se puede extraer por capas

### Modelo de relaciones

- Qué es: edge mínima con `curved`
- Por qué está mal: insuficiente para semántica y edición avanzada
- Dependencias: render de edges, backend schema
- Reemplazo aislado: sí, con migración controlada

### Estrategia de persistencia completa por reemplazo

- Qué es: `PUT /state`
- Por qué está mal: simple pero tosca
- Dependencias: autosave actual
- Reemplazo aislado: sí, si se define store/event sourcing o sync incremental

### Señalización de estado offline/error

- Qué es: demo + `status` mínimo
- Por qué está mal: puede inducir interpretación falsa
- Dependencias: `src/api.ts`, `src/NodeBoard.tsx`
- Reemplazo aislado: sí

## 23. Siguientes pasos recomendados

### Fase 0 — Entender y limpiar

- Objetivo:
  - reducir ambigüedad del proyecto

- Tareas:
  - definir tipos frontend reales para `Node`, `Edge`, `Port`, `Block`, `TimelineStage`
  - eliminar `@ts-nocheck`
  - separar `NodeBoard.tsx` en módulos
  - decidir si se conserva canvas manual o se migra a librería
  - eliminar o marcar claramente código duplicado (`nodeboard-backend/frontend/api.js`)
  - documentar qué es demo y qué es persistencia real

- Archivos afectados:
  - `src/NodeBoard.tsx`
  - `src/api.ts`
  - nueva carpeta `src/types/` o equivalente
  - `nodeboard-backend/frontend/api.js`

- Riesgo:
  - medio

- Criterio de cierre:
  - sin `@ts-nocheck`
  - contratos frontend explícitos
  - estructura modular mínima

### Fase 1 — Modelo de datos real

- Objetivo:
  - convertir el tablero en una estructura semántica seria

- Tareas:
  - definir tipos de nodo formales
  - definir tipos de relación formales
  - agregar metadata de nodo
  - agregar label/tipo/peso/dirección visual a edges
  - definir relevancia formal si es requisito
  - decidir si timeline sigue siendo nodo especial o entidad aparte

- Archivos afectados:
  - `src` tipos y componentes
  - `nodeboard-backend/app/schemas.py`
  - `nodeboard-backend/app/models.py`
  - `nodeboard-backend/app/main.py`

- Riesgo:
  - alto

- Criterio de cierre:
  - modelo estable y documentado

### Fase 2 — Canvas funcional

- Objetivo:
  - llevar la UX a nivel de pizarra real

- Tareas:
  - multi-selección
  - marquee/lasso
  - atajos de teclado
  - snapping opcional
  - mejor edición de conexiones
  - agrupaciones/burbujas si son parte del producto
  - capas, orden visual, copy/paste

- Archivos afectados:
  - frontend canvas y componentes

- Riesgo:
  - alto

- Criterio de cierre:
  - operaciones básicas de pizarra comparables a un editor usable

### Fase 3 — Persistencia

- Objetivo:
  - hacer la persistencia confiable y extensible

- Tareas:
  - selector de tableros
  - guardar/cargar explícito además de autosave
  - manejo offline/error
  - export/import JSON
  - revisar si conviene pasar de replace-all a sync incremental
  - validar referencias de puertos y relaciones

- Archivos afectados:
  - `src/api.ts`
  - backend endpoints
  - DB schemas si cambia estrategia

- Riesgo:
  - medio-alto

- Criterio de cierre:
  - persistencia predecible, recuperable y portable

### Fase 4 — Integración con la Suite

- Objetivo:
  - definir el rol real de Huginn dentro de Yggdrasil

- Tareas:
  - acordar contrato con Muninn/Heimdall/RAG
  - decidir si Huginn consume documentos, entidades o embeddings
  - definir formato de import/export común
  - decidir si Huginn es editor manual, visor semántico o ambos

- Archivos afectados:
  - no confirmados todavía

- Riesgo:
  - alto por definición de producto

- Criterio de cierre:
  - integración especificada y probada contra otro módulo real

### Fase 5 — Tests y estabilización

- Objetivo:
  - bajar riesgo de regresiones

- Tareas:
  - tests frontend de canvas y flujos
  - tests API de CRUD real
  - tests end-to-end
  - validación de contratos
  - pruebas de persistencia y recuperación

- Archivos afectados:
  - suite de tests nueva
  - backend tests existentes

- Riesgo:
  - medio

- Criterio de cierre:
  - flujos críticos cubiertos y ejecutables en CI

## 24. Resumen final

Huginn hoy es una pizarra visual parcialmente funcional, no solo un mock.

Qué funciona:

- canvas manual
- pan y zoom
- drag de nodos
- nodos tipo tarjeta y timeline
- edición inline de contenido
- puertos
- conexiones básicas
- selección simple
- autosave real a backend
- backend FastAPI con SQLite

Qué es prototipo:

- modelo implícito del frontend
- demo inicial de nodos/aristas
- colores sin semántica formal
- timeline como pieza visual más que entidad integrada al grafo
- cliente duplicado no usado

Qué está incompleto:

- multi-selección
- import/export
- modelo rico de relaciones
- paneles e inspección avanzada
- integración con la suite
- tipado serio frontend
- tests frontend
- estrategia robusta de persistencia y manejo offline

Qué debería hacerse primero:

- tipar y modularizar el frontend
- definir el modelo de datos real
- decidir el rol exacto de las relaciones y de la timeline
- eliminar ambigüedad entre demo visual y estado persistido

Qué tan lejos está de ser funcional:

- como demo interactiva con persistencia simple: ya está relativamente cerca
- como herramienta de pizarra seria dentro de una suite mayor: todavía está a una distancia media-alta
- como módulo productivo integrado a Yggdrasil Suite: todavía falta definición de dominio, robustez técnica y pruebas
