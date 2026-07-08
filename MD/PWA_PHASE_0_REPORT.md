# PWA Phase 0 Report

## 1. Estado anterior

- FastAPI servía `index.html` como catch-all para cualquier ruta no `/api/*` cuando existía `app/static/`.
- Ese catch-all podía responder `200 index.html` para futuros recursos PWA faltantes como `/sw.js` o `/manifest.webmanifest`.
- La cookie de sesión usaba `HttpOnly` y `SameSite=lax`, pero no configuraba `Secure` ni `Path=/`.
- No había políticas explícitas de `Cache-Control`.
- No había cabeceras básicas de seguridad.
- El cliente frontend mezclaba `fetch(..., { credentials: "include" })` manual en auth con un cliente API general sin una política centralizada de credenciales.
- Los secretos OAuth existían localmente en `.env` y `nodeboard-backend/.env`; `git` no los estaba trackeando en el estado actual, pero Docker sí podía copiarlos al contexto de build.

## 2. Problemas encontrados

1. El catch-all SPA no distinguía entre navegación del frontend y requests que parecían archivo.
2. `/sw.js` y `/manifest.webmanifest` podían caer accidentalmente en `index.html`.
3. `curl -I` devolvía `405` en `/` y `/api/health` porque no había soporte explícito para `HEAD`.
4. La cookie de sesión no endurecía `Secure` en producción.
5. No había control explícito de caché para HTML, assets, API privada ni futuros recursos PWA.
6. Docker podía recibir `.env` reales porque no existía `.dockerignore`.
7. El cliente API no garantizaba `credentials: "include"` en todas las llamadas autenticadas.
8. La detección de asset hasheado inicialmente no cubría el formato real de Vite `index-<hash>.js`; se corrigió.

## 3. Archivos modificados

- `nodeboard-backend/app/main.py`
- `nodeboard-backend/tests/test_api.py`
- `nodeboard-backend/tests/test_pwa_phase0.py`
- `src/api.ts`
- `src/api.test.ts`
- `src/lib/auth-context.tsx`
- `.dockerignore`
- `.env.example`
- `nodeboard-backend/.env.example`

## 4. Solución del catch-all

- El serving quedó centralizado en `nodeboard-backend/app/main.py`.
- La regla ahora es:
  - `/api/*` conserva el comportamiento API normal.
  - Si el archivo real existe dentro de `app/static/`, se sirve.
  - Si la ruta parece archivo porque su último segmento tiene extensión y el archivo no existe, devuelve `404`.
  - Si no parece archivo, se trata como navegación SPA y devuelve `index.html`.
- Esto evita que `/sw.js`, `/manifest.webmanifest`, `/offline.html`, `/favicon.ico` o `/icons/*` faltantes reciban `index.html`.
- La arquitectura queda preparada para que Vite copie en el futuro esos recursos a `dist/`, Docker los pase a `app/static/` y FastAPI los sirva desde raíz con scope `/`.

## 5. Configuración de cookies

- La cookie de sesión ahora usa una política centralizada.
- En producción:
  - `HttpOnly=True`
  - `Secure=True` por default
  - `SameSite="lax"`
  - `Path="/"`
  - `max_age=7 días`, alineado con `SESSION_DURATION_DAYS`
- En desarrollo:
  - `COOKIE_SECURE=false` permite usar HTTP local sin romper login.
- Logout borra la cookie con atributos compatibles (`Path=/`, `SameSite=lax`, `Secure` coherente con el entorno).

## 6. Políticas Cache-Control

- HTML y rutas SPA: `Cache-Control: no-cache`
- Assets hasheados bajo `/assets/`: `Cache-Control: public, max-age=31536000, immutable`
- API privada bajo `/api/*`: `Cache-Control: private, no-store`
- Healthcheck `/api/health`: `Cache-Control: no-store`
- Recursos PWA futuros en raíz:
  - `/sw.js`: `Cache-Control: no-cache`
  - `/manifest.webmanifest`: `Cache-Control: no-cache`

## 7. Cabeceras de seguridad

Implementadas globalmente:

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `X-Frame-Options: DENY`
- `Permissions-Policy: camera=(), geolocation=(), microphone=(), payment=(), usb=()`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` solo en producción bajo HTTPS

### CSP

No se implementó CSP todavía.

Motivo:

- La app usa estilos inline desde React en varios componentes.
- `index.html` carga Google Fonts (`fonts.googleapis.com` y `fonts.gstatic.com`).
- La app renderiza imágenes embebidas `data:` y avatares externos.
- El cliente puede usar `VITE_API_URL`, lo que puede requerir `connect-src` adicional.

Antes de activar CSP habrá que definir y verificar al menos:

- `default-src 'self'`
- `script-src 'self'`
- `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`
- `font-src 'self' https://fonts.gstatic.com`
- `img-src 'self' data: https:`
- `connect-src 'self' [dominio API si aplica]`
- `frame-ancestors 'none'`

## 8. Tratamiento de secretos

- `git ls-files` confirmó que `.env` y `nodeboard-backend/.env` no están trackeados actualmente.
- `.gitignore` ya evitaba versionarlos.
- Se añadieron:
  - `.env.example`
  - `nodeboard-backend/.env.example`
  - `.dockerignore`
- `.dockerignore` ahora evita copiar `.env` reales al contexto de Docker.
- Las credenciales reales deben rotarse en Google Cloud y actualizarse en Railway.

## 9. Cambios en requests del frontend

- Se centralizó `apiFetch()` en `src/api.ts`.
- Todas las llamadas autenticadas pasan ahora por una política común con `credentials: "include"`.
- `AuthProvider` dejó de usar `fetch` directo y reutiliza helpers comunes:
  - `fetchCurrentUser()`
  - `loginWithGoogleCode()`
  - `logoutSession()`
- Same-origin sigue funcionando porque `buildApiUrl("/api/...")` devuelve la ruta local cuando `VITE_API_URL` no está definida.

## 10. Tests añadidos

### Frontend

- `src/api.test.ts`
  - same-origin por default
  - boards con `credentials: "include"`
  - `auth/me` con `credentials: "include"`
  - login backend con `credentials: "include"`
  - logout con `credentials: "include"`

### Backend

- `nodeboard-backend/tests/test_pwa_phase0.py`
  - `/` devuelve `index.html`
  - una ruta SPA devuelve `index.html`
  - `/api/ruta-inexistente` no devuelve `index.html`
  - `/archivo-inexistente.js` devuelve `404`
  - `/manifest.webmanifest` devuelve `404`
  - `/sw.js` devuelve `404`
  - un asset existente se sirve
  - caché correcta para HTML, assets hasheados, API privada y health
  - security headers
  - HSTS solo en producción HTTPS
  - cookie segura en producción
  - cookie no segura permitida en desarrollo
  - logout borra cookie correctamente

## 11. Resultados de tests

- `npm test -- --run`
  - `3` archivos, `23` tests, todo OK
- `nodeboard-backend/.venv/bin/python -m pytest nodeboard-backend/tests`
  - `43` tests, todo OK

## 12. Resultado del build

- `npm run build`
  - OK
- `docker build -t huginn-pwa-phase0 .`
  - OK

## 13. Variables de entorno nuevas o modificadas

Nuevas:

- `ENVIRONMENT`
  - usar `production` en Railway
  - default implícito: `development`
- `COOKIE_SECURE`
  - opcional
  - si no se define, en `production` queda `true` por default
  - en local puede forzarse `false`

Sin cambios funcionales pero relevantes:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_CALLBACK_URL`
- `VITE_GOOGLE_CLIENT_ID`
- `DATA_PATH`
- `PORT`

## 14. Acciones manuales necesarias en Railway

1. Configurar `ENVIRONMENT=production`.
2. No definir `COOKIE_SECURE=false` en Railway; dejar el default seguro o definir `COOKIE_SECURE=true`.
3. Confirmar que las credenciales OAuth reales estén cargadas como variables de entorno, no en archivos.
4. Confirmar `DATA_PATH=/data` y que el volumen persistente siga montado en `/data`.
5. Redeploy después de rotar credenciales.

## 15. Acciones manuales necesarias en Google Cloud

1. Rotar el `GOOGLE_CLIENT_SECRET` usado hasta ahora.
2. Verificar o actualizar el `Authorized redirect URI` real de producción.
3. Confirmar que el `GOOGLE_CLIENT_ID` usado por frontend y backend coincide con el proyecto correcto.

## 16. Riesgos pendientes

1. CSP sigue pendiente y debe resolverse antes de endurecer más la superficie web.
2. No existe todavía `manifest.webmanifest`.
3. No existe todavía `sw.js`.
4. No existe todavía `offline.html`.
5. No existe todavía instalación PWA ni actualización controlada.
6. No existe todavía estrategia offline; la persistencia sigue siendo online y completa por snapshot.
7. Railway debe recibir variables reales rotadas antes del siguiente deploy.

## 17. Confirmación de que aún no se implementó la PWA

Confirmado:

- No se agregó `vite-plugin-pwa`
- No se agregó Workbox
- No se creó un service worker funcional
- No se agregó manifest final
- No se implementó caché offline
- No se implementó instalación PWA
- No se cachearon respuestas privadas

## Evidencia manual

Verificación manual contra el contenedor final local `huginn-pwa-phase0` en `http://localhost:8003`:

- `curl -I /` → `200 OK`, `Cache-Control: no-cache`
- `curl -I /api/health` → `200 OK`, `Cache-Control: no-store`
- `curl -I /sw.js` → `404 Not Found`, `Cache-Control: no-cache`
- `curl -I /manifest.webmanifest` → `404 Not Found`, `Cache-Control: no-cache`
- `curl -I /archivo-inexistente.js` → `404 Not Found`
- `curl -I /assets/index-BocrDOzT.js` → `200 OK`, `Cache-Control: public, max-age=31536000, immutable`
- `curl -i /boards/123` → `200 OK`, devuelve `index.html`
