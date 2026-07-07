# Prueba de persistencia — Railway + SQLite

## Contexto

La aplicación Huginn desplegada en Railway perdía todos los datos en cada deploy porque la base de datos SQLite se creaba en `/app/nodeboard.db` (filesystem efímero del contenedor) en lugar de en `/data/nodeboard.db` (volumen persistente).

## Corrección aplicada

Se configuró la variable de entorno `DATA_PATH=/data` en Railway y se montó un volumen persistente en `/data`.

La función `get_database_url()` en `app/database.py` resuelve la ruta así:

```
DATA_PATH=/data → sqlite:////data/nodeboard.db → /data/nodeboard.db ✅
```

## Verificación

Para confirmar que la persistencia funciona correctamente después del fix:

```bash
# 1. Conectarse al shell del contenedor en Railway
# 2. Verificar la variable de entorno
echo $DATA_PATH
# → /data

# 3. Verificar que la DB está en el volumen
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM users;"
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM studios;"
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM boards;"

# 4. Hacer un deploy de prueba (push un cambio trivial)
# 5. Después del deploy, reconectarse y verificar que los conteos son los mismos
```

## Resultado esperado

| Antes | Después |
|-------|---------|
| DB en `/app/nodeboard.db` (efímero) | DB en `/data/nodeboard.db` (persistente) |
| Datos desaparecen en cada deploy | Datos sobreviven entre deploys |
| Sin errores visibles | Log de inicio confirma ruta |

## Referencias

- [[RAILWAY_DATA_LOSS_AUDIT.md]] — auditoría completa
- [[Archivos/nodeboard-backend/app/database.py.md]] — resolución de ruta
- `Dockerfile` — `RUN mkdir -p /data`
