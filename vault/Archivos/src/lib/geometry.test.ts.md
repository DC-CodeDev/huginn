**Ruta:** `src/lib/geometry.test.ts`

## Responsabilidad
Tests unitarios (vitest) de `geometry.ts`. Es la única suite que corre `npm test` (vitest `include: src/**/*.test.ts`).

## Cobertura
- `portPos`: ubica puerto left en `x = node.x`; right en `x = node.x + node.w`; indexa la `y` por posición dentro del mismo lado (no en el array global); devuelve `null` para portId inexistente
- `edgePath`: path recto (`M … L …`) sin `C` cuando `curved=false`; Bézier con `dx=60` mínimo; `dx=|Δx|/2` cuando supera 60

## Importa
- [[../../../Archivos/src/lib/geometry.ts.md]] — `portPos`, `edgePath`, `PORT_Y0`, `PORT_DY`
- [[../../../Archivos/src/types.ts.md]] — `PORT_COLORS`, `Node`, `Port`
- Librerías externas: `vitest`

## Importado por
- (ninguno) — suite de tests
