# Resumen — Logout automático por sesión expirada

> Fecha: 2026-07-07
> Tests: frontend 18/18, backend 33/33.

---

## Cambios

### `src/api.ts`

- Se agregó variable privada `_unauthorizedHandler` a nivel de módulo.
- Se exportó `registerUnauthorizedHandler(fn: (() => void) | null)` para que `AuthProvider` registre su `logout` como handler.
- `request()` ahora, cuando recibe `401`, llama al handler registrado (si existe) **antes** de hacer `throw`. Esto asegura que `logout()` dispare `setUser(null)` y el gate global en `AppInner` muestre `Login`, todo sin recargar la página.
- Los `.catch()` existentes en Home, StudioView, FolderView y useBoardPersistence siguen ejecutándose después — el logout global es un side effect adicional, no un reemplazo.

### `src/lib/auth-context.tsx`

- Import `registerUnauthorizedHandler` desde `../api`.
- Nuevo `useEffect` en `AuthProvider` que registra `logout` al montar y lo desregistra (setea `null`) al desmontar.

---

## Arquitectura

```
request() en api.ts
  │
  ├─ status === 401 ──→ _unauthorizedHandler?.() ──→ logout() en AuthContext
  │                                                      │
  │                                                      └─ setUser(null) → AppInner gate → Login
  │
  └─ throw new Error(...) ──→ .catch() local en cada componente
                                  (setea arrays vacíos / estado "error")
```

Sin dependencia circular: `api.ts` no importa `auth-context.tsx`, solo recibe un callback. `auth-context.tsx` importa `registerUnauthorizedHandler` de `api.ts`.
