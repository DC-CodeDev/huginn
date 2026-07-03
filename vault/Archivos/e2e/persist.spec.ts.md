**Ruta:** `e2e/persist.spec.ts`

## Responsabilidad
Test e2e: un nodo creado persiste tras recargar la página (verifica el ciclo de autosave + carga desde la DB).

## Flujo del test
1. `goto("/")` + `waitForBoardLoaded`; captura ids previos
2. Crea un nodo y espera el `PUT /state` OK (autosave con debounce de 800 ms) + `save-status === "guardado"`
3. Identifica el id nuevo (el que no estaba antes)
4. `reload()` + `waitForBoardLoaded`
5. Verifica que el nodo nuevo siga visible

## Importa
- [[../../Archivos/e2e/helpers.ts.md]] — `waitForBoardLoaded`
- Librerías externas: `@playwright/test`

## Importado por
- (ninguno) — spec ejecutado por Playwright
