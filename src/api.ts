import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import type { BoardSummary, Folder, Node, Edge, Studio, StudioBoards } from "./types";

export type SaveStatus = "cargando" | "guardando" | "guardado" | "error";

type Board = { id: string; name: string; nodes: Node[]; edges: Edge[] };

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
  // Studios
  listStudios: () => request<Studio[]>("/api/studios"),
  createStudio: (name: string, color: string) => request<Studio>("/api/studios", {
    method: "POST", body: JSON.stringify({ name, color }),
  }),
  deleteStudio: (id: string) => request<void>(`/api/studios/${id}`, { method: "DELETE" }),

  // Folders
  listFolders: (studioId: string) => request<Folder[]>(`/api/studios/${studioId}/folders`),
  createFolder: (name: string, studioId: string) => request<Folder>("/api/folders", {
    method: "POST", body: JSON.stringify({ name, studio_id: studioId }),
  }),
  deleteFolder: (id: string) => request<void>(`/api/folders/${id}`, { method: "DELETE" }),
  listFolderBoards: (folderId: string) => request<BoardSummary[]>(`/api/folders/${folderId}/boards`),

  // Boards
  listBoards: () => request<BoardSummary[]>("/api/boards"),
  createBoard: (name: string, studioId: string, folderId?: string) => request<Board>("/api/boards", {
    method: "POST", body: JSON.stringify({ name, studio_id: studioId, folder_id: folderId ?? null }),
  }),
  deleteBoard: (id: string) => request<void>(`/api/boards/${id}`, { method: "DELETE" }),
  getBoard: (id: string) => request<Board>(`/api/boards/${id}`),
  getBoardTags: (id: string) => request<string[]>(`/api/boards/${id}/tags`),
  saveState: (id: string, state: Pick<Board, "nodes" | "edges">) =>
    request<Board>(`/api/boards/${id}/state`, { method: "PUT", body: JSON.stringify(state) }),
  getStudioBoards: (studioId: string) => request<StudioBoards>(`/api/studios/${studioId}/boards`),
};

type PersistenceOptions = {
  boardId: string | null;
  nodes: Node[];
  edges: Edge[];
  setNodes: Dispatch<SetStateAction<Node[]>>;
  setEdges: Dispatch<SetStateAction<Edge[]>>;
  debounceMs?: number;
};

export function useBoardPersistence({
  boardId, nodes, edges, setNodes, setEdges, debounceMs = 800,
}: PersistenceOptions) {
  const [status, setStatus] = useState<SaveStatus>("cargando");
  const loadedRef = useRef(false);

  useEffect(() => {
    if (!boardId) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const board = await api.getBoard(boardId);
        if (controller.signal.aborted) return;
        setNodes(board.nodes);
        setEdges(board.edges);
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
  }, [boardId, setEdges, setNodes]);

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

  return { status };
}
