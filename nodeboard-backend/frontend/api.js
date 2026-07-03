/**
 * ⚠️ CÓDIGO HISTÓRICO — NO USAR NI ACTUALIZAR.
 *
 * Este archivo es el cliente original del prototipo de Nodeboard. Fue
 * reemplazado por `src/api.ts`, que es el cliente real y mantenido del
 * frontend actual. No se importa ni se usa en ningún punto del proyecto.
 * Se conserva únicamente como referencia del prototipo; cualquier cambio
 * debe hacerse en `src/api.ts`, no acá.
 */

/**
 * Cliente de la Nodeboard API + hook de autosave.
 *
 * Integración con nodeboard.jsx:
 *
 *   import { useBoardPersistence } from "./api";
 *
 *   export default function NodeBoard() {
 *     const [nodes, setNodes] = useState([]);
 *     const [edges, setEdges] = useState([]);
 *     const { status } = useBoardPersistence({ nodes, edges, setNodes, setEdges });
 *     // ... el resto del componente queda igual
 *   }
 *
 * El hook carga (o crea) un tablero al montar y guarda automáticamente
 * con debounce cada vez que cambian nodos o aristas.
 */
import { useEffect, useRef, useState } from "react";

const BASE = import.meta?.env?.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

/* ------------------------------------------------------------ CRUD */
export const api = {
  listBoards: () => request("/api/boards"),
  createBoard: (name = "Mi tablero") =>
    request("/api/boards", { method: "POST", body: JSON.stringify({ name }) }),
  getBoard: (id) => request(`/api/boards/${id}`),
  renameBoard: (id, name) =>
    request(`/api/boards/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteBoard: (id) => request(`/api/boards/${id}`, { method: "DELETE" }),
  saveState: (id, state) =>
    request(`/api/boards/${id}/state`, { method: "PUT", body: JSON.stringify(state) }),

  createNode: (boardId, node) =>
    request(`/api/boards/${boardId}/nodes`, { method: "POST", body: JSON.stringify(node) }),
  updateNode: (nodeId, patch) =>
    request(`/api/nodes/${nodeId}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteNode: (nodeId) => request(`/api/nodes/${nodeId}`, { method: "DELETE" }),

  createEdge: (boardId, edge) =>
    request(`/api/boards/${boardId}/edges`, { method: "POST", body: JSON.stringify(edge) }),
  updateEdge: (edgeId, patch) =>
    request(`/api/edges/${edgeId}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteEdge: (edgeId) => request(`/api/edges/${edgeId}`, { method: "DELETE" }),
};

/* ------------------------------------------------------ autosave hook */
export function useBoardPersistence({ nodes, edges, setNodes, setEdges, debounceMs = 800 }) {
  const [boardId, setBoardId] = useState(null);
  const [status, setStatus] = useState("cargando"); // cargando | guardado | guardando | error
  const timerRef = useRef(null);
  const loadedRef = useRef(false);

  // Cargar el primer tablero disponible (o crear uno) al montar
  useEffect(() => {
    (async () => {
      try {
        const boards = await api.listBoards();
        const board = boards.length
          ? await api.getBoard(boards[0].id)
          : await api.createBoard("Mi tablero");
        setNodes(board.nodes);
        setEdges(board.edges);
        setBoardId(board.id);
        loadedRef.current = true;
        setStatus("guardado");
      } catch (err) {
        console.error("No se pudo cargar el tablero:", err);
        setStatus("error");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Autosave con debounce ante cualquier cambio
  useEffect(() => {
    if (!boardId || !loadedRef.current) return;
    setStatus("guardando");
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        await api.saveState(boardId, { nodes, edges });
        setStatus("guardado");
      } catch (err) {
        console.error("No se pudo guardar:", err);
        setStatus("error");
      }
    }, debounceMs);
    return () => clearTimeout(timerRef.current);
  }, [nodes, edges, boardId, debounceMs]);

  return { boardId, status };
}
