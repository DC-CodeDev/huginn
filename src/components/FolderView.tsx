import { useState, useEffect } from "react";
import { ArrowLeft, Loader2, FileText, Plus, Ellipsis, Trash2, FolderOpen } from "lucide-react";
import { api } from "../api";
import { renameBoard as renameBoardAction, deleteBoard as deleteBoardAction } from "../lib/board-actions";
import type { Folder, BoardSummary } from "../types";
import { ConfirmDeleteModal } from "./ConfirmDeleteModal";
import { PressableButton } from "./PressableButton";

function relativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = Math.floor((now - then) / 1000);
  if (diff < 60) return "Ahora";
  if (diff < 3600) return `Hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `Hace ${Math.floor(diff / 3600)} h`;
  if (diff < 604800) return `Hace ${Math.floor(diff / 86400)} d`;
  return new Date(iso).toLocaleDateString();
}

const RECENT_LIMIT = 6;

interface FolderViewProps {
  folderId: string;
  studioId: string;
  onBack: () => void;
  onBoardClick: (boardId: string) => void;
}

export function FolderView({ folderId, studioId, onBack, onBoardClick }: FolderViewProps) {
  const [folder, setFolder] = useState<Folder | null>(null);
  const [recentBoards, setRecentBoards] = useState<BoardSummary[] | null>(null);
  const [folderBoards, setFolderBoards] = useState<BoardSummary[] | null>(null);
  const [menuBoardId, setMenuBoardId] = useState<string | null>(null);
  const [deleteBoardId, setDeleteBoardId] = useState<string | null>(null);
  const [renameBoardId, setRenameBoardId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    api.listFolders(studioId).then((list) => {
      const f = list.find((x) => x.id === folderId);
      if (f) setFolder(f);
    });
    // Boards recientes del Studio completo
    api.getStudioBoards(studioId).then((data) => {
      const all = [...data.root_boards, ...data.folder_boards];
      all.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      setRecentBoards(all.slice(0, RECENT_LIMIT));
    }).catch(() => setRecentBoards([]));
    // Boards de esta carpeta
    api.listFolderBoards(folderId).then(setFolderBoards).catch(() => setFolderBoards([]));
  }, [folderId, studioId]);

  // Cerrar menú contextual al hacer clic fuera
  useEffect(() => {
    if (!menuBoardId) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-menu-root]')) setMenuBoardId(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuBoardId]);

  const doRename = async (id: string) => {
    const trimmed = renameValue.trim();
    if (!trimmed) { setRenameBoardId(null); return; }
    const boards = recentBoards ?? folderBoards;
    const result = await renameBoardAction(id, trimmed, boards);
    if (result.ok) {
      const upd = (prev: BoardSummary[] | null) =>
        prev ? prev.map((b) => b.id === id ? result.board : b) : prev;
      setRecentBoards(upd);
      setFolderBoards(upd);
    } else {
      if (result.reason === "conflict") {
        console.error("Conflicto al renombrar: el board fue modificado por otro cliente");
      } else {
        console.error("Error al renombrar board", result.reason === "no-version" ? "sin versión" : result.error);
      }
    }
    setRenameBoardId(null);
  };

  const createBoard = async () => {
    const board = await api.createBoard("Nuevo board", studioId, folderId);
    const summary: BoardSummary = {
      id: board.id,
      name: board.name,
      version: board.version,
      created_at: "",
      updated_at: new Date().toISOString(),
      node_count: 0,
      edge_count: 0,
    };
    setRecentBoards((prev) => prev ? [summary, ...prev].slice(0, RECENT_LIMIT) : [summary]);
    setFolderBoards((prev) => prev ? [summary, ...prev] : [summary]);
    onBoardClick(board.id);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteBoardId) return;
    const boards = folderBoards ?? recentBoards;
    const result = await deleteBoardAction(deleteBoardId, boards);
    if (result.ok) {
      setRecentBoards((prev) => prev ? prev.filter((b) => b.id !== deleteBoardId) : prev);
      setFolderBoards((prev) => prev ? prev.filter((b) => b.id !== deleteBoardId) : prev);
    } else if (result.reason === "conflict") {
      console.error("Conflicto al eliminar: el board fue modificado por otro cliente");
      // Recargar listados para obtener versión actualizada
      try {
        const data = await api.getStudioBoards(studioId);
        const all = [...data.root_boards, ...data.folder_boards];
        all.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
        setRecentBoards(all.slice(0, RECENT_LIMIT));
      } catch { /* ignorar */ }
    } else if (result.reason !== "no-version") {
      console.error("Error al eliminar board", result.error);
    }
    setDeleteBoardId(null);
  };

  const deleteName = deleteBoardId
    ? folderBoards?.find((b) => b.id === deleteBoardId)?.name
      ?? recentBoards?.find((b) => b.id === deleteBoardId)?.name
      ?? ""
    : "";

  if (!folder || recentBoards === null || folderBoards === null) {
    return (
      <div className="w-full app-dvh app-safe-page flex items-center justify-center" style={{ background: "var(--bg)" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "var(--sub)" }} />
      </div>
    );
  }

  return (
    <div className="w-full app-dvh" style={{ background: "var(--bg)" }}>
      <div className="max-w-5xl mx-auto px-6 py-8 app-safe-page">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button
            data-testid="back-to-studio"
            onClick={onBack}
            className="p-2 rounded-xl transition-colors"
          style={{ color: "var(--sub)" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--sub)")}
          >
            <ArrowLeft size={20} />
          </button>
          <h1 style={{ color: "var(--text)" }} className="text-2xl font-semibold">{folder.name}</h1>
        </div>

        {/* Archivos recientes (de todo el Studio) */}
        <section className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 style={{ color: "var(--sub)", opacity: 0.6 }} className="text-sm font-medium uppercase tracking-wider">
              Archivos recientes
            </h2>
            <button
              data-testid="create-board-btn"
              onClick={() => createBoard()}
              className="px-3 py-1.5 rounded-xl text-xs font-medium transition-colors"
              style={{ color: "var(--text)", opacity: 0.7, background: "var(--btn-overlay)", border: "1px solid var(--btn-overlay-border)" }}
            >
              + Nuevo Board
            </button>
          </div>
          {recentBoards.length === 0 ? (
            <p style={{ color: "var(--sub)", opacity: 0.5 }} className="text-sm">No hay boards en este Studio todavía</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {recentBoards.map((b) => (
                <BoardCard
                  key={b.id}
                  board={b}
                  menuBoardId={menuBoardId}
                  renameBoardId={renameBoardId}
                  renameValue={renameValue}
                  onMenuToggle={(id) => setMenuBoardId(menuBoardId === id ? null : id)}
                  onRenameStart={(id, name) => { setRenameValue(name); setRenameBoardId(id); setMenuBoardId(null); }}
                  onRenameChange={setRenameValue}
                  onRenameFinish={doRename}
                  onRenameCancel={() => setRenameBoardId(null)}
                  onDelete={() => { setDeleteBoardId(b.id); setMenuBoardId(null); }}
                  onClick={() => { if (!menuBoardId) onBoardClick(b.id); }}
                />
              ))}
            </div>
          )}
        </section>

        {/* Boards en esta carpeta */}
        {folderBoards.length > 0 && (
          <section>
            <h2 style={{ color: "var(--sub)", opacity: 0.6 }} className="text-sm font-medium uppercase tracking-wider mb-4">
              Boards en esta carpeta
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {folderBoards.map((b) => (
                <BoardCard
                  key={b.id}
                  board={b}
                  menuBoardId={menuBoardId}
                  renameBoardId={renameBoardId}
                  renameValue={renameValue}
                  onMenuToggle={(id) => setMenuBoardId(menuBoardId === id ? null : id)}
                  onRenameStart={(id, name) => { setRenameValue(name); setRenameBoardId(id); setMenuBoardId(null); }}
                  onRenameChange={setRenameValue}
                  onRenameFinish={doRename}
                  onRenameCancel={() => setRenameBoardId(null)}
                  onDelete={() => { setDeleteBoardId(b.id); setMenuBoardId(null); }}
                  onClick={() => { if (!menuBoardId) onBoardClick(b.id); }}
                />
              ))}
            </div>
          </section>
        )}
      </div>

      {deleteBoardId && (
        <ConfirmDeleteModal
          title="Eliminar Board"
          description={`Esta acción eliminará «${deleteName}» y todo su contenido de forma permanente.`}
          itemName={deleteName}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteBoardId(null)}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  BoardCard — componente interno para evitar duplicar el JSX        */
/* ------------------------------------------------------------------ */

interface BoardCardProps {
  board: BoardSummary;
  menuBoardId: string | null;
  renameBoardId: string | null;
  renameValue: string;
  onMenuToggle: (id: string) => void;
  onRenameStart: (id: string, name: string) => void;
  onRenameChange: (value: string) => void;
  onRenameFinish: (id: string) => void;
  onRenameCancel: () => void;
  onDelete: () => void;
  onClick: () => void;
}

function BoardCard({ board, menuBoardId, renameBoardId, renameValue, onMenuToggle, onRenameStart, onRenameChange, onRenameFinish, onRenameCancel, onDelete, onClick }: BoardCardProps) {
  return (
    <div
      data-testid={`board-card-${board.id}`}
      className="flex flex-col gap-2 p-4 rounded-xl text-left transition-all hover:scale-[1.02] cursor-pointer relative"
      style={{ background: "var(--card-overlay)", border: "1px solid var(--card-overlay-border)", boxShadow: "0 4px 16px rgba(0,0,0,.45)" }}
      onClick={onClick}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={14} style={{ color: "var(--sub)" }} className="shrink-0" />
          {renameBoardId === board.id ? (
            <input
              autoFocus
              value={renameValue}
              onChange={(e) => onRenameChange(e.target.value)}
              onBlur={() => onRenameFinish(board.id)}
              onKeyDown={(e) => { if (e.key === "Enter") onRenameFinish(board.id); if (e.key === "Escape") onRenameCancel(); }}
              onClick={(e) => e.stopPropagation()}
              className="text-sm font-medium bg-transparent outline-none border-b min-w-0"
              style={{ color: "var(--text)", borderColor: "var(--dashed-border)" }}
            />
          ) : (
            <span style={{ color: "var(--text)", opacity: 0.85 }} className="text-sm font-medium truncate">{board.name}</span>
          )}
        </div>
        {/* Three-dot menu */}
        <div data-menu-root="true" style={{ position: "relative" }} className="shrink-0">
          <PressableButton
            className="p-1 rounded-lg hover:opacity-70"
            style={{ color: "var(--sub)" }}
            onClick={(e) => { e.stopPropagation(); onMenuToggle(board.id); }}
          >
            <Ellipsis size={14} />
          </PressableButton>
          {menuBoardId === board.id && (
            <div
              className="absolute right-0 top-7 z-20 rounded-xl overflow-hidden text-xs w-32"
              style={{
                background: "var(--field)",
                border: "1px solid var(--field-border)",
                boxShadow: "0 14px 30px -12px rgba(0,0,0,.6)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <PressableButton
                className="flex items-center gap-1.5 w-full px-3 py-2 hover:opacity-80"
                style={{ color: "var(--text)" }}
                onClick={() => { onRenameStart(board.id, board.name); }}
              >
                <FileText size={13} /> Renombrar
              </PressableButton>
              <PressableButton
                className="flex items-center gap-1.5 w-full px-3 py-2 hover:opacity-80"
                style={{ color: "#F87171" }}
                onClick={onDelete}
              >
                <Trash2 size={13} /> Eliminar
              </PressableButton>
            </div>
          )}
        </div>
      </div>
      <span style={{ color: "var(--sub)" }} className="text-xs">{relativeTime(board.updated_at)}</span>
    </div>
  );
}
