# PWA Readiness Audit for Huginn

## 1. Resumen ejecutivo

**Estimación de preparación PWA actual: 32%**

Huginn está razonablemente bien encaminado como aplicación web autenticada desplegable en un solo servicio, pero hoy **no está preparado** para convertirse en una PWA instalable y confiable sin trabajo previo. El proyecto ya tiene varios cimientos útiles: frontend en Vite/React, backend FastAPI que sirve el build del frontend en producción, `HTTPS` implícito por Railway, fallback SPA y persistencia server-side real. Sin embargo, faltan casi todos los elementos PWA explícitos y existen varios riesgos de arquitectura si se agrega un service worker sin endurecer antes la app.

La conclusión principal es:

- `IMPLEMENTADO`: build pipeline, serving same-origin en producción, fallback SPA, sesiones por cookie, autosave con estado visible, health endpoint.
- `PARCIAL`: deploy preparado para Railway, autenticación usable en navegador, persistencia de boards, soporte responsive básico.
- `FALTANTE`: `manifest`, `service worker`, registro SW, iconos PWA, offline fallback, aviso de actualización, limpieza de cachés, detección online/offline, estrategia de caché.
- `RIESGO`: canvas basado en mouse, guardado por snapshot completo sin control de versión, posible serving incorrecto de `sw.js` y `manifest.webmanifest` por el catch-all actual, credenciales OAuth comprometidas en `.env`, cookies sin `Secure`, falta de políticas explícitas de caché/seguridad.

**Nivel recomendado para la primera versión:** PWA instalable con caché segura de assets estáticos, `offline fallback`, detección de conectividad y flujo de actualización controlado. **No** recomiendo edición offline ni cola de escrituras en la primera iteración.

## 2. Estado actual

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Frontend React + Vite | `IMPLEMENTADO` | [`package.json`](/home/diego/Projects/huginn/package.json:6), [`vite.config.ts`](/home/diego/Projects/huginn/vite.config.ts:1) | La app ya usa un stack moderno y apto para PWA. |
| Backend FastAPI sirviendo el build | `IMPLEMENTADO` | [`Dockerfile`](/home/diego/Projects/huginn/Dockerfile:35), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:743) | En producción el frontend se copia a `app/static/` y el backend sirve `index.html`. |
| PWA básica instalable | `FALTANTE` | Búsqueda repo-wide sin `manifest`, SW ni plugin PWA | No existe ningún artefacto PWA. |
| Offline seguro | `FALTANTE` | Sin `service worker`, sin fallback offline, sin caché declarada | La app depende totalmente de red activa. |
| Protección fuerte frente a updates | `FALTANTE` | Sin SW, sin aviso de nueva versión, sin limpieza de cachés | No existe estrategia de actualización controlada. |
| Base para futura PWA | `PARCIAL` | Serving same-origin, fallback SPA, assets hasheados de Vite | Hay una base útil, pero faltan piezas críticas y endurecimiento previo. |

## 3. Arquitectura encontrada

### 3.1 Frontend

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Framework | `IMPLEMENTADO` | `react` y `react-dom` en [`package-lock.json`](/home/diego/Projects/huginn/package-lock.json), declarados en [`package.json`](/home/diego/Projects/huginn/package.json:15) | React 19.2.7 resuelto en lockfile. |
| Build tool | `IMPLEMENTADO` | [`package.json`](/home/diego/Projects/huginn/package.json:10), [`vite.config.ts`](/home/diego/Projects/huginn/vite.config.ts:5) | Usa Vite 8.1.3. |
| CSS/UI | `IMPLEMENTADO` | [`src/styles.css`](/home/diego/Projects/huginn/src/styles.css:1) | Tailwind v4 y estilos custom. |
| Entry point | `IMPLEMENTADO` | [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:219), [`index.html`](/home/diego/Projects/huginn/index.html:13) | `createRoot(...).render(...)` desde `/src/main.tsx`. |
| Routing | `PARCIAL` | [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:17) | Hay routing manual en estado React; solo `/auth/callback` depende de URL real. No hay deep-linking general. |
| Routing profundo a board/studio/folder | `FALTANTE` | [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:48) | La vista actual vive en estado local; refrescar no conserva board/studio/folder. |

### 3.2 Backend y API

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Backend framework | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:86) | FastAPI 1 servicio. |
| Persistencia | `IMPLEMENTADO` | [`nodeboard-backend/app/database.py`](/home/diego/Projects/huginn/nodeboard-backend/app/database.py:9), [`nodeboard-backend/app/models.py`](/home/diego/Projects/huginn/nodeboard-backend/app/models.py:95) | SQLAlchemy 2.x + SQLite. |
| API principal | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:247), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:395), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:549) | Rutas para auth, studios, folders, boards, state. |
| Comunicación frontend/backend | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:19) | Todo via `fetch` a `/api/...` o `VITE_API_URL`. |
| Proxy dev | `IMPLEMENTADO` | [`vite.config.ts`](/home/diego/Projects/huginn/vite.config.ts:10) | `/api` proxied a `127.0.0.1:8001`. |
| CORS | `PARCIAL` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:88) | Configurable por `CORS_ORIGINS`, pero solo útil si hay cross-origin real. |
| Healthcheck | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:726) | `/api/health`. |

### 3.3 Railway y serving en producción

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Docker multi-stage | `IMPLEMENTADO` | [`Dockerfile`](/home/diego/Projects/huginn/Dockerfile:3) | Compila Vite y empaqueta backend Python. |
| Frontend y backend en mismo dominio | `IMPLEMENTADO` | [`Dockerfile`](/home/diego/Projects/huginn/Dockerfile:35), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:754) | El build se sirve desde el mismo proceso FastAPI. |
| Soporte `PORT` Railway | `IMPLEMENTADO` | [`nodeboard-backend/entrypoint.sh`](/home/diego/Projects/huginn/nodeboard-backend/entrypoint.sh:7) | Uvicorn escucha en `${PORT:-8001}`. |
| Volumen persistente | `PARCIAL` | [`Dockerfile`](/home/diego/Projects/huginn/Dockerfile:38), [`nodeboard-backend/app/database.py`](/home/diego/Projects/huginn/nodeboard-backend/app/database.py:17) | La app soporta `DATA_PATH=/data`, pero depende de configurar el volumen en Railway. |
| `railway.toml` | `FALTANTE` | No existe archivo | No hay configuración Railway declarativa en repo. |
| Dominio público exacto | `PARCIAL` | No aparece en repo | La arquitectura indica same-origin, pero el hostname público no es verificable desde código. |

### 3.4 Variables de entorno relevantes

| Variable | Estado | Evidencia | Motivo |
|---|---|---|---|
| `VITE_GOOGLE_CLIENT_ID` | `IMPLEMENTADO` | [`src/components/Login.tsx`](/home/diego/Projects/huginn/src/components/Login.tsx:3), [`Dockerfile`](/home/diego/Projects/huginn/Dockerfile:7) | Se inyecta al build frontend. |
| `VITE_API_URL` | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:8) | Permite API fuera de mismo origen. |
| `CORS_ORIGINS` | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:90) | Configura CORS. |
| `DATA_PATH` | `IMPLEMENTADO` | [`nodeboard-backend/app/database.py`](/home/diego/Projects/huginn/nodeboard-backend/app/database.py:17) | Ruta persistente recomendada para Railway. |
| `NODEBOARD_DB` | `IMPLEMENTADO` | [`nodeboard-backend/app/database.py`](/home/diego/Projects/huginn/nodeboard-backend/app/database.py:20) | Override legacy de DB. |
| `GOOGLE_CLIENT_ID/SECRET/CALLBACK_URL` | `IMPLEMENTADO` | [`nodeboard-backend/app/auth.py`](/home/diego/Projects/huginn/nodeboard-backend/app/auth.py:42) | OAuth backend. |
| Secrets comprometidos en repo | `RIESGO` | [`.env`](/home/diego/Projects/huginn/.env:1), [`nodeboard-backend/.env`](/home/diego/Projects/huginn/nodeboard-backend/.env:1) | Client secret de Google está versionado. Debe rotarse antes de cualquier rollout PWA. |

## 4. Elementos PWA existentes

| Elemento | Estado | Evidencia | Motivo |
|---|---|---|---|
| HTTPS en producción | `PARCIAL` | Despliegue Railway indicado por el proyecto | Railway normalmente sirve HTTPS, pero no está descrito en repo. |
| Build con assets versionados | `IMPLEMENTADO` | Vite build en [`package.json`](/home/diego/Projects/huginn/package.json:10) | Vite genera assets con hash, buenos para caché larga. |
| Fallback SPA | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:754) | Toda ruta no API devuelve `index.html`. |
| App shell razonable | `PARCIAL` | [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:46) | Hay una shell React, pero no navegación URL-driven ni offline. |
| Meta viewport | `IMPLEMENTADO` | [`index.html`](/home/diego/Projects/huginn/index.html:5) | Meta básica móvil presente. |
| Theme variables | `IMPLEMENTADO` | [`src/styles.css`](/home/diego/Projects/huginn/src/styles.css:3) | La app ya maneja dos temas y tokens visuales. |

## 5. Elementos faltantes

| Elemento | Estado | Evidencia | Motivo |
|---|---|---|---|
| `manifest.json` o `manifest.webmanifest` | `FALTANTE` | Búsqueda repo-wide sin archivo | No existe manifest. |
| Plugin PWA para Vite | `FALTANTE` | [`vite.config.ts`](/home/diego/Projects/huginn/vite.config.ts:1) | Solo usa `react()` y `tailwindcss()`. |
| Service worker | `FALTANTE` | Búsqueda repo-wide sin `sw.js`, `service-worker.js`, `navigator.serviceWorker` | No existe SW ni registro. |
| Workbox | `FALTANTE` | [`package.json`](/home/diego/Projects/huginn/package.json:15) | No hay dependencia relacionada. |
| Registro manual SW | `FALTANTE` | [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:1) | No hay `navigator.serviceWorker.register(...)`. |
| Estrategias de caché | `FALTANTE` | Sin SW y sin headers explícitos | No existe política formal para assets, HTML o API. |
| Iconos PWA 192/512 | `FALTANTE` | No hay `public/` ni assets PWA | No hay iconos instalables. |
| Iconos maskable | `FALTANTE` | No hay manifest ni iconos | Requisito importante para Android. |
| Apple touch icons | `FALTANTE` | [`index.html`](/home/diego/Projects/huginn/index.html:3) | No existe `<link rel="apple-touch-icon">`. |
| `theme-color` | `FALTANTE` | [`index.html`](/home/diego/Projects/huginn/index.html:3) | No existe meta `theme-color`. |
| `background_color`, `display`, `scope`, `start_url` | `FALTANTE` | Sin manifest | No configurado. |
| Screenshots / shortcuts | `FALTANTE` | Sin manifest | No definido. |
| Página offline | `FALTANTE` | Sin SW ni ruta offline | No existe fallback offline. |
| Aviso de actualización | `FALTANTE` | Sin SW | No existe detección de nueva versión. |
| Limpieza de cachés viejas | `FALTANTE` | Sin SW | No existe invalidación gestionada. |
| Detección online/offline | `FALTANTE` | Sin listeners `online/offline` | La UI no informa conectividad. |

### 5.1 Manifest recomendado para Huginn

Como no existe manifest actual, estos son los valores recomendados para una primera versión:

| Campo | Estado | Valor recomendado | Motivo |
|---|---|---|---|
| `name` | `FALTANTE` | `Huginn` o `Huginn Nodeboard` | Nombre visible en instalación. |
| `short_name` | `FALTANTE` | `Huginn` | Etiqueta corta en homescreen. |
| `description` | `FALTANTE` | `Pizarra visual para studios, boards y workflows.` | Descriptivo sin depender del marketing. |
| `start_url` | `FALTANTE` | `/` | La app hoy no soporta deep links estables a board. |
| `scope` | `FALTANTE` | `/` | Todo el producto se sirve bajo el mismo origen. |
| `display` | `FALTANTE` | `standalone` | Objetivo explícito del proyecto. |
| `orientation` | `FALTANTE` | `any` | El canvas puede beneficiarse de landscape; no conviene bloquear. |
| `theme_color` | `FALTANTE` | `#0F1117` | Coincide con tema oscuro por defecto en [`src/styles.css`](/home/diego/Projects/huginn/src/styles.css:4). |
| `background_color` | `FALTANTE` | `#0F1117` | Evita flash blanco en launch. |
| `icons` 192x192 | `FALTANTE` | PNG | Requisito de Android/desktop installability. |
| `icons` 512x512 | `FALTANTE` | PNG | Requisito de Android/desktop installability. |
| `maskable` | `FALTANTE` | Sí, al menos 192 y 512 | Mejora recorte e integración Android. |
| `screenshots` | `FALTANTE` | 2 desktop + 2 mobile | Mejora install prompt en Chromium. |
| `shortcuts` | `PARCIAL` | Opcional: `Abrir Huginn`, `Ir a Studios` | Útil, pero no crítico en v1. |

Observación de compatibilidad:

- `RIESGO`: con el serving actual, poner `manifest.webmanifest` en raíz no basta; hay que servirlo explícitamente para que no responda `index.html` desde el catch-all de FastAPI.
- `RECOMENDADO`: usar rutas relativas a `/` y no rutas absolutas dependientes del hostname Railway.

## 6. Riesgos críticos

| Riesgo | Estado | Evidencia | Motivo |
|---|---|---|---|
| `sw.js` y `manifest.webmanifest` hoy caerían en el catch-all SPA si se agregan sin rutas explícitas | `RIESGO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:745) | El backend solo monta `/assets`; cualquier otra ruta no API devuelve `index.html`. Un SW o manifest en raíz quedarían servidos con contenido/MIME incorrectos. |
| Canvas fuertemente basado en mouse | `RIESGO` | [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx:121), [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx:317), [`src/components/NodeCard.tsx`](/home/diego/Projects/huginn/src/components/NodeCard.tsx:62) | No usa `PointerEvent`; en móvil el comportamiento será incompleto o frágil. |
| Guardado por snapshot completo sin versionado ni control de concurrencia | `RIESGO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:102), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:565) | Reintentos, offline queue o respuestas fuera de orden pueden sobrescribir trabajo. |
| Credenciales OAuth versionadas | `RIESGO` | [`.env`](/home/diego/Projects/huginn/.env:1) | Es un problema de seguridad previo a cualquier PWA. |
| Cookie de sesión sin `Secure` explícito | `RIESGO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:277) | Para una app instalable y móvil conviene `Secure=True` en producción. |
| API privada podría cachearse mal si se añade SW genérico | `RIESGO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:33), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:247) | La app maneja datos privados por usuario; un runtime cache agresivo sería peligroso. |
| `VITE_API_URL` cross-origin rompería auth API por falta de `credentials: "include"` en `src/api.ts` | `RIESGO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:19), [`src/lib/auth-context.tsx`](/home/diego/Projects/huginn/src/lib/auth-context.tsx:24) | AuthProvider sí envía cookies explícitamente, pero el cliente API general no. |

## 7. Riesgos medios

| Riesgo | Estado | Evidencia | Motivo |
|---|---|---|---|
| `100vh` / `h-screen` en varias pantallas | `RIESGO` | [`src/components/Home.tsx`](/home/diego/Projects/huginn/src/components/Home.tsx:68), [`src/components/Login.tsx`](/home/diego/Projects/huginn/src/components/Login.tsx:21), [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx:307) | En iPhone/standalone puede producir saltos con barras del navegador y teclado virtual. |
| Grid fijo y paddings grandes en Home | `RIESGO` | [`src/components/Home.tsx`](/home/diego/Projects/huginn/src/components/Home.tsx:71), [`src/components/Home.tsx`](/home/diego/Projects/huginn/src/components/Home.tsx:172) | No parece diseñado primero para pantallas pequeñas. |
| Targets táctiles pequeños en puertos | `RIESGO` | [`src/components/NodeCard.tsx`](/home/diego/Projects/huginn/src/components/NodeCard.tsx:154) | Los dots de 12x12 no son adecuados para touch. |
| Menús dependientes de hover/mouse | `RIESGO` | [`src/components/Login.tsx`](/home/diego/Projects/huginn/src/components/Login.tsx:121), [`src/styles.css`](/home/diego/Projects/huginn/src/styles.css:63) | Parte de la experiencia depende de hover, pobre en móvil. |
| Deep links no preservados | `RIESGO` | [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:48) | La PWA abrirá `/`, no el último board, salvo que se agregue routing/restore. |
| Sin safe areas | `FALTANTE` | No hay `env(safe-area-inset-*)` en CSS | En iPhone standalone puede chocar con notch/home indicator. |

## 8. Compatibilidad con Railway

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Build + run en un contenedor | `IMPLEMENTADO` | [`Dockerfile`](/home/diego/Projects/huginn/Dockerfile:1) | Apto para Railway. |
| Start command con `$PORT` | `IMPLEMENTADO` | [`nodeboard-backend/entrypoint.sh`](/home/diego/Projects/huginn/nodeboard-backend/entrypoint.sh:8) | Correcto para Railway. |
| SPA fallback | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:754) | Compatible con serving de app web. |
| Manifest servido correctamente desde raíz | `FALTANTE` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:745) | Requiere nuevas rutas o static root adicional. |
| Service worker servido desde raíz correcta | `FALTANTE` | Misma evidencia | Igual problema que manifest. |
| MIME types explícitos para manifest/SW | `FALTANTE` | No hay configuración | Debe garantizarse `application/manifest+json` y `application/javascript`. |
| Headers cache-control para HTML/SW/assets | `FALTANTE` | No hay configuración explícita en backend | Railway por sí solo no resuelve la política correcta para PWA. |
| Dominio público y scope exacto verificable | `PARCIAL` | No aparece en repo | El scope recomendado sería `/`, pero falta validar hostname final. |

### 8.1 Headers recomendados

| Recurso | Estado | Header recomendado | Motivo |
|---|---|---|---|
| `index.html` | `FALTANTE` | `Cache-Control: no-cache` | Debe revalidarse para recoger nuevos builds. |
| `sw.js` | `FALTANTE` | `Cache-Control: no-cache` | El navegador debe poder detectar updates del SW. |
| `manifest.webmanifest` | `FALTANTE` | `Cache-Control: no-cache` | Cambios de iconos/nombre/start_url deben propagarse. |
| `/assets/*.js`, `/assets/*.css` hasheados | `FALTANTE` | `Cache-Control: public, max-age=31536000, immutable` | Son versionados por hash. |
| Iconos estáticos | `FALTANTE` | `Cache-Control: public, max-age=31536000, immutable` | Seguros para caché larga. |
| Fuentes self-hosted | `FALTANTE` | `Cache-Control: public, max-age=31536000, immutable` | Buen candidato a caché larga. |
| API privada autenticada | `FALTANTE` | `Cache-Control: private, no-store` | Evita caches compartidas o reuso indebido. |
| Auth responses | `FALTANTE` | `Cache-Control: no-store` | Sensibles por definición. |

### 8.2 Headers de seguridad recomendados

| Header | Estado | Recomendación |
|---|---|---|
| `Content-Security-Policy` | `FALTANTE` | Definir política estricta compatible con Vite build, fonts y OAuth. |
| `X-Frame-Options` o `frame-ancestors` | `FALTANTE` | Bloquear embedding no deseado. |
| `Referrer-Policy` | `FALTANTE` | `strict-origin-when-cross-origin` o más estricto. |
| `Permissions-Policy` | `FALTANTE` | Limitar capacidades no usadas. |
| `Strict-Transport-Security` | `PARCIAL` | Depende del edge de Railway; validar en producción. |

## 9. Compatibilidad móvil

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Uso básico en móvil | `PARCIAL` | Layouts con `min-h-screen`, grids y modales | Hay componentes que se adaptan parcialmente, pero no está claro que el canvas sea usable. |
| Pointer/touch events | `FALTANTE` | [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx:152), [`src/components/NodeCard.tsx`](/home/diego/Projects/huginn/src/components/NodeCard.tsx:62) | Todo está basado en `mousedown/mousemove/mouseup/contextmenu`. |
| Zoom/pan táctil | `FALTANTE` | [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx:101) | Solo wheel + mouse. No hay pinch ni drag táctil robusto. |
| Selección de nodos táctil | `PARCIAL` | [`src/components/NodeCard.tsx`](/home/diego/Projects/huginn/src/components/NodeCard.tsx:62) | El click simple puede funcionar, pero sin pointer un drag touch será incierto. |
| Edición de texto con teclado virtual | `PARCIAL` | Inputs y textareas existen | Puede funcionar, pero `h-screen/100vh` y canvas absoluto pueden interferir al abrir teclado. |
| Menús contextuales | `RIESGO` | [`src/components/NodeCard.tsx`](/home/diego/Projects/huginn/src/components/NodeCard.tsx:164) | Click derecho no existe de forma estándar en móvil. |
| Carga de imágenes | `PARCIAL` | [`src/components/Block.tsx`](/home/diego/Projects/huginn/src/components/Block.tsx:111) | `<input type="file" accept="image/*">` es compatible, pero el UX en canvas móvil no está resuelto. |
| Safe areas y standalone iOS | `FALTANTE` | Sin CSS dedicado | Debe agregarse antes de llamar estable a la experiencia móvil. |

## 10. Persistencia y funcionamiento offline

### 10.1 Persistencia actual

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Autosave | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:102) | Guarda automáticamente después de cambios. |
| Debounce | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:76) | `debounceMs = 800`. |
| Estado visual de guardado | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:4), [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx:489) | Muestra `cargando/guardando/guardado/error`. |
| Carga inicial de board | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:81) | `GET /api/boards/{id}` al montar. |
| Save por snapshot completo | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:106), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:565) | El frontend manda todo el board y el backend reemplaza todo. |

### 10.2 Riesgo de pérdida de datos

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Cola offline de escrituras | `FALTANTE` | Sin IndexedDB ni cola | No existe almacenamiento temporal confiable. |
| Retry seguro de escrituras | `FALTANTE` | Sin lógica de retry | Reintentar `PUT /state` ciegamente sería peligroso por snapshot total. |
| Versionado de board | `FALTANTE` | No hay `version`, `etag`, `If-Match` | No hay protección frente a carreras o múltiples clientes. |
| Protección al cerrar con cambios pendientes | `FALTANTE` | Sin `beforeunload` ni `pagehide` | El usuario puede cerrar antes del siguiente autosave. |
| Detección de desconexión | `FALTANTE` | Sin listeners `online/offline` | El usuario solo ve `error` tras fallar un save. |
| Resolución de conflictos multi-dispositivo | `FALTANTE` | Arquitectura actual de snapshot | El último `PUT` gana. |
| IDs temporales | `NO APLICA` | IDs generados cliente con `uid()` y persistidos | No hay temp IDs separados; el cliente ya crea IDs finales. |
| Seguridad de offline editing v1 | `RIESGO` | Arquitectura actual | No recomiendo cola offline ni edición offline como primera fase. |

### 10.3 Nivel de offline recomendado

| Nivel | Estado recomendado | Motivo |
|---|---|---|
| PWA instalable | `RECOMENDADO` | Bajo riesgo si solo se cachea app shell y assets. |
| PWA con lectura offline | `PARCIALMENTE RECOMENDADO` | Solo después de definir qué vistas privadas pueden persistirse de forma segura. |
| PWA con edición offline | `NO RECOMENDADO` | La persistencia actual por snapshot completo no soporta bien colas offline. |
| Sincronización offline completa | `NO RECOMENDADO` | Requiere rediseño de persistencia, idempotencia y resolución de conflictos. |

## 11. Autenticación y seguridad

| Punto | Estado | Evidencia | Motivo |
|---|---|---|---|
| Cookie de sesión `HttpOnly` | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:280) | Correcto. |
| `SameSite=Lax` | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:281) | Correcto para callback OAuth frontend/backend same-site. |
| `Secure` en cookie | `FALTANTE` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:277) | Debe activarse en producción. |
| Expiración de sesión | `IMPLEMENTADO` | [`nodeboard-backend/app/auth.py`](/home/diego/Projects/huginn/nodeboard-backend/app/auth.py:102), [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:120) | 7 días. |
| Renovación de sesión | `FALTANTE` | No existe refresh/sliding expiration | La sesión expira y luego retorna 401. |
| Logout | `IMPLEMENTADO` | [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:287), [`src/lib/auth-context.tsx`](/home/diego/Projects/huginn/src/lib/auth-context.tsx:45) | Borra sesión server-side y limpia estado cliente. |
| Auto-logout ante 401 | `IMPLEMENTADO` | [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:25), [`src/lib/auth-context.tsx`](/home/diego/Projects/huginn/src/lib/auth-context.tsx:55) | Útil al expirar sesión. |
| OAuth callback | `IMPLEMENTADO` | [`src/components/Login.tsx`](/home/diego/Projects/huginn/src/components/Login.tsx:6), [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:101) | Flujo browser-based funcionando. |
| Compatibilidad standalone | `PARCIAL` | OAuth usa `window.location.origin` | Bien para mismo dominio, pero debe validarse en PWA instalada móvil. |
| Cache de rutas sensibles | `FALTANTE` | Sin SW aún | La recomendación es `NetworkOnly` para `/api/auth/*` y respuestas privadas. |
| CSP | `FALTANTE` | Sin header o meta CSP | Debe definirse antes de abrir cache controlada y standalone. |
| Clickjacking protection | `FALTANTE` | Sin `X-Frame-Options` o `frame-ancestors` | Recomendado. |
| Riesgo XSS persistente por HTML libre | `PARCIAL` | Los bloques de texto son texto plano en [`src/components/Block.tsx`](/home/diego/Projects/huginn/src/components/Block.tsx:31) | No se renderiza HTML rico hoy; el riesgo es bajo mientras siga siendo texto. |

## 12. Estrategia de caché recomendada

### 12.1 Estrategia objetivo

Recomiendo una PWA basada en **`vite-plugin-pwa` con `injectManifest`** y un service worker custom con Workbox runtime routing. Motivo: Huginn es un editor autenticado con datos privados y no tolera un `generateSW` genérico que cachee demasiado.

### 12.2 Estrategias por recurso

| Recurso | Estrategia recomendada | Estado | Justificación |
|---|---|---|---|
| `/` y navegaciones HTML | `Network First` con timeout corto + fallback offline | `RECOMENDADO` | Evita servir `index.html` viejo tras deploy, pero mantiene una pantalla offline. |
| `index.html` | `Network First` | `RECOMENDADO` | Debe refrescarse rápido al desplegar nueva versión. |
| JS/CSS con hash (`/assets/*`) | `Cache First` + `immutable` | `RECOMENDADO` | Vite ya produce nombres versionados; ideal para precache. |
| Fuentes externas Google Fonts | `PARCIAL` | `RIESGO` | Hoy dependen de red externa desde [`index.html`](/home/diego/Projects/huginn/index.html:7). Mejor auto-hostearlas antes de PWA estable. |
| Iconos PWA y app icons | `Cache First` | `RECOMENDADO` | Son estáticos y seguros. |
| `manifest.webmanifest` | `Network First` o `Network Only` con `no-cache` | `RECOMENDADO` | Debe reflejar cambios de instalación sin quedarse obsoleto. |
| `sw.js` | `Network Only` con `Cache-Control: no-cache` | `RECOMENDADO` | El browser ya maneja su lifecycle; no debe cachearse agresivamente. |
| Imágenes estáticas del producto | `Cache First` | `RECOMENDADO` | Si se agregan assets públicos, pueden cachearse. |
| Imágenes subidas por usuario | `NO APLICA` | [`src/components/Block.tsx`](/home/diego/Projects/huginn/src/components/Block.tsx:123) | Hoy quedan embebidas como data URI dentro del JSON del board, no como URLs separadas. |
| `GET /api/auth/me` | `Network Only` | `RECOMENDADO` | Es privado y sensible a expiración de sesión. |
| `POST /api/auth/login`, `POST /api/auth/logout` | `Network Only` | `RECOMENDADO` | Nunca cachear. |
| `GET /api/studios`, `/folders`, `/boards`, `/boards/{id}` | `Network Only` en v1 | `RECOMENDADO` | Son datos privados y altamente dinámicos; mejor sacrificar offline data que arriesgar fugas o staleness. |
| `GET /api/boards/{id}/tags` | `Network Only` en v1 | `RECOMENDADO` | También es privado y derivado del board. |
| `PUT/PATCH/POST/DELETE /api/*` | `Network Only` | `RECOMENDADO` | Nunca interceptar para caché automática. |
| `/api/health` | `Network Only` | `RECOMENDADO` | Health no aporta valor offline. |

### 12.3 Reglas de exclusión obligatorias

- Excluir completamente de runtime cache: `/api/auth/*`, `POST|PUT|PATCH|DELETE /api/*`, cualquier respuesta con datos privados por usuario.
- No cachear respuesta HTML privada post-login si depende de sesión; cachear solo el shell genérico.
- No persistir offline boards completos en v1 salvo decisión explícita y cifrado/aislamiento revisados.

## 13. Estrategia de actualización recomendada

| Punto | Estado recomendado | Motivo |
|---|---|---|
| `skipWaiting` | `PARCIAL` | Úsese solo cuando el usuario confirme actualizar o cuando no haya cambios sin guardar. |
| `clientsClaim` | `PARCIAL` | Útil, pero no debe forzar takeover silencioso mientras el usuario edita. |
| Aviso “Nueva versión disponible” | `RECOMENDADO` | Debe aparecer discreto cuando el SW nuevo esté listo. |
| Recarga automática inmediata | `NO RECOMENDADO` | Riesgo de perder cambios locales antes del próximo autosave. |
| Flujo sugerido | `RECOMENDADO` | Detectar SW waiting, mostrar banner, si `status !== "guardando"` ofrecer “Actualizar ahora”; si está guardando, esperar confirmación y luego `skipWaiting` + reload controlado. |
| Limpieza de cachés obsoletas | `RECOMENDADO` | En `activate`, borrar caches por versión anterior. |
| Protección contra bundles incompatibles | `RECOMENDADO` | HTML `Network First`, assets hasheados precacheados, actualización solo cuando el usuario acepte. |

## 14. Nivel PWA recomendado para la primera versión

**Recomendación:** `PWA instalable + shell offline segura`, con este alcance:

- `IMPLEMENTADO` objetivo de fase 1:
  - Manifest válido.
  - Instalación escritorio/Android.
  - Modo standalone.
  - Service worker mínimo.
  - Precaching de assets estáticos versionados.
  - Offline fallback.
  - Banner de actualización.
  - Indicador online/offline.

- `NO RECOMENDADO` para fase 1:
  - Boards offline editables.
  - Cola de escrituras offline.
  - Sync multi-dispositivo offline.
  - Cache persistente de respuestas privadas de board.

### 14.1 Comportamiento de instalación recomendado

| Punto | Estado recomendado | Motivo |
|---|---|---|
| Nombre visible | `RECOMENDADO` | `Huginn` |
| Nombre corto | `RECOMENDADO` | `Huginn` |
| Pantalla inicial | `RECOMENDADO` | `/` con restauración opcional del último contexto si luego se agrega persistencia local segura |
| Deep links | `PARCIAL` | No soportarlos en v1 más allá de `/auth/callback`, o implementarlos correctamente antes de exponerlos |
| Inicio sin conexión | `RECOMENDADO` | Mostrar offline fallback con mensaje claro: “Huginn necesita conexión para abrir o sincronizar tus boards” |
| Último studio/board al abrir | `PARCIAL` | Solo si se agrega restore local sin esconder estados desincronizados |

## 15. Plan de implementación por fases

### Fase 0 — Correcciones previas

- `RIESGO`: rotar y retirar secretos de [`.env`](/home/diego/Projects/huginn/.env:1) y [`nodeboard-backend/.env`](/home/diego/Projects/huginn/nodeboard-backend/.env:1).
- `RIESGO`: endurecer cookie de sesión con `Secure` en producción.
- `RIESGO`: definir serving explícito para `manifest.webmanifest`, `sw.js`, iconos y offline page; hoy el catch-all los rompería.
- `RIESGO`: revisar `src/api.ts` para credenciales si `VITE_API_URL` se usa cross-origin.
- `RIESGO`: empezar migración de interacciones del canvas de mouse a pointer events.
- `PARCIAL`: reducir dependencia en Google Fonts externas, idealmente self-host.

### Fase 1 — PWA instalable

- `FALTANTE`: agregar `manifest.webmanifest`.
- `FALTANTE`: crear iconos 192, 512 y maskable.
- `FALTANTE`: agregar `theme-color`, `apple-touch-icon`, `mobile-web-app-capable` y metadatos iOS necesarios.
- `FALTANTE`: servir manifest/SW/iconos desde raíz correcta.
- `FALTANTE`: registrar SW.

### Fase 2 — Caché de aplicación

- `FALTANTE`: `vite-plugin-pwa` con `injectManifest`.
- `FALTANTE`: precache de JS/CSS hasheados e iconos.
- `FALTANTE`: `Network First` para HTML con offline fallback.
- `FALTANTE`: banner de nueva versión.
- `FALTANTE`: limpieza de caches por versión.

### Fase 3 — Resiliencia de red

- `FALTANTE`: indicador online/offline.
- `FALTANTE`: protección visual cuando `autosave` falla.
- `FALTANTE`: warning antes de cerrar si hay cambios pendientes.
- `FALTANTE`: política clara de no guardar offline y no reintentar escrituras automáticamente.

### Fase 4 — Offline avanzado

Solo si la arquitectura cambia:

- `FALTANTE`: IndexedDB.
- `FALTANTE`: cola de operaciones idempotentes o modelo CRDT/event sourcing.
- `FALTANTE`: versionado por board.
- `FALTANTE`: resolución de conflictos multi-cliente.

## 16. Archivos que probablemente deberán modificarse

- [`index.html`](/home/diego/Projects/huginn/index.html:1)
- [`vite.config.ts`](/home/diego/Projects/huginn/vite.config.ts:1)
- [`src/main.tsx`](/home/diego/Projects/huginn/src/main.tsx:1)
- [`src/NodeBoard.tsx`](/home/diego/Projects/huginn/src/NodeBoard.tsx:101)
- [`src/components/Login.tsx`](/home/diego/Projects/huginn/src/components/Login.tsx:5)
- [`src/components/Home.tsx`](/home/diego/Projects/huginn/src/components/Home.tsx:68)
- [`src/components/NodeCard.tsx`](/home/diego/Projects/huginn/src/components/NodeCard.tsx:142)
- [`src/styles.css`](/home/diego/Projects/huginn/src/styles.css:37)
- [`src/api.ts`](/home/diego/Projects/huginn/src/api.ts:19)
- [`nodeboard-backend/app/main.py`](/home/diego/Projects/huginn/nodeboard-backend/app/main.py:743)
- [`nodeboard-backend/app/auth.py`](/home/diego/Projects/huginn/nodeboard-backend/app/auth.py:102)
- [`Dockerfile`](/home/diego/Projects/huginn/Dockerfile:35)

Archivos nuevos probables:

- `public/manifest.webmanifest` o equivalente servido desde raíz
- `public/icons/*`
- `src/sw.ts` o `src/service-worker.ts`
- `src/offline.html` o `public/offline.html`
- util de actualización y estado de conectividad

## 17. Dependencias que probablemente deberán agregarse

| Dependencia | Estado | Motivo |
|---|---|---|
| `vite-plugin-pwa` | `RECOMENDADO` | Mejor integración con Vite para build + manifest + SW. |
| `workbox-window` | `RECOMENDADO` | Útil para detectar updates y coordinar el banner de nueva versión. |
| Workbox runtime modules | `PARCIAL` | Pueden venir transitivamente con `vite-plugin-pwa`, pero la estrategia debe confirmarse al instalar. |

No recomiendo un service worker manual “crudo” como primera opción porque Huginn necesita control fino, pero también integración cómoda con Vite.

## 18. Plan de pruebas

### Funcionales y PWA

- `FALTANTE`: Lighthouse PWA en build de producción.
- `FALTANTE`: instalación en Chrome escritorio.
- `FALTANTE`: instalación en Android Chrome.
- `FALTANTE`: validación en iPhone Safari standalone.
- `FALTANTE`: apertura en modo standalone con sesión activa.
- `FALTANTE`: apertura sin conexión mostrando fallback offline.
- `FALTANTE`: navegación offline al menos hasta shell y pantalla explicativa.

### Actualizaciones

- `FALTANTE`: deploy A -> abrir app -> deploy B -> verificar banner de actualización.
- `FALTANTE`: editar board durante update waiting -> no recargar hasta confirmar.
- `FALTANTE`: aceptar update -> recarga controlada sin bundles mixtos.
- `FALTANTE`: verificación de borrado de caches antiguas.

### Persistencia y red

- `FALTANTE`: desconexión mientras `status=guardando`.
- `FALTANTE`: cierre de pestaña antes de que corra el debounce de 800 ms.
- `FALTANTE`: backend caído durante edición.
- `FALTANTE`: reconexión tras error de save.
- `FALTANTE`: múltiples tabs del mismo board.
- `FALTANTE`: dos dispositivos con la misma cuenta editando el mismo board.
- `FALTANTE`: duplicación accidental de requests al reconectar.

### Seguridad y auth

- `FALTANTE`: expiración de sesión estando la app abierta.
- `FALTANTE`: logout con datos previamente vistos y cacheados.
- `FALTANTE`: asegurar que `/api/auth/*` y `/api/boards/*` no quedan en caches públicas.
- `FALTANTE`: revisión de CSP, clickjacking y cabeceras.

### Móvil

- `FALTANTE`: drag/pan/zoom táctil en Android.
- `FALTANTE`: edición de texto con teclado virtual.
- `FALTANTE`: menú de puertos y color en touch.
- `FALTANTE`: notch/safe areas en iPhone.
- `FALTANTE`: portrait y landscape.

## 19. Criterios de aceptación

La primera versión PWA debería considerarse aceptable solo si cumple:

1. `IMPLEMENTADO`: instalación desde Chrome desktop y Android.
2. `IMPLEMENTADO`: apertura standalone con icono, nombre y colores correctos.
3. `IMPLEMENTADO`: `manifest.webmanifest` válido, iconos 192/512 y maskable.
4. `IMPLEMENTADO`: `service worker` registrado y servido desde raíz correcta.
5. `IMPLEMENTADO`: HTML y SW actualizan sin quedar pegados a versiones viejas.
6. `IMPLEMENTADO`: assets hasheados se sirven desde caché sin romper deploys.
7. `IMPLEMENTADO`: existe offline fallback claro.
8. `IMPLEMENTADO`: `/api/auth/*` y escrituras `/api/*` nunca se cachean.
9. `IMPLEMENTADO`: no hay pérdida silenciosa de cambios por actualización automática.
10. `IMPLEMENTADO`: el canvas es al menos usable en móvil para la interacción objetivo de la primera release, o se declara explícitamente soporte móvil limitado.

## 20. Conclusión

Huginn **no está listo todavía** para una PWA completa, pero sí está en una posición razonable para una **primera versión instalable y segura** si se corrigen antes varios puntos estructurales.

La arquitectura recomendada no es offline-first. Para este producto, el orden correcto es:

1. corregir seguridad, serving y experiencia móvil mínima;
2. agregar manifest + SW con caché solo de assets estáticos;
3. incorporar fallback offline, detección de conectividad y actualización controlada;
4. posponer edición offline hasta rediseñar persistencia y sincronización.

Si se respetan esas fases, Huginn puede convertirse en una PWA sólida sin comprometer el dato del usuario. Si se intenta saltar directamente a “offline editing” con la arquitectura actual de snapshot completo, el riesgo de pérdida, duplicación o sobrescritura de trabajo es alto.
