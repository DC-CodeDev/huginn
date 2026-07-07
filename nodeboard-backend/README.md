# Nodeboard API

Backend con persistencia para el nodeboard: FastAPI + SQLAlchemy + SQLite.

## Estructura

```
nodeboard-backend/
├── app/
│   ├── database.py    # Motor SQLite y sesión
│   ├── models.py      # ORM: Board, Node, Edge
│   ├── schemas.py     # Pydantic (mismo formato que el frontend)
│   └── main.py        # Endpoints REST + arranque de migraciones
├── migrations/
│   ├── env.py         # Config de Alembic (apunta a app.database.Base.metadata)
│   ├── script.py.mako # Template de revisiones
│   └── versions/      # Migraciones versionadas
├── alembic.ini        # Config de Alembic
├── frontend/
│   └── api.js         # Cliente fetch + hook useBoardPersistence (autosave)
├── requirements.txt
└── README.md
```

## Instalación y ejecución

```bash
cd nodeboard-backend
python -m venv .venv && source .venv/bin/activate   # en Arch: python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

La base de datos `nodeboard.db` se crea sola en el primer arranque (via Alembic migrations).
Documentación interactiva en `http://localhost:8000/docs`.

## Migraciones (Alembic)

Las migraciones se ejecutan automáticamente al arrancar el backend (`alembic upgrade head`
dentro del lifespan de FastAPI). Para generar una nueva migración tras cambiar los modelos:

```bash
cd nodeboard-backend
.venv/bin/alembic revision --autogenerate -m "descripcion_del_cambio"
```

Revisar la migración generada en `migrations/versions/` antes de aplicarla.
El autogenerate compara el metadata de `app.database.Base` contra el estado actual
de la base de datos; si el diff es vacío la migración generada tendrá `upgrade()` vacío.

La URL de la base de datos se lee de la variable de entorno `NODEBOARD_DB`
(ver `app/database.py` y `package.json` → `dev:api`).

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/boards` | Lista de tableros con conteo de nodos/aristas |
| POST | `/api/boards` | Crear tablero `{name}` |
| GET | `/api/boards/{id}` | Estado completo: nodos + aristas |
| GET | `/api/boards/{id}/tags` | Tags únicos usados por los nodos del tablero |
| PATCH | `/api/boards/{id}` | Renombrar |
| PUT | `/api/boards/{id}/state` | Guardar todo el estado (autosave) |
| DELETE | `/api/boards/{id}` | Eliminar tablero |
| POST | `/api/boards/{id}/nodes` | Crear nodo |
| PATCH | `/api/nodes/{id}` | Actualizar nodo (parcial) |
| DELETE | `/api/nodes/{id}` | Eliminar nodo y sus aristas |
| POST | `/api/boards/{id}/edges` | Crear arista |
| PATCH | `/api/edges/{id}` | Cambiar `curved` |
| DELETE | `/api/edges/{id}` | Eliminar arista |

El formato JSON es idéntico al estado interno de `src/NodeBoard.tsx`:

```json
{
  "nodes": [{ "id": "n1", "type": "card", "x": 120, "y": 260, "w": 280,
              "title": "Model", "ports": [], "blocks": [], "stages": [] }],
  "edges": [{ "id": "e1",
              "from": { "nodeId": "n1", "portId": "p2" },
              "to":   { "nodeId": "n2", "portId": "p4" },
              "curved": true }]
}
```

## Integración con el frontend

El cliente vive en `src/api.ts` y el componente principal es
`src/NodeBoard.tsx` (el archivo `frontend/api.js` de este backend es
código histórico del prototipo y ya no se usa).

`src/NodeBoard.tsx` importa el hook `useBoardPersistence` desde `src/api.ts`
y lo conecta al estado de nodos y aristas:

```tsx
import { useBoardPersistence } from "./api";

export default function NodeBoard() {
  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges);
  const { status } = useBoardPersistence({ nodes, edges, setNodes, setEdges });
  // ... resto del componente
}
```

El valor `status` se muestra en la barra de herramientas
(`cargando`, `guardando`, `guardado`, `error`).

El hook carga el primer tablero existente (o crea uno) y guarda
automáticamente con debounce de 800 ms ante cualquier cambio, usando
`PUT /state` como operación atómica. Los endpoints granulares quedan
disponibles si más adelante querés sincronización fina en vez de
guardado completo.

## Notas de diseño

- **JSON para ports/blocks/stages**: estas estructuras varían por tipo de
  nodo y cambian seguido con el frontend; guardarlas como JSON evita
  migraciones constantes. Las aristas sí están normalizadas para poder
  validarlas y limpiarlas al borrar nodos.
- **Imágenes**: los bloques de imagen viajan como data-URL dentro de
  `blocks`, así que persisten sin configuración extra. Si el tablero
  crece mucho, conviene mover las imágenes a archivos y guardar la ruta.
- **CORS**: habilitado para `localhost:5173` (Vite) y `localhost:3000`.
