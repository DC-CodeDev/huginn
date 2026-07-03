**Ruta:** `nodeboard-backend/app/schemas.py`

## Responsabilidad
Esquemas Pydantic del contrato de API. El formato expuesto es exactamente el que consume el canvas, así el frontend hace fetch y setea estado sin transformaciones (salvo la traducción de `Edge`, que ocurre en `main.py`). Desde Fase 1 (Paso 2) valida la **forma real** de las estructuras internas del nodo, no un `dict` genérico.

## Exporta

### Estructuras del nodo (espejan `src/types.ts`)
- `PortColor` — `Literal` con los 6 hex reales de `PORT_COLORS` (paleta cerrada, no `str` libre)
- `Port` — `{id, side: Literal["left","right"], color: PortColor, label}`
- `TextBlock` / `NumberBlock` / `TableBlock` / `ImageBlock` — variantes con `type` `Literal`
- `Block` — `Annotated[Union[...], Field(discriminator="type")]`: union discriminada por `type`
- `TimelineStage` — `{id, title, tags: list[str]}`

### Nodos
- `NodeSchema` — `{id?, type, x, y, w, title, ports: list[Port], blocks: list[Block], stages: list[TimelineStage], tags: list[str]}`; `from_attributes=True`. `tags` con `default_factory=list`
- `NodeUpdate` — versión parcial (todos opcionales, incluidos `ports`/`blocks`/`stages`/`tags`) para PATCH

### Aristas
- `PortRef` — `{nodeId, portId}`
- `EdgeSchema` — `{id?, from: PortRef, to: PortRef, curved, label}` (alias `from_` ↔ `from`, `populate_by_name=True`; `label` default `""`). **No** tiene `from_attributes`: se construye a mano en `main.py._edge_to_schema`, no vía `model_validate(orm)`
- `EdgeUpdate` — `{curved?, label?}`

### Boards
- `BoardCreate`, `BoardRename`, `BoardSummary` (con `node_count`/`edge_count`), `BoardState`, `BoardStateSave` (payload de autosave)

## Estado Fase 1
- ✅ **Paso 2 cerrado**: `tags` (Node) y `label` (Edge) reflejados; `ports`/`blocks`/`stages` migrados de `list[dict[str, Any]]` a tipos reales con discriminador. Ya no se acepta cualquier `dict` con forma genérica.
- Validado contra la DB real: los 7 nodos existentes conforman al schema estricto; colores fuera de paleta y `type` de bloque inválido se rechazan.
- ✅ **Paso 3 cerrado**: `main.py` ya propaga `tags` en nodos y `label` en `_edge_to_schema`, `create_edge`, `save_board_state`, `update_node` y `update_edge`.

## Importa
- Librerías externas: `pydantic` (`BaseModel`, `ConfigDict`, `Field`), `datetime`, `typing` (`Annotated`, `Literal`, `Optional`, `Union`)

## Importado por
- [[../../../Archivos/nodeboard-backend/app/main.py.md]] — todos los schemas (response_model y validación de payloads)
- [[../../../Archivos/nodeboard-backend/tests/test_api.py.md]] — `BoardStateSave`
