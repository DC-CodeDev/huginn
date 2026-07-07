## Flujo: Copy/Paste de Nodo (incluye multi-selección)

> **Estado:** IMPLEMENTADO (Fase 2)

Copia y pega uno o más nodos del canvas usando Ctrl+C / Ctrl+V. El clipboard vive en estado interno del frontend — no usa el OS clipboard. Todo vive en [[../Archivos/src/NodeBoard.tsx.md]].

### Estado involucrado
- `clipboard: Node[] | null` — array de nodos copiados; `null` si no hay copia activa. Un solo nodo copiado es el caso particular `[node]`.
- `lastPasteOffset: { dx, dy } | null` (ref) — delta acumulado de pegados sucesivos. `null` = ningún paste desde la última copia (primer paste parte desde los originales + 20px). Se acumula en +20 con cada `Ctrl+V`.

### Ctrl+C — copiar
1. El handler de teclado en `useEffect` (sin deps, para capturar el closure actual) recibe `keydown`.
2. Si `document.activeElement` es INPUT o TEXTAREA → early-return (pasa al navegador).
3. Si `e.key === "c"` con Ctrl/Meta y `selectedNodeIds.length > 0`:
   - `nodes.filter(n => selectedNodeIds.includes(n.id))` — recoge todos los nodos seleccionados **en el orden del array `nodes`** (no el orden de click).
   - `setClipboard(toCopy)` — guarda el array.
   - `lastPasteOffset.current = null` — resetea el acumulador para que el primer paste parta desde las posiciones originales.
   - `e.preventDefault()` — evita el copiado al OS clipboard.

### Ctrl+V — pegar
1. Si `e.key === "v"` con Ctrl/Meta y `clipboard !== null`:
   - `prev = lastPasteOffset.current ?? { dx: 0, dy: 0 }` — primer paste tiene prev={0,0}.
   - `dx = prev.dx + 20`, `dy = prev.dy + 20` — acumula el offset.
   - `lastPasteOffset.current = { dx, dy }` — actualiza el acumulador.
   - Para cada nodo `src` del clipboard:
     - Genera un ID nuevo con `uid()` para el nodo, todos sus ports, todos sus blocks (si card) o stages (si timeline).
     - Posición: `{ x: src.x + dx, y: src.y + dy }` — aplica el mismo delta a todos → preserva distancias relativas.
   - `setNodes((ns) => [...ns, ...newNodes])` — todos los nodos aparecen en el canvas; el autosave debounced los persiste vía PUT `/api/boards/{id}/state`.
   - `setSelectedNodeIds(newNodes.map(n => n.id))` — el grupo pegado queda seleccionado.
   - Ningún nodo pegado hereda edges, **incluyendo** las conexiones entre nodos del propio grupo copiado.
   - `e.preventDefault()`.

### Invariante de posiciones relativas
- Primer paste: todos los nodos en `clipboard[i].x + 20, clipboard[i].y + 20`. La distancia relativa `(x_i - x_j)` es idéntica a la del original porque se aplica el mismo delta (+20,+20) a todos.
- Segundo paste: todos en `clipboard[i].x + 40, clipboard[i].y + 40`. Distancias relativas conservadas.
- El acumulador opera sobre las **posiciones originales del momento de la copia**, no sobre las del último paste.

### Caso particular: un solo nodo
- `clipboard = [node]` → el comportamiento es idéntico al anterior (un solo nodo se pega en `node.x+dx, node.y+dy`); el test de "segundo paste acumula offset" sigue pasando.

### Limpieza al cambiar de board
- `useEffect(() => { setClipboard(null); lastPasteOffset.current = null; }, [boardId])` — descarta el clipboard al cambiar de tablero para evitar paste cruzado.

### Identificación de posición en tests
- [[../Archivos/src/components/NodeCard.tsx.md]] expone `data-node-x` y `data-node-y` en el div raíz de cada nodo.
- El SVG de aristas lleva `data-testid="canvas-edges"` para que los tests puedan contar sólo las aristas del canvas y no los paths de íconos Lucide.

## Notas
- La persistencia usa el mismo mecanismo de autosave que cualquier otra edición: `useBoardPersistence` (ver [[Flujo - Carga y Autosave del Tablero.md]]).
- Tests que cubren este flujo: [[../Archivos/e2e/copy-paste.spec.ts.md]] (single node + multi-node).
