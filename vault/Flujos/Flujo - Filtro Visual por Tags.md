# Flujo — Filtro Visual por Tags

**Estado:** Implementado en Fase 2 de interacciones avanzadas.

## Mecanismo

El filtro visual por tags permite atenuar nodos en el canvas según sus tags, sin ocultarlos ni afectar la interacción.

### Componentes

1. **`src/lib/filter.ts`** — función pura `computeNodeOpacity(nodeTags, filterOpen, filterTags, filterMode)`:
   - Filtro cerrado → opacidad 1 (sin efecto).
   - Filtro abierto, sin tags tildados → opacidad 0.75 para todos.
   - **Modo Amplio** ("wide"): opacidad 1 si el nodo tiene AL MENOS UNO de los tags tildados.
   - **Modo Estricto** ("strict"): opacidad 1 solo si el nodo tiene TODOS los tags tildados.

2. **`src/components/FilterPanel.tsx`** — panel fijo en la UI del canvas (top-right):
   - Botón de cierre (FilterX).
   - Selector de modo: Amplio / Estricto (toggle visual con highlight).
   - Lista de tags únicos del board con checkboxes.
   - Usa `localBoardTags` (derivados de `nodes[]` en NodeBoard) para la lista.

3. **Integración en `src/NodeBoard.tsx`**:
   - Estados: `filterOpen`, `filterTags` (string[]), `filterMode` (FilterMode).
   - `nodeOpacities`: `useMemo` que computa opacidad por nodo.
   - Botón `Filter` en la toolbar (entre save-status y el toggle de conector curvo/recto).
   - Opacidad pasada como prop `opacity` a `NodeCard`.
   - Escape cierra el panel.

4. **Prop `opacity` en `src/components/NodeCard.tsx`**:
   - Nueva prop `opacity: number`.
   - Aplicada al `style` del div raíz.

### Comportamiento

- Al abrir el panel (sin tags tildados): todos los nodos bajan a 75%.
- Al tildar tags: los nodos que coinciden vuelven a 100% según el modo.
- Destildar todos los tags: todos los nodos vuelven a 75%.
- Cerrar el panel: todos los nodos vuelven a 100% independientemente de los tags tildados.
- Los tags tildados se mantienen en memoria (React state) al cerrar/reabrir el panel.

### Tags tildados persistidos en memoria

El estado `filterTags` se conserva al cerrar el panel, de modo que al reabrirlo se restauran los mismos tags tildados. Esto sigue el patrón del resto de estados de UI en NodeBoard (no hay persistencia en servidor para el estado del filtro).

### Tests

- **`src/lib/filter.test.ts`** — 11 tests unitarios (vitest) que cubren:
  - Filtro cerrado → 1.
  - Sin tags tildados → 0.75.
  - Modo Amplio: acierto → 1, fallo → 0.75, nodo sin tags → 0.75.
  - Modo Estricto: todos coinciden → 1, algunos → 0.75, ninguno → 0.75, nodo sin tags → 0.75.
  - Case-insensitive en ambos modos.
