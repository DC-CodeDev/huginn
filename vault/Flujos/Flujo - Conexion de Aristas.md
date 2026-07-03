## Flujo: Conexión de Aristas

> **Estado:** IMPLEMENTADO

Cómo el usuario conecta dos nodos clickeando puertos, y cómo se renderiza y persiste la arista.

Secuencia:

1. [[../Archivos/src/components/NodeCard.tsx.md]] — clic en un dot de puerto llama `onPortClick(port)`.
2. [[../Archivos/src/NodeBoard.tsx.md]] — `onPortClick`: si no hay conexión en curso, guarda `pending = {nodeId, portId, color}`; si ya hay una, crea la `Edge` (`from` = pending, `to` = puerto clickeado, `curved = defaultCurved`) y limpia `pending`. Clickear el mismo puerto cancela.
3. Mientras hay `pending`, se dibuja una línea punteada desde el puerto hasta el mouse (`edgePath` con el destino en `mouseWorld`).
4. [[../Archivos/src/lib/geometry.ts.md]] — `portPos` da la posición de cada extremo y `edgePath` genera el path SVG (recto o Bézier según `curved`). El color de la arista lo hereda el puerto de origen.
5. Render: cada arista es dos `<path>` (uno transparente ancho para capturar el clic de selección, otro visible) dentro del `<svg width="1">`.
6. El cambio de `edges` dispara el **autosave** → [[Flujo - Carga y Autosave del Tablero.md]].
7. [[../Archivos/nodeboard-backend/app/main.py.md]] — al persistir, `Edge` se guarda con columnas planas (`from_node`/`from_port`/`to_node`/`to_port`); `_edge_to_schema` reconstruye el shape anidado `from`/`to` al leer.

## Notas
- Borrado de un nodo elimina en cascada sus aristas (tanto en el frontend `deleteSelection`/`onDelete` como en el backend `delete_node` y el `ON DELETE CASCADE` de SQLite con `PRAGMA foreign_keys=ON`).
- Una arista seleccionada puede alternar curvo/recto desde la barra de acciones.
- `label` (Fase 1) todavía no se envía ni renderiza; su edición es Fase 2.
- Cubierto por el e2e [[../Archivos/e2e/connect-edge.spec.ts.md]].
