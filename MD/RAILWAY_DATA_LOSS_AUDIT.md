# Auditoría de pérdida total de datos en Railway

> ⚠️ Documento de auditoría — no modificar código hasta completar todas las verificaciones.

---

## A. Resumen ejecutivo

| Elemento | Valor |
|----------|-------|
| **Causa más probable** | La variable de entorno `DATA_PATH` **no está configurada** en Railway. La aplicación cae al default `sqlite:///./nodeboard.db`, que resuelve a `/app/nodeboard.db` — dentro del filesystem **efímero** del contenedor. |
| **Nivel de certeza** | **Alto** (≥90 %). El código tiene un fallback silencioso a ruta relativa, y no hay evidencia en el repo de que `DATA_PATH` se configure en Railway. |
| **Impacto** | Pérdida total de datos en cada deploy. Es equivalente a no tener persistencia. |
| **Riesgo actual** | **Crítico**. Cada `git push` que redespliegue destruye todos los datos. La aplicación funciona pero todo lo creado se pierde. |
| **Recuperable** | Sí, si la base aún existe en el contenedor actual (antes del próximo deploy). |

---

## B. Ruta efectiva de datos

### Resolución de la ruta final de SQLite

La función `get_database_url()` en `nodeboard-backend/app/database.py:9-20` implementa esta precedencia:

```
  1. DATA_PATH=/data            → sqlite:////data/nodeboard.db    → /data/nodeboard.db   ✅ persistente
  2. NODEBOARD_DB=sqlite:///... → exactamente lo que indique      → ruta arbitraria      ⚠️ depende del valor
  3. (ninguna)                  → sqlite:///./nodeboard.db        → /app/nodeboard.db     ❌ efímero
```

### Tabla de resolución

| Elemento | Valor encontrado | Fuente |
|----------|-----------------|--------|
| Working directory (Docker) | `/app` | `Dockerfile:26` — `WORKDIR /app` |
| `DATA_PATH` | No definida (Railway) | Sin evidencia en repo de que se configure |
| `NODEBOARD_DB` | No definida (Railway) | Sin evidencia en repo de que se configure |
| DB URL | `sqlite:///./nodeboard.db` | `database.py:20` — default cuando no hay `DATA_PATH` ni `NODEBOARD_DB` |
| Ruta final DB | **`/app/nodeboard.db`** | Resolución: `WORKDIR=/app` + ruta relativa `./nodeboard.db` |
| Directorio persistente esperado | `/data` | `Dockerfile:38-42` (se crea `mkdir -p /data`, pero no se usa si `DATA_PATH` no existe) |
| Mount path Railway esperado | `/data` | Documentado en `Dockerfile:38-41` (comentario), pero no verificado |
| Usuario del proceso | `root` | `Dockerfile` — no hay instrucción `USER`, el contenedor corre como root |
| Permisos esperados | root puede leer/escribir `/data` y `/app` | Cualquier directorio creado por Dockerfile es propiedad de root |

### Evidencia de código

**`nodeboard-backend/app/database.py:9-20`:**
```python
def get_database_url() -> str:
    data_path = os.getenv("DATA_PATH")
    if data_path:
        return f"sqlite:///{Path(data_path) / 'nodeboard.db'}"
    return os.getenv("NODEBOARD_DB", "sqlite:///./nodeboard.db")
```

Línea 18: si `DATA_PATH` está definida → usa `/data/nodeboard.db`.
Línea 20: si `DATA_PATH` NO está → usa `NODEBOARD_DB`, y si esta tampoco → **fallback silencioso a ruta relativa**.

**`Dockerfile:26`:**
```dockerfile
WORKDIR /app
```

**`Dockerfile:38-42`:**
```dockerfile
# Directorio para volúmenes persistentes (ej. SQLite). En Railway se setea
# DATA_PATH=/data y se monta un Volume en /data para que los datos sobrevivan
# entre deploys. En desarrollo local DATA_PATH no está definida y se usa el
# default relativo (./nodeboard.db).
RUN mkdir -p /data
```

El comentario dice exactamente lo que debe hacerse, pero no hay `ENV DATA_PATH=/data` en el Dockerfile ni evidencia de que se configure en Railway. La línea `RUN mkdir -p /data` no sirve de nada si el código nunca escribe allí.

**`nodeboard-backend/app/main.py:96-100` (lifespan):**
```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = Config(_ALEMBIC_CFG)
    command.upgrade(cfg, "head")
    yield
```

**`nodeboard-backend/entrypoint.sh`:**
```sh
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8001}"
```

Ambos ejecutan `alembic upgrade head`, que a su vez llama a la misma `get_database_url()` (via `migrations/env.py:29-30`). No crean ni borran datos — solo aplican migraciones.

---

## C. Flujo de inicialización (inicio del contenedor a apertura de DB)

```
1. Railway inicia contenedor desde la imagen Docker
2. Se ejecuta: CMD ["/app/entrypoint.sh"]
3. entrypoint.sh: alembic upgrade head
   └─ migrations/env.py:29 → import app.database → get_database_url()
      └─ os.getenv("DATA_PATH") → None (no configurada)
         └─ os.getenv("NODEBOARD_DB") → None (no configurada)
            └─ default: "sqlite:///./nodeboard.db"
               └─ SQLAlchemy crea engine apuntando a /app/nodeboard.db
   └─ Alembic busca la tabla alembic_version
      └─ Si no existe → la BD acaba de crearse vacía → aplica las 3 migraciones
      └─ Si existe → compara versiones → aplica migraciones faltantes (si hay)
4. entrypoint.sh: exec uvicorn app.main:app
   └─ FastAPI importa app.main → import app.database (ya cacheado, mismo engine)
   └─ lifespan: alembic upgrade head (segunda vez, no-op)
   └─ Rutas disponibles
5. Usuario se autentica → se crea user + session en /app/nodeboard.db
6. Usuario crea studios, folders, boards → todo en /app/nodeboard.db
7. Siguiente deploy: Railway destruye el contenedor
   └─ /app/ se pierde → /app/nodeboard.db desaparece
   └─ Nuevo contenedor → paso 3 → BD vacía
```

### ¿El startup borra o reemplaza datos?

**No.** No hay `drop_all`, `init_db`, `seed`, `reset`, `unlink`, `remove`, `rm` de bases de datos, ni lógica destructiva en ningún archivo de producción. Las migraciones son puramente aditivas (crear tablas, agregar columnas). El "borrado" ocurre porque **cada deploy crea una BD nueva en una ruta efímera**.

### Diferenciación clara:

| Acción | ¿Ocurre? | ¿Destructivo? |
|--------|----------|---------------|
| `Base.metadata.create_all()` | ❌ No (solo en tests) | — |
| `alembic upgrade head` | ✅ Sí (entrypoint + lifespan) | **No**. Crea tablas faltantes, nunca borra datos. |
| `drop_all()` | ❌ No | — |
| Seed / init_db | ❌ No | — |
| Delete / reset de datos | ❌ No | — |

---

## D. Evidencias detalladas

### D1. No existe configuración Railway en el repositorio

```bash
$ find . -name "railway.toml" -o -name "railway.json" 2>/dev/null
# (vacio)
```

No hay `railway.toml`, `railway.json`, ni ningún archivo de configuración Railway. Toda la configuración se hace desde el dashboard de Railway, y no hay documentación vinculante en el repo que indique qué variables se configuraron.

### D2. No existe `.dockerignore`

```bash
$ find . -name ".dockerignore" 2>/dev/null
# (vacio)
```

Ausencia total de `.dockerignore`. Esto significa que `COPY nodeboard-backend/ .` en el `Dockerfile:33` copia **todo** el contenido del directorio `nodeboard-backend/` del contexto de build, incluyendo:

- `*.db` (si existe en el contexto)
- `*.sqlite`
- `.env` (si existe)
- `.venv/` (si existe)
- `__pycache__/`

En Railway, el contexto de build es un checkout limpio de git (sin `.db` local), por lo que esto no inyecta una DB. Pero en builds locales sí.

### D3. La base de datos local `nodeboard-backend/nodeboard.db` existe pero no está en git

```bash
$ ls -la nodeboard-backend/nodeboard.db
-rw-r--r-- 1 usuario usuario 104K nodeboard-backend/nodeboard.db

$ git ls-files nodeboard-backend/nodeboard.db
# (vacio — no está trackeado)
```

El `.gitignore` ignora `nodeboard-backend/*.db`, por lo que la DB local no entra a Railway (build desde git). Sin embargo, podría entrar a imágenes Docker construidas localmente.

### D4. El Dockerfile no setea `DATA_PATH` ni `NODEBOARD_DB`

```dockerfile
# Dockerfile — NO hay:
# ENV DATA_PATH=/data
# ENV NODEBOARD_DB=sqlite:////data/nodeboard.db
```

Toda la configuración de entorno depende exclusivamente de las variables que el usuario configure en Railway.

### D5. La aplicación usa el mismo engine para todo

No hay archivos auxiliares. Los datos principales están **todos** en la misma base SQLite:

| Tabla | Propósito | ¿En SQLite? |
|-------|-----------|-------------|
| `users` | Usuarios | ✅ |
| `sessions` | Sesiones de autenticación | ✅ |
| `studios` | Studios | ✅ |
| `folders` | Carpetas | ✅ |
| `boards` | Tableros | ✅ |
| `nodes` | Nodos del canvas | ✅ (JSON columns) |
| `edges` | Aristas del canvas | ✅ |
| `alembic_version` | Control de migraciones | ✅ |

No hay archivos JSON, imágenes externas, uploads, ni otros archivos fuera de la DB. Las imágenes en bloques de tipo `image` se guardan como base64 data URIs dentro del JSON de la columna `blocks` de la tabla `nodes`. Todo está en el mismo archivo `.db`.

---

## E. Hipótesis

| # | Hipótesis | Estado | Evidencia |
|---|-----------|--------|-----------|
| 1 | El volumen de Railway no está creado. | **Posible** | No verificable desde el repo. Debe comprobarse en el dashboard de Railway. |
| 2 | El volumen está creado, pero conectado a otro servicio. | **Posible** | No verificable desde el repo. |
| 3 | El volumen está montado en una ruta diferente de la usada por Huginn. | **Posible** | Si el mount path es `/data` pero la app escribe en `/app/nodeboard.db` por falta de `DATA_PATH`. |
| 4 | `DATA_PATH` no está configurado. | **Altamente probable** | No hay evidencia en el repo. Es la causa más consistente con la pérdida total. |
| 5 | `DATA_PATH` está configurado, pero el código lo ignora. | **Descartada** | `database.py:17-19` usa `DATA_PATH` correctamente. |
| 6 | `NODEBOARD_DB` sobrescribe a `DATA_PATH`. | **Descartada** | `DATA_PATH` tiene prioridad. `NODEBOARD_DB` solo se evalúa si `DATA_PATH` no existe. |
| 7 | La DB usa una ruta relativa dentro de `/app`. | **Confirmada** | `database.py:20` default = `sqlite:///./nodeboard.db` → `/app/nodeboard.db` en Docker. |
| 8 | La base queda incluida dentro de la imagen Docker. | **Posible (builds locales)** | No hay `.dockerignore`; `nodeboard-backend/*.db` podría colarse en builds locales. En Railway CI (git checkout limpio) no. |
| 9 | Cada build reemplaza la DB incluida en la imagen. | **Posible (builds locales)** | Si la imagen contiene un `nodeboard.db`, cada nuevo build lo reemplaza. En Railway CI esto no aplica. |
| 10 | El startup elimina o recrea la base. | **Descartada** | No hay `drop_all`, `init_db`, `rm`, `unlink`, ni lógica destructiva. |
| 11 | Las migraciones son destructivas. | **Descartada** | Las 3 migraciones son puramente aditivas (crear tablas, agregar columnas, alterar tipos). |
| 12 | El directorio persistente no tiene permisos de escritura. | **Posible** | El contenedor corre como root, improbable. Pero si hubiera un `USER` no-root y `/data` no tuviera permisos, podría fallar. No hay `USER` en el Dockerfile. |
| 13 | Al fallar la escritura en `/data`, el código usa silenciosamente otra ruta. | **Descartada** | No hay try/except ni fallback en `get_database_url()`. Si `DATA_PATH=/data`, esa ruta se usa o falla. |
| 14 | Railway está ejecutando varias réplicas. | **Posible** | No verificable desde el repo. SQLite no es seguro con múltiples réplicas. |
| 15 | Existen dos bases y el proceso abre una diferente después de cada deploy. | **Confirmada** | La ruta relativa `./nodeboard.db` depende del `WORKDIR` y del CWD al momento de importar `database.py`. Siempre es `/app/nodeboard.db`, pero el contenedor es efímero. |
| 16 | El volumen está montado correctamente, pero la base usa otro nombre. | **Posible** | Si el volumen está en `/data` pero la app escribe en `/app/nodeboard.db`, los datos nunca llegan al volumen. |
| 17 | Los datos no están en SQLite sino en archivos no persistidos. | **Descartada** | Todos los datos están en SQLite (`models.py`). |
| 18 | Alguna variable de entorno cambia entre deploys. | **Posible** | No verificable desde el repo. |
| 19 | El servicio se recreó sin conservar el volumen. | **Posible** | Si el servicio se eliminó y recreó en Railway, el volumen anterior se pierde. |
| 20 | El problema ocurre por una inicialización o seed ejecutado en cada arranque. | **Descartada** | No existe seed, init_db, ni lógica de inicialización de datos. |

---

## F. Verificaciones manuales en Railway

Instrucciones exactas para comprobar desde el dashboard de Railway:

### 1. Verificar servicio correcto

1. Ir a [Railway Dashboard](https://railway.app/dashboard)
2. Seleccionar el proyecto de Huginn
3. Verificar que el servicio desplegado es el backend (no otro servicio como una base de datos PostgreSQL)

### 2. Verificar Volumes

1. En la vista del servicio, ir a la pestaña **Volumes**
2. Verificar que existe un volumen
3. Anotar el **Mount Path** exacto (debería ser `/data`)
4. Verificar que el volumen está **conectado** (estado "Attached")

### 3. Verificar variables de entorno

1. Ir a la pestaña **Variables**
2. Buscar `DATA_PATH` — si no aparece, esa es la causa raíz
3. Buscar `NODEBOARD_DB` — si aparece, anotar su valor
4. Verificar que no hay valores heredados de un entorno anterior

Anotar los resultados exactos:
```
DATA_PATH = _______
NODEBOARD_DB = _______
```

### 4. Verificar número de réplicas

1. Ir a la pestaña **Deployments** o **Settings**
2. Buscar la sección **Replicas**
3. Debe estar en `1` (exactamente una réplica)
4. Si está en más de 1, SQLite no es seguro

### 5. Revisar logs del último deploy

1. Ir a la pestaña **Deployments**
2. Seleccionar el último deploy exitoso
3. Revisar los logs de build y runtime
4. Buscar mensajes como:
   - `→ Ejecutando migraciones de base de datos...`
   - `→ Iniciando uvicorn en puerto...`
   - Errores de permisos o "no such file or directory"
   - Si no hay mensajes de migración, la DB se creó vacía

### 6. Shell del contenedor (si está disponible)

Railway ofrece una terminal en la pestaña **Shell** del servicio. Si está habilitada:

```bash
# Ver ruta actual
pwd

# Verificar DATA_PATH
echo "DATA_PATH=${DATA_PATH:-<unset>}"
echo "NODEBOARD_DB=${NODEBOARD_DB:-<unset>}"

# Buscar bases de datos
find / -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) 2>/dev/null

# Verificar /data
ls -la /data/

# Verificar /app para base efímera
ls -la /app/nodeboard.db 2>/dev/null
```

---

## G. Comandos seguros

### G1. Local (repositorio)

```bash
# Verificar rutas de DB en código
grep -rn "sqlite:///" nodeboard-backend/app/ --include="*.py"
grep -rn "DATA_PATH\|NODEBOARD_DB" nodeboard-backend/app/ --include="*.py"

# Verificar migraciones (solo aditivas)
cat nodeboard-backend/migrations/versions/*.py | grep -E "(create_table|add_column|alter_column|drop_table|drop_column)"

# Verificar si hay .dockerignore
ls -la .dockerignore 2>/dev/null || echo "NO EXISTE .dockerignore"

# Verificar si hay DB local
ls -la nodeboard-backend/*.db 2>/dev/null || echo "No hay DB local"
```

### G2. En Railway (Shell del contenedor)

```bash
# 1. Identidad
pwd
id
hostname

# 2. Variables de entorno relevantes
env | grep -E 'DATA_PATH|NODEBOARD_DB|DATABASE_URL|PORT|HOME'

# 3. Buscar todas las bases SQLite en el contenedor
find / -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) 2>/dev/null

# 4. Verificar /data
ls -la /data/
ls -la /data/nodeboard.db 2>/dev/null && echo "EXISTE /data/nodeboard.db" || echo "NO EXISTE /data/nodeboard.db"

# 5. Verificar /app
ls -la /app/nodeboard.db 2>/dev/null && echo "EXISTE /app/nodeboard.db" || echo "NO EXISTE /app/nodeboard.db"

# 6. Verificar tamaño y permisos
stat /app/nodeboard.db 2>/dev/null
stat /data/nodeboard.db 2>/dev/null

# 7. Verificar si el directorio /data es el mismo filesystem que /app
df /app /data
```

### G3. Script Python de diagnóstico (no destructivo)

```python
"""Diagnóstico seguro de la base de datos. No modifica nada."""
import os, sys
from pathlib import Path

# === Rutas ===
print("=" * 60)
print("[huginn-storage] DIAGNÓSTICO DE ALMACENAMIENTO")
print("=" * 60)

# Variables de entorno
data_path = os.getenv("DATA_PATH", "<unset>")
nodeboard_db = os.getenv("NODEBOARD_DB", "<unset>")
print(f"[huginn-storage] DATA_PATH={data_path}")
print(f"[huginn-storage] NODEBOARD_DB={nodeboard_db}")

# Directorio actual
cwd = os.getcwd()
print(f"[huginn-storage] cwd={cwd}")
print(f"[huginn-storage] hostname={os.uname().nodename}")

# Resolver ruta que usaría la app
from app.database import get_database_url
db_url = get_database_url()
# Extraer ruta del archivo desde sqlite:///path
db_path = db_url.replace("sqlite:///", "", 1)
print(f"[huginn-storage] db_url={db_url}")
print(f"[huginn-storage] db_path={db_path}")

# Verificar directorio padre
db_dir = Path(db_path).parent
print(f"[huginn-storage] db_parent={db_dir}")
print(f"[huginn-storage] db_parent_exists={db_dir.exists()}")
if db_dir.exists():
    print(f"[huginn-storage] db_parent_permissions={oct(db_dir.stat().st_mode)}")
    print(f"[huginn-storage] db_parent_writable={os.access(db_dir, os.W_OK)}")

# Verificar archivo DB
db_file = Path(db_path)
if db_file.exists():
    st = db_file.stat()
    print(f"[huginn-storage] db_exists=true")
    print(f"[huginn-storage] db_size_bytes={st.st_size}")
    print(f"[huginn-storage] db_permissions={oct(st.st_mode)}")
    print(f"[huginn-storage] db_device={st.st_dev}")
    print(f"[huginn-storage] db_inode={st.st_ino}")
else:
    print(f"[huginn-storage] db_exists=false")

# Tablas y conteos (solo metadatos + conteos, sin datos personales)
try:
    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cur.fetchall()]
    print(f"[huginn-storage] sqlite_tables={tables}")
    for table in tables:
        if table != "sqlite_sequence":
            cur.execute(f"SELECT COUNT(*) FROM \"{table}\"")
            count = cur.fetchone()[0]
            print(f"[huginn-storage]   {table}: {count} filas")
    conn.close()
except Exception as e:
    print(f"[huginn-storage] sqlite_error={e}")

print("=" * 60)
```

Ejecutar en Railway (desde `/app`):
```bash
cd /app
python -c "$(cat << 'PYEOF'
# pegar aquí el script de diagnóstico de G3
PYEOF
)"
```

O mejor, crear un archivo temporal:
```bash
cat > /tmp/diag.py << 'EOF'
# pegar aquí el script de diagnóstico de G3
EOF
python /tmp/diag.py
rm /tmp/diag.py  # opcional, no deja rastro
```

---

## H. Causa raíz

**Una sola causa raíz principal:**

> **La variable de entorno `DATA_PATH` no está configurada en Railway.**

Esto provoca que `get_database_url()` en `database.py:17-20` retorne el default `sqlite:///./nodeboard.db`, que dentro del contenedor Docker (con `WORKDIR=/app`) se resuelve a `/app/nodeboard.db` — un archivo en el filesystem efímero del contenedor que se destruye en cada deploy.

Mecanismo exacto:

1. Railway despliega un nuevo contenedor desde la imagen
2. No hay `DATA_PATH` en el entorno → `database.py:20` retorna `sqlite:///./nodeboard.db`
3. SQLite crea `/app/nodeboard.db` (vacío) en el primer request de BD
4. Alembic crea las tablas (BD vacía, sin datos)
5. El usuario interactúa y los datos se guardan en `/app/nodeboard.db`
6. Siguiente deploy → Railway destruye el contenedor → `/app/` desaparece
7. Nuevo contenedor, nueva BD vacía en `/app/nodeboard.db`
8. **Los datos anteriores no existen y no hay error visible** porque la creación de BD es silenciosa

**No es "Railway es efímero"** — el volumen de Railway está diseñado precisamente para persistir datos. El problema es que la aplicación nunca escribe en el volumen porque ninguna variable de entorno le dice que use la ruta `/data`.

---

## I. Corrección recomendada

### Parche mínimo y definitivo

```yaml
# Railway (dashboard o CLI):
# Variable: DATA_PATH = /data
# Volume mount path: /data
# Replicas: 1
```

### Cambios en el código

#### 1. Agregar `.dockerignore`

Crear `.dockerignore` en la raíz del proyecto:

```dockerignore
node_modules/
dist/
nodeboard-backend/.venv/
nodeboard-backend/__pycache__/
nodeboard-backend/.pytest_cache/
nodeboard-backend/*.db
nodeboard-backend/*.sqlite
nodeboard-backend/.env
.git/
.gitignore
**/*.md
vault/
e2e/
```

#### 2. Agregar validación en `database.py`

Agregar una validación que impida el uso de rutas relativas en producción:

```python
def get_database_url() -> str:
    data_path = os.getenv("DATA_PATH")
    if data_path:
        return f"sqlite:///{Path(data_path) / 'nodeboard.db'}"
    
    db_url = os.getenv("NODEBOARD_DB")
    if db_url:
        return db_url
    
    # En producción, fallar explícitamente si no hay DATA_PATH
    env = os.getenv("ENVIRONMENT", "development").strip().lower()
    if env == "production":
        raise RuntimeError(
            "DATA_PATH no está configurado. "
            "En producción debe establecerse DATA_PATH=/data "
            "con un volumen persistente montado en esa ruta."
        )
    
    # En desarrollo, mantener compatibilidad
    return "sqlite:///./nodeboard.db"
```

#### 3. Agregar log de la ruta al inicio

En `database.py`, al final:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("database_url=%s db_file=%s", DATABASE_URL, DATABASE_URL.replace("sqlite:///", "", 1))
```

### Arquitectura final deseada

```
DATA_PATH=/data                          ← env var en Railway
DB_PATH=/data/nodeboard.db              ← resultado de get_database_url()
Railway volume mount=/data              ← mount path del volumen
replicas=1                               ← exactamente una réplica
```

La aplicación debe:
- ✅ Resolver la ruta de forma absoluta (`/data/nodeboard.db`)
- ✅ Crear solo el directorio, no reemplazar la base
- ✅ Fallar explícitamente si producción intenta usar ruta efímera
- ✅ No tener fallback silencioso
- ✅ Registrar la ruta usada al iniciar
- ✅ Verificar que el directorio sea escribible
- ✅ Usar una única variable canónica (`DATA_PATH`)
- ✅ Mantener compatibilidad local razonable (cuando `ENVIRONMENT != "production"`)

---

## J. Plan de migración segura

Si la base actual está en `/app/nodeboard.db` (efímera) y aún existe en el contenedor actual, hay que copiarla al volumen antes del próximo deploy.

### Pasos

> ⚠️ Ejecutar solo cuando el servicio esté funcionando y antes del próximo deploy.

#### 1. Detener escrituras

No se necesita detener el servicio si se hace rápido. La base es SQLite y las escrituras son transaccionales. Para máxima seguridad, pausar el servicio en Railway.

#### 2. Identificar la DB correcta

Conectarse al Shell de Railway y ejecutar:

```bash
# Buscar todas las DBs
find / -type f \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) 2>/dev/null

# Verificar la que tiene datos
sqlite3 /app/nodeboard.db "SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM studios; SELECT COUNT(*) FROM boards;"
```

#### 3. Hacer backup

```bash
cp /app/nodeboard.db /tmp/nodeboard.backup.db
```

#### 4. Configurar Railway

Antes de copiar, asegurar que el volumen existe y está montado:

1. En Railway Dashboard → servicio → pestaña **Volumes**
2. Crear un volumen con **Mount Path** = `/data`
3. En **Variables**, agregar `DATA_PATH=/data`
4. Esperar a que el servicio redespliegue **con el volumen montado**

#### 5. Copiar la DB al volumen

Después del redespliegue (que creará una BD vacía en `/data/nodeboard.db`):

```bash
# Detener temporalmente el servicio (opcional)
# Desde el Shell de Railway:
cp /tmp/nodeboard.backup.db /data/nodeboard.db
# Verificar permisos
chmod 644 /data/nodeboard.db
```

O alternativamente, si el volumen está montado en el mismo deploy:

```bash
# Verificar que /data existe y es escribible
ls -la /data/
# Copiar la DB
cp /app/nodeboard.db /data/nodeboard.db
```

#### 6. Verificar integridad

```bash
sqlite3 /data/nodeboard.db "PRAGMA integrity_check;"
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM users;"
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM studios;"
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM boards;"
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM nodes;"
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM edges;"
```

#### 7. Arrancar usando la nueva ruta

Si el servicio ya tiene `DATA_PATH=/data` y el volumen montado en `/data`, al reiniciar usará `/data/nodeboard.db`.

#### 8. Confirmar conteos

Después del reinicio:

```bash
curl -s http://localhost:8001/api/health
# O desde la API externa
```

O desde el Shell:
```bash
sqlite3 /data/nodeboard.db "SELECT 'users', COUNT(*) FROM users UNION ALL SELECT 'studios', COUNT(*) FROM studios UNION ALL SELECT 'boards', COUNT(*) FROM boards UNION ALL SELECT 'nodes', COUNT(*) FROM nodes;"
```

#### 9. Hacer deploy de prueba

Hacer un cambio trivial (ej: editar un README), pushear, y verificar que Railway redespliega. Después del deploy:

```bash
# Verificar que los datos sobreviven
sqlite3 /data/nodeboard.db "SELECT COUNT(*) FROM users;"
```

#### 10. Comprobar que los datos siguen existiendo

Confirmar que el contador de filas es el mismo antes y después del deploy. Si es así, la persistencia está funcionando.

### Después de la migración

1. Conservar el backup en `/tmp/nodeboard.backup.db` por al menos 1 semana
2. Monitorear los logs del deploy para ver `[huginn-storage]` si se agregó el diagnóstico
3. No borrar el volumen de Railway

---

## K. Checklist de criterios de aceptación

| # | Pregunta | Respuesta |
|---|----------|-----------|
| 1 | ¿Cuál es la ruta absoluta de la DB en producción? | **`/app/nodeboard.db`** (efímera). Debería ser `/data/nodeboard.db`. |
| 2 | ¿Está dentro o fuera del volumen Railway? | **Fuera.** Railway espera que la DB esté en `/data/`, pero la app escribe en `/app/`. |
| 3 | ¿Cuál es el mount path correcto? | **`/data`** |
| 4 | ¿Qué variable controla la ruta? | **`DATA_PATH`** (variable canónica). `NODEBOARD_DB` es override legacy. |
| 5 | ¿Existe alguna variable que la sobrescriba? | `NODEBOARD_DB`, si está definida y `DATA_PATH` no. |
| 6 | ¿El startup puede borrar o reemplazar datos? | **No**, el startup no tiene lógica destructiva. |
| 7 | ¿La imagen Docker contiene una DB? | **No en Railway CI** (git checkout limpio). **Posible en builds locales** (no hay `.dockerignore`). |
| 8 | ¿Hay más de una DB posible? | **Sí:** `/app/nodeboard.db` (efímera) y `/data/nodeboard.db` (deseada). |
| 9 | ¿Hay una sola réplica? | **Pendiente de verificar** en Railway. Debería ser 1. |
| 10 | ¿Qué cambio exacto evita que vuelva a ocurrir? | Configurar `DATA_PATH=/data` en Railway + montar volumen en `/data`. |
| 11 | ¿Cómo recupero datos existentes? | Ver sección **J. Plan de migración segura**. |
| 12 | ¿Cómo compruebo con un deploy de prueba? | Ver pasos 9-10 del plan de migración. |

---

## L. Resumen de archivos revisados

| Archivo | Líneas clave | Hallazgo |
|---------|-------------|----------|
| `Dockerfile` | 26, 38-42, 48 | WORKDIR=/app. Crea `/data` pero no setea `DATA_PATH`. No hay `USER`. |
| `.dockerignore` | — | **No existe**. |
| `railway.toml` | — | **No existe**. |
| `nodeboard-backend/entrypoint.sh` | 5, 8 | Ejecuta `alembic upgrade head`. No toca datos. |
| `nodeboard-backend/app/database.py` | 9-20, 23-28 | `get_database_url()`: `DATA_PATH` → `NODEBOARD_DB` → default relativo. |
| `nodeboard-backend/app/main.py` | 96-100 | Lifespan ejecuta `alembic upgrade head` (segunda vez, no-op). |
| `nodeboard-backend/app/models.py` | — | Tablas ORM. Sin lógica de inicialización. |
| `nodeboard-backend/migrations/env.py` | 29-30 | Usa `get_database_url()` para la URL de Alembic. |
| `nodeboard-backend/alembic.ini` | 88 | Default `sqlite:///./nodeboard.db` (sobrescrito por env.py). |
| `nodeboard-backend/migrations/versions/*.py` | — | 3 migraciones puramente aditivas. |
| `package.json` | 9 | `dev:api` setea `NODEBOARD_DB` por defecto (solo desarrollo). |
| `playwright.config.ts` | 34-36 | E2E usa su propia DB en `e2e/.db/`. |

---

*Fin del informe de auditoría. No realizar cambios sin completar las verificaciones de la sección F.*
