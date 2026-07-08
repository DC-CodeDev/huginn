import { useEffect, useRef, useState, useCallback, type Dispatch, type SetStateAction } from "react";
import type { BoardSummary, Folder, Node, Edge, Studio, StudioBoards } from "./types";
import { VersionConflictError, type BoardConflict, type VersionConflictPayload } from "./lib/board-conflict";
import { createWriteQueue } from "./lib/board-write-queue";

export type SaveStatus = "cargando" | "guardando" | "guardado" | "error" | "conflicto";
export type AuthUser = {
  id: string;
  email: string;
  name: string;
  avatar_url: string;
};

type Board = { id: string; name: string; version: number; nodes: Node[]; edges: Edge[] };

const BASE = import.meta.env.VITE_API_URL ?? "";

// ----------------------------------------------------------------------
//  Callback global para 401
// ----------------------------------------------------------------------
let _unauthorizedHandler: (() => void) | null = null;

export function registerUnauthorizedHandler(fn: (() => void) | null) {
  _unauthorizedHandler = fn;
}

export function buildApiUrl(path: string): string {
  return `${BASE}${path}`;
}

export function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const defaultHeaders = new Headers(options.body === undefined ? undefined : { "Content-Type": "application/json" });
  if (options.headers) {
    new Headers(options.headers).forEach((value, key) => defaultHeaders.set(key, value));
  }
  return fetch(buildApiUrl(path), {
    credentials: "include",
    ...options,
    headers: defaultHeaders,
  });
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, options);
  if (!response.ok) {
    if (response.status === 401 && _unauthorizedHandler) {
      _unauthorizedHandler();
    }
    if (response.status === 409) {
      let body: unknown;
      try {
        body = await response.clone().json();
      } catch {
        body = null;
      }
      if (body && typeof body === "object" && "detail" in (body as Record<string, unknown>)) {
        const detail = (body as Record<string, unknown>).detail as Record<string, unknown> | undefined;
        if (detail?.code === "VERSION_CONFLICT") {
          throw new VersionConflictError(detail as VersionConflictPayload);
        }
      }
    }
    const text = await response.text().catch(() => "");
    throw new Error(`${response.status} ${text}`);
  }
  return (response.status === 204 ? null : await response.json()) as T;
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const response = await apiFetch("/api/auth/me");
  if (!response.ok) {
    throw new Error("No autenticado");
  }
  return response.json() as Promise<AuthUser>;
}

export async function loginWithGoogleCode(code: string): Promise<AuthUser> {
  const response = await apiFetch("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  if (!response.ok) {
    throw new Error("Error al iniciar sesión");
  }
  return response.json() as Promise<AuthUser>;
}

export async function logoutSession(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" });
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
  deleteBoard: (id: string, expectedVersion: number) =>
    request<void>(`/api/boards/${id}?expected_version=${expectedVersion}`, { method: "DELETE" }),
  renameBoard: (id: string, name: string, expectedVersion: number) =>
    request<Board>(`/api/boards/${id}`, {
      method: "PATCH", body: JSON.stringify({ name, expected_version: expectedVersion }),
    }),
  getBoard: (id: string) => request<Board>(`/api/boards/${id}`),
  getBoardTags: (id: string) => request<string[]>(`/api/boards/${id}/tags`),
  saveState: (id: string, state: Pick<Board, "nodes" | "edges" | "version"> & { name?: string }) =>
    request<Board>(`/api/boards/${id}/state`, { method: "PUT", body: JSON.stringify(state) }),
  getStudioBoards: (studioId: string) => request<StudioBoards>(`/api/studios/${studioId}/boards`),
};

// ----------------------------------------------------------------------
//  useBoardPersistence
// ----------------------------------------------------------------------

type PersistenceOptions = {
  boardId: string | null;
  nodes: Node[];
  edges: Edge[];
  setNodes: Dispatch<SetStateAction<Node[]>>;
  setEdges: Dispatch<SetStateAction<Edge[]>>;
  boardName?: string;
  debounceMs?: number;
};

export function useBoardPersistence({
  boardId, nodes, edges, setNodes, setEdges, boardName, debounceMs = 800,
}: PersistenceOptions) {
  const [status, setStatus] = useState<SaveStatus>("cargando");
  const [boardVersion, setBoardVersion] = useState<number | null>(null);
  const [conflict, setConflict] = useState<BoardConflict | null>(null);
  const loadedRef = useRef(false);

  // Refs para evitar closures obsoletas
  const boardVersionRef = useRef<number | null>(null);
  const conflictRef = useRef<BoardConflict | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const boardIdRef = useRef<string | null>(null);

  // Cola de escrituras — se recrea al cambiar de board
  const queueRef = useRef<ReturnType<typeof createWriteQueue>>(
    createWriteQueue(
      () => boardVersionRef.current,
      () => conflictRef.current,
      () => boardIdRef.current ?? "",
    ),
  );

  // Mantener refs sincronizados
  boardVersionRef.current = boardVersion;
  conflictRef.current = conflict;
  boardIdRef.current = boardId;

  // --- beforeunload: proteger al salir ---
  useEffect(() => {
    const shouldWarn = status === "guardando" || status === "conflicto";
    if (!shouldWarn) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = ""; // necesario para la mayoría de navegadores
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [status]);

  // --- Carga inicial del board ---
  useEffect(() => {
    if (!boardId) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const board = await api.getBoard(boardId);
        if (controller.signal.aborted) return;
        setNodes(board.nodes);
        setEdges(board.edges);
        setBoardVersion(board.version);
        boardVersionRef.current = board.version;
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

  // --- Cancelar debounce helper ---
  const cancelDebounce = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
  }, []);

  // --- Cola de escrituras ---
  const enqueueWrite = useCallback(<T,>(
    operation: (version: number) => Promise<T>,
  ): Promise<T> => {
    return queueRef.current.enqueue(operation);
  }, []);

  // --- Autosave con cola de escrituras ---
  useEffect(() => {
    if (!boardId || !loadedRef.current) return;
    if (boardVersionRef.current === null) return;
    if (conflict !== null) return;

    cancelDebounce();
    setStatus("guardando");
    debounceTimerRef.current = setTimeout(() => {
      void enqueueWrite(async (version) => {
        const payload: Record<string, unknown> = {
          nodes, edges, expected_version: version,
        };
        if (boardName !== undefined) payload.name = boardName;
        const result = await api.saveState(boardId, payload as Parameters<typeof api.saveState>[1]);
        // Actualizar versión desde la respuesta del backend
        setBoardVersion(result.version);
        boardVersionRef.current = result.version;
        cancelDebounce();
        setStatus("guardado");
        return result;
      }).catch((error: unknown) => {
        if (error instanceof VersionConflictError) {
          const c: BoardConflict = {
            boardId: error.boardId,
            expectedVersion: error.expectedVersion,
            currentVersion: error.currentVersion,
            message: error.message,
          };
          setConflict(c);
          conflictRef.current = c;
          cancelDebounce();
          setStatus("conflicto");
        } else {
          console.error("No se pudo guardar el tablero", error);
          setStatus("error");
        }
      });
    }, debounceMs);

    return () => cancelDebounce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boardId, boardName, debounceMs, edges, nodes, conflict, cancelDebounce, enqueueWrite]);

  // --- Recarga controlada desde el servidor ---
  const reloadBoardFromServer = useCallback(async (): Promise<boolean> => {
    if (!boardIdRef.current) return false;
    try {
      const fresh = await api.getBoard(boardIdRef.current);
      setNodes(fresh.nodes);
      setEdges(fresh.edges);
      setBoardVersion(fresh.version);
      boardVersionRef.current = fresh.version;
      setConflict(null);
      conflictRef.current = null;
      // Reiniciar cola
      queueRef.current.reset();
      cancelDebounce();
      setStatus("guardado");
      return true;
    } catch (error) {
      console.error("No se pudo recargar el board", error);
      return false;
    }
  }, [setNodes, setEdges, cancelDebounce]);

  // --- Limpiar al cambiar de board ---
  useEffect(() => {
    return () => {
      cancelDebounce();
      setConflict(null);
      conflictRef.current = null;
      boardVersionRef.current = null;
      queueRef.current.reset();
    };
  }, [boardId, cancelDebounce]);

  return { status, boardVersion, conflict, reloadBoardFromServer };
}
