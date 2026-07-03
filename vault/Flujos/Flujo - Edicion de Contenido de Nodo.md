## Flujo: Edición de Contenido de Nodo

> **Estado:** IMPLEMENTADO

Cómo se edita el interior de un nodo card (bloques) y de un nodo timeline (etapas y tags).

### Card — bloques
1. [[../Archivos/src/components/NodeCard.tsx.md]] — el botón "+" abre el menú ([[../Archivos/src/components/MenuItem.tsx.md]]) para añadir bloque de texto, número, tabla o imagen (o puertos).
2. [[../Archivos/src/components/Block.tsx.md]] — cada bloque se edita según su `type`:
   - `text`: textarea con auto-resize
   - `number`: valor + label
   - `table`: grilla editable con [[../Archivos/src/components/MiniBtn.tsx.md]] para +/− fila/columna
   - `image`: `FileReader` → data URL guardada en `src`
3. Cada edición llama `update(fn)` que muta el nodo en el estado de `NodeBoard`.

### Timeline — etapas y tags
1. [[../Archivos/src/components/Timeline.tsx.md]] — añadir etapa (menú o botón al pie); cada etapa tiene título editable y tags.
2. Los tags se agregan con Enter (draft local `tagDrafts`) y se quitan con la "×".

### Persistencia
- Toda edición modifica `nodes` → dispara el **autosave** → [[Flujo - Carga y Autosave del Tablero.md]].
- [[../Archivos/nodeboard-backend/app/models.py.md]] — `blocks` y `stages` se guardan como JSON en la tabla `nodes`.

## Notas
- Ojo con la homonimia: los **tags de etapa de timeline** (`TimelineStage.tags`, ya existentes) no son los **`tags` de nodo** que agrega Fase 1 (`Node.tags`, metadata del nodo completo, aún sin UI de edición — eso es Fase 2).
