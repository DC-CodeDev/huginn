import { useState, useEffect } from "react";
import { ArrowLeft, Plus, Loader2, FolderIcon, FileText, Ellipsis, Trash2 } from "lucide-react";
import { api } from "../api";
import { renameBoard as renameBoardAction, deleteBoard as deleteBoardAction } from "../lib/board-actions";
import type { Studio, Folder, BoardSummary } from "../types";
import { CreateFolderModal } from "./CreateFolderModal";
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

interface StudioViewProps {
  studioId: string;
  onBack: () => void;
  onFolderClick: (folderId: string) => void;
  onBoardClick: (boardId: string) => void;
}

type MenuTarget =
  | { kind: "board"; id: string }
  | { kind: "folder"; id: string };

export function StudioView({ studioId, onBack, onFolderClick, onBoardClick }: StudioViewProps) {
  const [studio, setStudio] = useState<Studio | null>(null);
  const [folders, setFolders] = useState<Folder[] | null>(null);
  const [boards, setBoards] = useState<BoardSummary[] | null>(null);
  const [showCreateFolder, setShowCreateFolder] = useState(false);
  const [menuTarget, setMenuTarget] = useState<MenuTarget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<MenuTarget | null>(null);
  const [renameBoardId, setRenameBoardId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    api.listStudios().then((list) => {
      const s = list.find((x) => x.id === studioId);
      if (s) setStudio(s);
    });
    api.listFolders(studioId).then(setFolders).catch(() => setFolders([]));
    api.getStudioBoards(studioId).then((data) => {
      const all = [...data.root_boards, ...data.folder_boards];
      all.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      setBoards(all);
    }).catch(() => setBoards([]));
  }, [studioId]);

  // Cerrar menú contextual al hacer clic fuera
  useEffect(() => {
    if (!menuTarget) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-menu-root]')) setMenuTarget(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuTarget]);

  const doRename = async (id: string) => {
    const trimmed = renameValue.trim();
    if (!trimmed) { setRenameBoardId(null); return; }
    const result = await renameBoardAction(id, trimmed, boards);
    if (result.ok) {
      setBoards((prev) => prev ? prev.map((b) => b.id === id ? result.board : b) : prev);
    } else if (result.reason === "conflict") {
      console.error("Conflicto al renombrar: el board fue modificado por otro cliente");
    } else {
      console.error("Error al renombrar board", result.reason === "no-version" ? "sin versión" : result.error);
    }
    setRenameBoardId(null);
  };

  const handleFolderCreated = (folder: Folder) => {
    setFolders((prev) => prev ? [...prev, folder] : [folder]);
    setShowCreateFolder(false);
  };

  const createBoard = async () => {
    const board = await api.createBoard("Nuevo board", studioId);
    setBoards((prev) => [{
      id: board.id,
      name: board.name,
      version: board.version,
      created_at: "",
      updated_at: new Date().toISOString(),
      node_count: 0,
      edge_count: 0,
    }, ...(prev ?? [])]);
    onBoardClick(board.id);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      if (deleteTarget.kind === "board") {
        const result = await deleteBoardAction(deleteTarget.id, boards);
        if (result.ok) {
          setBoards((prev) => prev ? prev.filter((b) => b.id !== deleteTarget.id) : prev);
        } else if (result.reason === "conflict") {
          console.error("Conflicto al eliminar: el board fue modificado por otro cliente");
          // Recargar listados
          try {
            const data = await api.getStudioBoards(studioId);
            const all = [...data.root_boards, ...data.folder_boards];
            all.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
            setBoards(all);
          } catch { /* ignorar */ }
        } else if (result.reason !== "no-version") {
          console.error("Error al eliminar", result.error);
        }
      } else {
        await api.deleteFolder(deleteTarget.id);
        setFolders((prev) => prev ? prev.filter((f) => f.id !== deleteTarget.id) : prev);
      }
    } catch (e) {
      console.error("Error al eliminar", e);
    }
    setDeleteTarget(null);
  };

  const deleteName = deleteTarget
    ? deleteTarget.kind === "board"
      ? boards?.find((b) => b.id === deleteTarget.id)?.name ?? ""
      : folders?.find((f) => f.id === deleteTarget.id)?.name ?? ""
    : "";

  if (!studio || folders === null || boards === null) {
    return (
      <div className="w-full app-dvh app-safe-page flex items-center justify-center" style={{ background: "var(--bg)" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "var(--sub)" }} />
      </div>
    );
  }

  const recentBoards = boards.slice(0, RECENT_LIMIT);

  const cardBase = () =>
    "flex flex-col gap-2 p-4 rounded-xl text-left transition-all hover:scale-[1.02] cursor-pointer"
    + " relative";

  return (
    <div className="w-full app-dvh" style={{ background: "var(--bg)" }}>
      <div className="max-w-5xl mx-auto px-6 py-8 app-safe-page">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <button
            data-testid="back-to-home"
            onClick={onBack}
            className="p-2 rounded-xl transition-colors"
          style={{ color: "var(--sub)" }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "var(--sub)")}
          >
            <ArrowLeft size={20} />
          </button>
          <h1 style={{ color: "var(--text)" }} className="text-2xl font-semibold">{studio.name}</h1>
        </div>

        {/* Recent Boards */}
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
                <div
                  key={b.id}
                  data-testid={`board-card-${b.id}`}
                  className={cardBase()}
                  style={{ background: "var(--card-overlay)", border: "1px solid var(--card-overlay-border)", boxShadow: "0 4px 16px rgba(0,0,0,.45)" }}
                  onClick={() => { if (!menuTarget) onBoardClick(b.id); }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText size={14} style={{ color: "var(--sub)" }} className="shrink-0" />
                      {renameBoardId === b.id ? (
                        <input
                          autoFocus
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onBlur={() => doRename(b.id)}
                          onKeyDown={(e) => { if (e.key === "Enter") doRename(b.id); if (e.key === "Escape") setRenameBoardId(null); }}
                          onClick={(e) => e.stopPropagation()}
                          className="text-sm font-medium bg-transparent outline-none border-b min-w-0"
                          style={{ color: "var(--text)", borderColor: "var(--dashed-border)" }}
                        />
                      ) : (
                        <span style={{ color: "var(--text)", opacity: 0.85 }} className="text-sm font-medium truncate">{b.name}</span>
                      )}
                    </div>
                    {/* Three-dot menu */}
                    <div data-menu-root="true" style={{ position: "relative" }} className="shrink-0">
                      <button
                        className="p-1 rounded-lg hover:opacity-70"
                        style={{ color: "var(--sub)" }}
                        onClick={(e) => { e.stopPropagation(); setMenuTarget(menuTarget?.id === b.id && menuTarget?.kind === "board" ? null : { kind: "board", id: b.id }); }}
                      >
                        <Ellipsis size={14} />
                      </button>
                      {menuTarget?.kind === "board" && menuTarget.id === b.id && (
                        <div
                          className="absolute right-0 top-7 z-20 rounded-xl overflow-hidden text-xs w-32"
                          style={{
                            background: "var(--field)",
                            border: "1px solid var(--field-border)",
                            boxShadow: "0 14px 30px -12px rgba(0,0,0,.6)",
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            className="flex items-center gap-1.5 w-full px-3 py-2 hover:opacity-80"
                            style={{ color: "var(--text)" }}
                            onClick={() => { setRenameValue(b.name); setRenameBoardId(b.id); setMenuTarget(null); }}
                          >
                            <FileText size={13} /> Renombrar
                          </button>
                          <button
                            className="flex items-center gap-1.5 w-full px-3 py-2 hover:opacity-80"
                            style={{ color: "#F87171" }}
                            onClick={() => { setDeleteTarget({ kind: "board", id: b.id }); setMenuTarget(null); }}
                          >
                            <Trash2 size={13} /> Eliminar
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                  <span style={{ color: "var(--sub)" }} className="text-xs">{relativeTime(b.updated_at)}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Folders */}
        <section>
          <h2 style={{ color: "var(--sub)", opacity: 0.6 }} className="text-sm font-medium uppercase tracking-wider mb-4">
            Carpetas
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {folders.map((f) => (
              <div
                key={f.id}
                data-testid={`folder-card-${f.id}`}
                className={cardBase()}
                style={{ background: "var(--card-overlay)", border: "1px solid var(--card-overlay-border)", boxShadow: "0 4px 16px rgba(0,0,0,.45)" }}
                onClick={() => { if (!menuTarget) onFolderClick(f.id); }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <FolderIcon size={14} style={{ color: "var(--sub)" }} className="shrink-0" />
                    <span style={{ color: "var(--text)", opacity: 0.85 }} className="text-sm font-medium truncate">{f.name}</span>
                  </div>
                  {/* Three-dot menu */}
                  <div data-menu-root="true" style={{ position: "relative" }} className="shrink-0">
                    <button
                      className="p-1 rounded-lg hover:opacity-70"
                      style={{ color: "var(--sub)" }}
                      onClick={(e) => { e.stopPropagation(); setMenuTarget(menuTarget?.id === f.id && menuTarget?.kind === "folder" ? null : { kind: "folder", id: f.id }); }}
                    >
                      <Ellipsis size={14} />
                    </button>
                    {menuTarget?.kind === "folder" && menuTarget.id === f.id && (
                      <div
                        className="absolute right-0 top-7 z-20 rounded-xl overflow-hidden text-xs w-32"
                        style={{
                          background: "var(--field)",
                          border: "1px solid var(--field-border)",
                          boxShadow: "0 14px 30px -12px rgba(0,0,0,.6)",
                        }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          className="flex items-center gap-1.5 w-full px-3 py-2 hover:opacity-80"
                          style={{ color: "#F87171" }}
                          onClick={() => { setDeleteTarget({ kind: "folder", id: f.id }); setMenuTarget(null); }}
                        >
                          <Trash2 size={13} /> Eliminar
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <span style={{ color: "var(--sub)" }} className="text-xs">Carpeta</span>
              </div>
            ))}

            <button
              data-testid="create-folder-card"
              onClick={() => setShowCreateFolder(true)}
              className="flex flex-col items-center justify-center gap-2 p-4 rounded-xl transition-all hover:scale-[1.02]"
              style={{
                background: "var(--card-overlay)",
                border: "1px dashed var(--dashed-border)",
              }}
            >
              <Plus size={20} style={{ color: "var(--sub)" }} />
              <span style={{ color: "var(--sub)" }} className="text-sm font-medium">Nueva Carpeta</span>
            </button>
          </div>
        </section>
      </div>

      {showCreateFolder && (
        <CreateFolderModal
          studioId={studioId}
          onClose={() => setShowCreateFolder(false)}
          onCreated={handleFolderCreated}
        />
      )}

      {deleteTarget && (
        <ConfirmDeleteModal
          title={deleteTarget.kind === "board" ? "Eliminar Board" : "Eliminar Carpeta"}
          description={`Esta acción eliminará «${deleteName}» de forma permanente.`}
          itemName={deleteName}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  );
}
