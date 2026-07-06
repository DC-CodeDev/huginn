import { useState, useEffect } from "react";
import { ArrowLeft, Loader2, FileText, Plus, Ellipsis, Trash2, FolderOpen } from "lucide-react";
import { api } from "../api";
import type { Folder, BoardSummary } from "../types";
import { ConfirmDeleteModal } from "./ConfirmDeleteModal";

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

  const createBoard = async () => {
    const board = await api.createBoard("Nuevo board", studioId, folderId);
    const summary: BoardSummary = {
      id: board.id,
      name: board.name,
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
    try {
      await api.deleteBoard(deleteBoardId);
      setRecentBoards((prev) => prev ? prev.filter((b) => b.id !== deleteBoardId) : prev);
      setFolderBoards((prev) => prev ? prev.filter((b) => b.id !== deleteBoardId) : prev);
    } catch (e) {
      console.error("Error al eliminar board", e);
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
      <div className="w-full h-screen flex items-center justify-center" style={{ background: "#0F1117" }}>
        <Loader2 className="animate-spin text-white/40" size={32} />
      </div>
    );
  }

  return (
    <div className="w-full min-h-screen" style={{ background: "#0F1117" }}>
      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button
            data-testid="back-to-studio"
            onClick={onBack}
            className="p-2 rounded-xl text-white/50 hover:text-white/80 hover:bg-white/5 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <h1 className="text-2xl font-semibold text-white">{folder.name}</h1>
        </div>

        {/* Archivos recientes (de todo el Studio) */}
        <section className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider">
              Archivos recientes
            </h2>
            <button
              data-testid="create-board-btn"
              onClick={() => createBoard()}
              className="px-3 py-1.5 rounded-xl text-xs font-medium text-white/70 hover:text-white transition-colors"
              style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)" }}
            >
              + Nuevo Board
            </button>
          </div>
          {recentBoards.length === 0 ? (
            <p className="text-white/25 text-sm">No hay boards en este Studio todavía</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {recentBoards.map((b) => (
                <BoardCard
                  key={b.id}
                  board={b}
                  menuBoardId={menuBoardId}
                  onMenuToggle={(id) => setMenuBoardId(menuBoardId === id ? null : id)}
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
            <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4">
              Boards en esta carpeta
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {folderBoards.map((b) => (
                <BoardCard
                  key={b.id}
                  board={b}
                  menuBoardId={menuBoardId}
                  onMenuToggle={(id) => setMenuBoardId(menuBoardId === id ? null : id)}
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
  onMenuToggle: (id: string) => void;
  onDelete: () => void;
  onClick: () => void;
}

function BoardCard({ board, menuBoardId, onMenuToggle, onDelete, onClick }: BoardCardProps) {
  return (
    <div
      data-testid={`board-card-${board.id}`}
      className="flex flex-col gap-2 p-4 rounded-xl text-left transition-all hover:scale-[1.02] cursor-pointer relative"
      style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)", boxShadow: "0 4px 16px rgba(0,0,0,.45)" }}
      onClick={onClick}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={14} className="text-white/30 shrink-0" />
          <span className="text-white/80 text-sm font-medium truncate">{board.name}</span>
        </div>
        {/* Three-dot menu */}
        <div data-menu-root="true" style={{ position: "relative" }} className="shrink-0">
          <button
            className="p-1 rounded-lg hover:opacity-70"
            style={{ color: "#8A90A3" }}
            onClick={(e) => { e.stopPropagation(); onMenuToggle(board.id); }}
          >
            <Ellipsis size={14} />
          </button>
          {menuBoardId === board.id && (
            <div
              className="absolute right-0 top-7 z-20 rounded-xl overflow-hidden text-xs w-32"
              style={{
                background: "#0C0E14",
                border: "1px solid #1E2230",
                boxShadow: "0 14px 30px -12px rgba(0,0,0,.6)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                className="flex items-center gap-1.5 w-full px-3 py-2 hover:opacity-80"
                style={{ color: "#F87171" }}
                onClick={onDelete}
              >
                <Trash2 size={13} /> Eliminar
              </button>
            </div>
          )}
        </div>
      </div>
      <span className="text-white/25 text-xs">{relativeTime(board.updated_at)}</span>
    </div>
  );
}
