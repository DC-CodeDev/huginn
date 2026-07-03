**Ruta:** `src/lib/id.ts`

## Responsabilidad
Generador de IDs únicos del lado del frontend, para nodos, puertos, aristas, bloques y etapas creados en el cliente.

## Exporta
- `uid()` — string `id_<contador>_<sufijo aleatorio base36>`; contador de módulo arranca en 100

## Nota
Los IDs del frontend son provisionales: el backend puede reasignar `id` propios (`_uuid`) al persistir un nodo/arista sin id enviado.

## Importa
- (ninguno)

## Importado por
- [[../../../Archivos/src/NodeBoard.tsx.md]] — `uid`
- [[../../../Archivos/src/components/NodeCard.tsx.md]] — `uid`
- [[../../../Archivos/src/components/Timeline.tsx.md]] — `uid`
