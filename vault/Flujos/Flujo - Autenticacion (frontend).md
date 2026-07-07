# Contexto de Autenticación (frontend) — Fase 2

## Archivos tocados

- `src/lib/auth-context.tsx` — **NUEVO**: AuthProvider, useAuth hook
- `src/components/Login.tsx` — **NUEVO**: Login page + AuthLoader
- `src/components/ProfileMenu.tsx` — **MODIFICADO**: recibe `user` y `onLogout`
- `src/main.tsx` — **MODIFICADO**: envuelve con AuthProvider, ruteo condicional

## AuthContext (`src/lib/auth-context.tsx`)

Expone:

| Prop      | Tipo       | Descripción                                         |
| --------- | ---------- | --------------------------------------------------- |
| `user`    | `User \| null` | Usuario autenticado o `null` si no hay sesión      |
| `loading` | `bool`     | `true` mientras se resuelve la llamada inicial a /me |
| `login`   | `(code: string) => Promise<void>` | Envía code a `/api/auth/login` y setea el user |
| `logout`  | `() => Promise<void>` | POST a `/api/auth/logout`, limpia el user      |

### User (tipo compartido)

```typescript
interface User {
  id: string
  email: string
  name: string
  avatar_url: string
}
```

### Ciclo de vida

1. Al montar, `fetch("/api/auth/me", { credentials: "include" })` resuelve si hay cookie de sesión.
2. Si la respuesta es 401 → `user = null`.
3. `loading = true` → spinner. `loading = false` → Login si no hay user, app si hay.

## Login (`src/components/Login.tsx`)

- Card centrada con icono de nodo, título "Huginn", subtítulo, y botón "Sign in with Google".
- El botón es un `<a>` que redirige a `https://accounts.google.com/o/oauth2/v2/auth` con:
  - `client_id` de `VITE_GOOGLE_CLIENT_ID`
  - `redirect_uri = ${window.location.origin}/auth/callback`
  - `response_type=code`
  - `scope=openid email profile`
- Si falta `VITE_GOOGLE_CLIENT_ID`, muestra un mensaje de error en lugar del login.
- Incluye `AuthLoader`: spinner centrado (usado durante la carga inicial y en el callback).

## Callback de Google (`/auth/callback`)

En `main.tsx`, `AppInner` detecta:

```typescript
window.location.pathname === "/auth/callback" && URLSearchParams.has("code")
```

En ese caso renderiza `CallbackHandler`, que:
1. Extrae `?code=` de la URL.
2. Reemplaza la URL a `/` (sin recargar) para ocultar el code.
3. POSTea `{ code }` a `/api/auth/login` con `credentials: "include"`.
4. En éxito, setea el usuario en el contexto → la app muestra Home automáticamente.
5. En error, logea a console (usuario ve pantalla de error — mejora futura).

## Ruteo condicional (en `AppInner`)

Secuencia exacta (cada return es terminal):

1. `loading === true` → `AuthLoader` (spinner centrado, sobre fondo).
2. URL es `/auth/callback?code=...` → `CallbackHandler` (procesa code, no renderiza ni Login ni Home).
3. `user === null` → `Login` (no hay sesión activa).
4. `user` existe → render normal (Home/Studio/Folder/Board según `view` state).

**No hay react-router.** El estado de vista es un discriminated union `View` en `main.tsx`. Una vez autenticado, la navegación entre vistas y el callback redirigen al Home vía el mismo mecanismo de ruteo — no hay redirect hardcodeado.

## ProfileMenu

Ahora recibe:
- `user: User` — muestra nombre real y email en el header del menú
- `onLogout: () => void` — dispara logout desde el contexto

El botón cambió de "Cerrar perfil" a "Cerrar sesión" y llama `onLogout()` antes de cerrar el menú.

## Variables de entorno (frontend)

Agregar al `.env` en la raíz del proyecto:

```
VITE_GOOGLE_CLIENT_ID=700161543471-xxxxx.apps.googleusercontent.com
VITE_API_URL=                          # opcional, defaults a ""
```

## Pruebas

```
npm test          → 18 tests pasan (vitest)
npx tsc --noEmit  → 0 errores
```

Los 18 E2E que hoy fallan por auth requerida quedan fuera de alcance — se retoman en paso aparte.
