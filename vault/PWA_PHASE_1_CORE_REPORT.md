# PWA Phase 1 Core Report

## Dependencias añadidas

- `vite-plugin-pwa@^1.3.0`
- `workbox-window@^7.4.1`

## Archivos creados

- `public/manifest.webmanifest`
- `public/offline.html`
- `public/apple-touch-icon.png`
- `public/favicon.ico`
- `public/icons/icon-192.png`
- `public/icons/icon-512.png`
- `public/icons/icon-192-maskable.png`
- `public/icons/icon-512-maskable.png`
- `src/sw.ts`
- `src/lib/pwa.ts`
- `src/lib/pwa.test.ts`
- `src/sw.test.ts`

## Archivos modificados

- `package.json`
- `package-lock.json`
- `vite.config.ts`
- `index.html`
- `src/main.tsx`
- `tsconfig.app.json`
- `nodeboard-backend/app/main.py`
- `nodeboard-backend/tests/test_pwa_phase0.py`

## Manifest

Se dejó disponible en `/manifest.webmanifest` con estos campos:

- `name`: `Huginn`
- `short_name`: `Huginn`
- `description`: `Pizarra visual para organizar ideas, relaciones y workflows.`
- `start_url`: `/`
- `scope`: `/`
- `display`: `standalone`
- `orientation`: `any`
- `theme_color`: `#0F1117`
- `background_color`: `#0F1117`
- `lang`: `es`
- `categories`: `productivity`, `utilities`

El manifest final se sirve como archivo estático real. `vite-plugin-pwa` no lo sobrescribe.

## Iconos

Se agregaron:

- `192x192`: `public/icons/icon-192.png`
- `512x512`: `public/icons/icon-512.png`
- `192x192 maskable`: `public/icons/icon-192-maskable.png`
- `512x512 maskable`: `public/icons/icon-512-maskable.png`
- `180x180 Apple touch icon`: `public/apple-touch-icon.png`
- `favicon`: `public/favicon.ico`

No se encontró un logo oficial reutilizable en el repo. Los iconos actuales son provisionales y minimalistas.

## Metadatos HTML

`index.html` ahora incluye:

- `manifest`
- `theme-color`
- `apple-touch-icon`
- `apple-mobile-web-app-capable`
- `apple-mobile-web-app-status-bar-style`
- `apple-mobile-web-app-title`
- `favicon`
- `viewport-fit=cover`
- título `Huginn`

## Estrategia del service worker

Se implementó un SW custom con `vite-plugin-pwa` en modo `injectManifest`:

- fuente: `src/sw.ts`
- salida: `/sw.js`
- scope: `/`

Comportamiento:

- `precacheAndRoute(self.__WB_MANIFEST)` para assets hasheados de Vite y assets públicos declarados
- `cleanupOutdatedCaches()` para limpiar cachés obsoletas
- `NetworkOnly` para todo `/api/*`
- `NetworkOnly` para `POST`, `PUT`, `PATCH`, `DELETE`
- navegación HTML con red primero y fallback a `/offline.html`
- sin `skipWaiting`
- sin `clients.claim()`
- sin `Background Sync`
- sin reintentos automáticos
- sin IndexedDB

## Precache

Entra al precache:

- assets hasheados generados por Vite
- `manifest.webmanifest`
- `offline.html`
- `favicon.ico`
- `apple-touch-icon.png`
- iconos PWA en `/icons/*`

No se escriben nombres manuales de assets hasheados.

## Exclusiones y seguridad

Rutas excluidas de cache runtime:

- `/api/auth/*`
- `/api/studios*`
- `/api/folders*`
- `/api/boards*`
- `/api/health`
- cualquier otro `/api/*`
- toda escritura `POST|PUT|PATCH|DELETE`

No se cachean boards, tags, auth ni respuestas privadas.

## Offline

Se agregó `/offline.html` sin dependencia de React ni API.

Contenido:

- `Huginn está sin conexión`
- `Necesitas conexión para cargar y guardar tus boards.`
- `Reintentar`

El botón recarga la página. No promete edición offline.

## Registro del SW

Se separó el registro en `src/lib/pwa.ts`:

- solo corre en producción
- no corre en desarrollo
- detecta errores de registro
- detecta estado `waiting`
- no llama `skipWaiting`
- no recarga automáticamente la app

`src/main.tsx` solo invoca el helper.

## Serving y headers

FastAPI sirve correctamente:

- `/manifest.webmanifest`
- `/sw.js`
- `/offline.html`
- `/icons/*`
- `/apple-touch-icon.png`
- `/favicon.ico`

MIME / caché:

- manifest: `application/manifest+json`, `Cache-Control: no-cache`
- SW: `application/javascript`, `Cache-Control: no-cache`
- offline HTML: `text/html`, `Cache-Control: no-cache`
- iconos: `image/png` o `image/x-icon`, `Cache-Control: public, max-age=31536000, immutable`

No se rompió:

- `/assets`
- fallback SPA
- `/api`
- rutas profundas
- empaquetado Docker/Railway

## Tests

Cobertura añadida o actualizada:

- manifest servido y con campos principales correctos
- `/sw.js` devuelve `200`
- `/offline.html` devuelve `200`
- iconos devuelven `200`
- MIME types correctos
- headers de caché correctos para manifest, SW, offline e iconos
- dimensiones reales de iconos `192`, `512`, `maskable`, `apple-touch`
- política `NetworkOnly` para `/api/*`
- política `NetworkOnly` para escrituras
- fallback offline en navegación
- ausencia de Background Sync
- registro del SW en producción
- no registro en desarrollo
- detección de `waiting`
- no activación automática
- no recarga automática

## Verificación ejecutada

- `npm test -- --run` ✅
- `npm run build` ✅
- `nodeboard-backend/.venv/bin/python -m pytest nodeboard-backend/tests` ✅
- `docker build -t huginn-pwa-phase1-core .` ✅

## Limitaciones pendientes

- Los iconos son temporales; falta branding oficial si aparece un logo definitivo.
- No hay edición offline.
- No hay caché de boards ni de API.
- No hay cola de escrituras.
- No hay Background Sync.
- No hay IndexedDB.
- No hay UI de actualización del SW; solo se detecta `waiting`.
