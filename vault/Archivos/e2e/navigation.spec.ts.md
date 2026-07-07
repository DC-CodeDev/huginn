**Ruta:** `e2e/navigation.spec.ts`

## Responsabilidad
Tests e2e del nuevo sistema de navegación Studios/Carpetas — Fase 3.

## Casos de test (6)
1. `el Home muestra los Studios reales del backend` — navega a `/`, verifica que se muestre la UI de Home (estado vacío o grid)
2. `crear un Studio nuevo desde el modal lo agrega a la grilla` — click en `create-studio-card`, llena formulario, selecciona color verde, verifica que la card aparezca con el texto correcto
3. `la vista de Studio separa correctamente recientes de carpetas` — crea Studio, crea Carpeta, crea Board en raíz, verifica que ambas secciones existan
4. `la vista de Carpeta lista sus boards y no muestra la seccion Carpetas` — navega a carpeta, verifica que no tenga `create-folder-card`
5. `el boton atras desde un board en raiz vuelve al Studio` — usa `setupStudioAndBoard`, click en `back-btn`, verifica `back-to-home` y `create-folder-card` visibles
6. `el boton atras desde un board en carpeta vuelve a la Carpeta` — usa `setupStudioFolderAndBoard`, click en `back-btn`, verifica `back-to-studio` visible y `create-folder-card` NO visible

## Importa
- `./helpers` — `setupStudioAndBoard`, `setupStudioFolderAndBoard`
- `@playwright/test` — `test`, `expect`
