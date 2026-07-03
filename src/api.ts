import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

export type SaveStatus = "cargando" | "guardando" | "guardado" | "error";

type Entity = { id: string; [key: string]: unknown };
type Board = { id: string; name: string; nodes: Entity[]; edges: Entity[] };
type BoardSummary = Pick<Board, "id" | "name">;

const BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return (response.status === 204 ? null : await response.json()) as T;
}

export const api = {
  listBoards: () => request<BoardSummary[]>("/api/boards"),
  createBoard: (name = "Mi tablero") => request<Board>("/api/boards", {
    method: "POST", body: JSON.stringify({ name }),
  }),
  getBoard: (id: string) => request<Board>(`/api/boards/${id}`),
  saveState: (id: string, state: Pick<Board, "nodes" | "edges">) =>
    request<Board>(`/api/boards/${id}/state`, { method: "PUT", body: JSON.stringify(state) }),
};

type PersistenceOptions<T extends Entity> = {
  nodes: T[];
  edges: T[];
  setNodes: Dispatch<SetStateAction<T[]>>;
  setEdges: Dispatch<SetStateAction<T[]>>;
  debounceMs?: number;
};

export function useBoardPersistence<T extends Entity>({
  nodes, edges, setNodes, setEdges, debounceMs = 800,
}: PersistenceOptions<T>) {
  const [boardId, setBoardId] = useState<string | null>(null);
  const [status, setStatus] = useState<SaveStatus>("cargando");
  const loadedRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const boards = await api.listBoards();
        const board = boards.length ? await api.getBoard(boards[0].id) : await api.createBoard();
        if (controller.signal.aborted) return;
        setNodes(board.nodes as T[]);
        setEdges(board.edges as T[]);
        setBoardId(board.id);
        loadedRef.current = true;
        setStatus("guardado");
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error("No se pudo cargar el tablero", error);
          setStatus("error");
        }
      }
    })();
    return () => controller.abort();
  }, [setEdges, setNodes]);

  useEffect(() => {
    if (!boardId || !loadedRef.current) return;
    setStatus("guardando");
    const timer = window.setTimeout(() => {
      void api.saveState(boardId, { nodes, edges })
        .then(() => setStatus("guardado"))
        .catch((error) => {
          console.error("No se pudo guardar el tablero", error);
          setStatus("error");
        });
    }, debounceMs);
    return () => window.clearTimeout(timer);
  }, [boardId, debounceMs, edges, nodes]);

  return { boardId, status };
}
