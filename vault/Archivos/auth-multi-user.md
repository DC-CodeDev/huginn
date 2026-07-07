---
tags: [backend, auth, models, schema]
---

# Autenticación multi-usuario (Google OAuth) — Fase 2

## Modelo de datos

### Tabla `users`

| Columna        | Tipo               | Notas                                |
| -------------- | ------------------ | ------------------------------------ |
| `id`           | String(32) PK      | uuid4.hex                            |
| `email`        | String(320) UNIQUE | Correo de Google                     |
| `name`         | String(200)        | Nombre del usuario                   |
| `avatar_url`   | String(1000)       | Foto de perfil de Google             |
| `auth_provider`| String(50)         | Hoy solo `"google"`, extensible     |
| `created_at`   | DateTime(tz)       |                                      |
| `updated_at`   | DateTime(tz)       |                                      |

### Tabla `sessions`

| Columna      | Tipo               | Notas                                |
| ------------ | ------------------ | ------------------------------------ |
| `id`         | String(32) PK      | uuid4.hex                            |
| `user_id`    | FK → users.id      | CASCADE on delete                    |
| `expires_at` | DateTime(tz)       | 7 días desde creación                |
| `created_at` | DateTime(tz)       |                                      |

### Tabla `studios` (modificada)

| Columna      | Tipo               | Notas                                |
| ------------ | ------------------ | ------------------------------------ |
| `user_id`    | FK → users.id      | NUEVA: obligatoria, CASCADE on delete|
| `created_at` | DateTime(tz)       | NUEVA: default _now()                |

Folder, Board, Node, Edge **no** tienen `user_id` propio. Heredan ownership por cadena de FKs hasta `Studio.user_id`.

## Flujo de autenticación

1. Frontend redirige al usuario a Google OAuth para obtener un `authorization_code`.
2. Frontend envía `POST /api/auth/login {code}` al backend.
3. `verify_google_token()` en `app/auth.py` intercambia el code por tokens y extrae `email`, `name`, `avatar_url`.
4. Backend busca o crea `User` por `email + auth_provider="google"`.
5. Se crea una `Session` con `expires_at = now + 7 días`.
6. Se setea cookie httpOnly `session=<session_id>` con `SameSite=Lax`.
7. En cada request protegido, `get_current_user()` en `app/main.py` lee la cookie, busca la sesión en DB, valida expiración, y resuelve el `User`.
8. `POST /api/auth/logout` borra la sesión y limpia la cookie.
9. `GET /api/auth/me` devuelve el usuario actual.

## Variables de entorno

| Variable               | Descripción                              |
| ---------------------- | ---------------------------------------- |
| `GOOGLE_CLIENT_ID`     | Client ID de Google OAuth                |
| `GOOGLE_CLIENT_SECRET` | Client Secret de Google OAuth            |
| `GOOGLE_CALLBACK_URL`  | URL de callback (localhost en desarrollo)|

## Ownership (cadena de FKs)

Toda ruta de negocio usa helpers que unen hasta `Studio.user_id`:

- `_get_board()` → `Board → Studio → user_id`
- `_get_studio()` → `Studio → user_id`
- `_get_folder()` → `Folder → Studio → user_id`
- `_get_owned_node()` → `Node → Board → Studio → user_id`
- `_get_owned_edge()` → `Edge → Board → Studio → user_id`

Si el recurso no pertenece al usuario autenticado → **404** (nunca 403).

## Archivos tocados

- `nodeboard-backend/app/models.py` — User, Session, Studio (user_id + created_at)
- `nodeboard-backend/app/schemas.py` — LoginRequest, UserOut, StudioOut (user_id, created_at)
- `nodeboard-backend/app/auth.py` — verify_google_token(), resolve_user_from_session(), create_session()
- `nodeboard-backend/app/main.py` — get_current_user(), login(), logout(), me(), ownership en todas las rutas
- `nodeboard-backend/requirements.txt` — google-auth, requests
- `nodeboard-backend/migrations/versions/e847afe87df5_*.py` — migración autogenerada (NO aplicada aún)
- `nodeboard-backend/tests/test_multi_user.py` — 19 tests de aislamiento multi-usuario
- `nodeboard-backend/tests/test_tags_label.py` — actualizado para pasar `current_user`

## Convención: datetimes naive-UTC (importante)

**Problema detectado:** SQLite no implementa `DateTime(timezone=True)` de SQLAlchemy.
Al leer un datetime aware desde SQLite, el dialecto lo devuelve como naive (sin zona
horaria), causando `TypeError: can't compare offset-naive and offset-aware datetimes`
al compararlo contra `datetime.now(timezone.utc)` en `get_current_user()` y
`resolve_user_from_session()`.

**Decisión:** Se eliminó `timezone=True` de todas las columnas `DateTime` del proyecto
(User, Session, Studio, Board) y se adoptó la convención:

> **Todos los datetimes guardados en la BD son naive pero representan SIEMPRE UTC.**
> Nunca usar `datetime.now()` a secas (devuelve hora local del sistema) ni
> `datetime.now(timezone.utc)` directo (aware). Usar siempre:
> `datetime.now(timezone.utc).replace(tzinfo=None)`

**Archivos modificados:**
- `models.py` — `_now()` helper, y todas las columnas DateTime perdieron `timezone=True`
- `auth.py` — `create_session()` y `resolve_user_from_session()` usan `.replace(tzinfo=None)`
- `main.py` — `get_current_user()` idem
- `migrations/versions/1f621998aecf_remove_timezone_from_datetime_columns.py` — migración

**Advertencia para código futuro:** Cualquier nuevo código que cree o compare fechas
contra estas columnas debe usar la misma forma naive-UTC. NO usar aware datetimes
en estas columnas.

## Migración

- `e847afe87df5` — usuarios, sesiones, studio user_id + created_at
- `1f621998aecf` — elimina `timezone=True` de todas las columnas DateTime
  (no-op en SQLite, necesaria para compatibilidad con PostgreSQL etc.)

La aplicación aplica ambas en startup via lifespan.

## Pendiente (siguiente prompt)

- Frontend: pantalla de login, contexto de auth, enviar cookie en requests.
