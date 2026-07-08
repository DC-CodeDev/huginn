# PWA Phase 1 Final Report

## Estado inicial

La mitad inicial de Fase 1 ya había dejado:

- manifest final
- iconos PWA
- service worker custom con `injectManifest`
- fallback offline
- registro del SW solo en producción
- exclusión total de `/api/*`
- build y Docker funcionales

Quedaban pendientes:

- actualización controlada
- conectividad online/offline
- avisos visuales
- safe areas
- altura dinámica segura
- verificación final en contenedor/navegador
- decisión final sobre CSP

## Archivos modificados

- `src/lib/pwa.ts`
- `src/lib/connectivity.ts`
- `src/main.tsx`
- `src/NodeBoard.tsx`
- `src/styles.css`
- `src/components/PwaNoticeCenter.tsx`
- `src/components/AppBar.tsx`
- `src/components/ProfileMenu.tsx`
- `src/components/SettingsModal.tsx`
- `src/components/Login.tsx`
- `src/components/Home.tsx`
- `src/components/StudioView.tsx`
- `src/components/FolderView.tsx`
- `src/components/CreateStudioModal.tsx`
- `src/components/ConfirmDeleteModal.tsx`
- `src/lib/pwa.test.ts`
- `src/lib/connectivity.test.ts`
- `src/components/PwaNoticeCenter.test.tsx`

## Actualización controlada

Se implementó un flujo manual:

- detección de worker `waiting`
- aviso visual discreto
- acción `Actualizar`
- acción `Más tarde`
- `skipWaiting()` solo después de la acción del usuario
- recarga solo después de `controllerchange`
- sin recarga automática

Lógica:

- `src/lib/pwa.ts` registra el SW y guarda el estado de update disponible
- `resolveUpdateIntent()` decide si la actualización:
  - se bloquea (`guardando`)
  - requiere confirmación (`error`)
  - puede aplicarse (`guardado` o fuera del board)
- `subscribeToControllerChange()` recarga solo cuando el usuario ya aprobó la actualización

## Integración con guardado

No se tocó la arquitectura de autosave.

Integración mínima:

- `NodeBoard` sigue usando `useBoardPersistence`
- `NodeBoard` reporta `status` al contexto PWA con `setSaveStatus()`
- el contexto PWA usa ese estado para gobernar la actualización

Comportamiento final:

- `guardando`: el botón de actualización queda deshabilitado
- `guardado`: permite actualizar
- `error`: muestra advertencia y requiere una segunda acción manual

## Conectividad

Se agregó estado centralizado reutilizable:

- `readOnlineStatus()`
- `subscribeToConnectivity()`
- `useOnlineStatus()`

Basado en:

- `navigator.onLine`
- evento `online`
- evento `offline`

Se documentó en código que `navigator.onLine` no garantiza disponibilidad del backend.

No se implementó:

- cola de requests
- retry automático
- reenvío de escrituras pendientes

## Componentes visuales

Se agregó `src/components/PwaNoticeCenter.tsx` con dos avisos:

### Sin conexión

Texto:

- `Sin conexión`
- `Huginn necesita red para cargar y guardar tus boards.`

Aclara además:

- `navigator.onLine` no garantiza que el backend esté disponible

### Nueva versión

Texto:

- `Hay una nueva versión de Huginn disponible.`

Acciones:

- `Actualizar`
- `Más tarde`

Si el board está en error:

- cambia a advertencia previa
- la acción pasa a `Actualizar de todos modos`

## Safe areas

Se agregaron variables CSS reutilizables:

- `--safe-top`
- `--safe-right`
- `--safe-bottom`
- `--safe-left`

Y utilidades:

- `.app-safe-page`
- `.app-safe-top-left`
- `.app-safe-top-right`
- `.app-safe-bottom-left`
- `.app-safe-bottom-center`
- `.app-modal-backdrop`

Aplicadas en:

- Login
- Home
- StudioView
- FolderView
- NodeBoard
- AppBar
- ProfileMenu
- SettingsModal
- CreateStudioModal
- ConfirmDeleteModal

## Cambios de viewport y altura dinámica

Se agregó:

- `--app-dvh: 100vh`
- override con `100dvh` vía `@supports`

Y la utilidad:

- `.app-dvh`

Se reemplazaron usos problemáticos de `h-screen`/`100vh` en pantallas principales por `var(--app-dvh)` o `.app-dvh`.

## Compatibilidad standalone

La app quedó preparada para standalone con:

- manifest `display: standalone`
- `theme-color`
- `background_color`
- safe areas
- `viewport-fit=cover`
- altura dinámica segura
- fallback offline servido en raíz
- SW en scope `/`

Verificación completa de instalación/standalone real en navegador:

- no pudo ejecutarse en este entorno por fallo del sandbox de Chromium al lanzar Playwright

## CSP

No se implementó CSP todavía.

Motivo:

- la app usa muchos estilos inline desde React
- `index.html` carga Google Fonts
- el login usa redirección a Google OAuth
- hay imágenes `data:`
- pueden existir avatares/URLs HTTPS externas
- el cliente soporta `VITE_API_URL`

Directivas mínimas recomendadas para la siguiente fase:

- `default-src 'self'`
- `script-src 'self'`
- `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`
- `font-src 'self' https://fonts.gstatic.com`
- `img-src 'self' data: https:`
- `connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com [dominio VITE_API_URL si aplica]`
- `manifest-src 'self'`
- `worker-src 'self'`
- `frame-ancestors 'none'`
- `base-uri 'self'`
- `object-src 'none'`

Siguiente paso recomendado:

1. mover estilos inline críticos a clases/CSS
2. confirmar hosts reales de avatar/OAuth/API
3. activar CSP primero en `Report-Only`
4. validar login, fuentes, service worker y manifest

## Tests

Se añadieron tests para:

- worker `waiting`
- no activación automática
- bloqueo de update mientras guarda
- advertencia en estado `error`
- `controllerchange` subscription/cleanup
- estado inicial de conectividad por `navigator.onLine`
- reacción a `online`
- reacción a `offline`
- cleanup de listeners
- ausencia de colas/reintentos
- render de aviso offline
- render de aviso de actualización
- respeto del estado de guardado en la UI

## Resultados

- `npm test -- --run` ✅
  - `6` files, `38` tests, OK
- `npm run build` ✅
- `nodeboard-backend/.venv/bin/python -m pytest nodeboard-backend/tests` ✅
  - `45` tests, OK
- `docker build -t huginn-pwa-phase1-final .` ✅

## Docker y curl

Se levantó el contenedor final y se verificó:

- `curl -I /` → `200`, `Cache-Control: no-cache`
- `curl -I /manifest.webmanifest` → `200`, `Content-Type: application/manifest+json`, `Cache-Control: no-cache`
- `curl -I /sw.js` → `200`, `Content-Type: application/javascript`, `Cache-Control: no-cache`
- `curl -I /offline.html` → `200`, `Content-Type: text/html`, `Cache-Control: no-cache`
- `curl -I /api/health` → `200`, `Cache-Control: no-store`

## Navegador

Intento realizado:

- Playwright/Chromium headless contra el contenedor local

Resultado:

- no fue posible completar la verificación porque Chromium falló al iniciar por una restricción del sandbox del entorno (`sandbox_host_linux.cc`)

Conclusión:

- no se inventaron resultados de navegador
- la cobertura quedó respaldada por tests unitarios + build + contenedor + `curl`

## Lighthouse

No disponible en este entorno.

## Limitaciones

- no hay edición offline
- no hay IndexedDB
- no hay Background Sync
- no hay colas
- no hay retry automático
- no hay caché de datos privados
- no hay verificación real de instalación standalone en navegador por la limitación del sandbox
- no hay CSP activa todavía
- la actualización `waiting` quedó probada por tests unitarios, no por simulación real de dos versiones en navegador

## Pasos exactos para Railway

1. Construir y desplegar esta versión con la imagen que incluya el `dist/` nuevo.
2. Configurar `ENVIRONMENT=production`.
3. No definir `COOKIE_SECURE=false`.
4. Mantener `DATA_PATH=/data` con volumen persistente montado.
5. Confirmar que las credenciales OAuth reales estén en variables de entorno.
6. Confirmar que el redirect URI de Google use el dominio final real.
7. Hacer redeploy.
8. Verificar en producción:
   - `GET /manifest.webmanifest`
   - `GET /sw.js`
   - `GET /offline.html`
   - `GET /api/health`
   - registro del SW en DevTools
   - aviso offline
   - aviso de nueva versión al publicar una nueva build
9. Antes de activar CSP, correr primero una política `Report-Only`.
