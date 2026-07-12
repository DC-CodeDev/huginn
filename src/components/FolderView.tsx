import { useState, useEffect } from "react";
import { ChevronLeft, Loader2 } from "lucide-react";
import { api } from "../api";
import { renameBoard as renameBoardAction, deleteBoard as deleteBoardAction } from "../lib/board-actions";
import type { Folder, BoardSummary, Studio } from "../types";
import { ConfirmDeleteModal } from "./ConfirmDeleteModal";
import { BoardCardLarge } from "./BoardCardLarge";

function relativeTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = Math.floor((now - then) / 1000);
  if (diff < 60) return "Ahora";
  if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
  if (diff < 604800) return `hace ${Math.floor(diff / 86400)} d`;
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
  const [studio, setStudio] = useState<Studio | null>(null);
  const [folderBoards, setFolderBoards] = useState<BoardSummary[] | null>(null);
  const [menuBoardId, setMenuBoardId] = useState<string | null>(null);
  const [deleteBoardId, setDeleteBoardId] = useState<string | null>(null);
  const [renameBoardId, setRenameBoardId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    api.listStudios().then((list) => {
      const s = list.find((x) => x.id === studioId);
      if (s) setStudio(s);
    });
    api.listFolders(studioId).then((list) => {
      const f = list.find((x) => x.id === folderId);
      if (f) setFolder(f);
    });
    api.listFolderBoards(folderId).then((data) => {
      const sorted = [...data].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      setFolderBoards(sorted.slice(0, RECENT_LIMIT));
    }).catch(() => setFolderBoards([]));
  }, [folderId, studioId]);

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
    const result = await renameBoardAction(id, trimmed, folderBoards);
    if (result.ok) {
      setFolderBoards((prev) => prev ? prev.map((b) => b.id === id ? result.board : b) : prev);
    } else if (result.reason === "conflict") {
      console.error("Conflicto al renombrar: el board fue modificado por otro cliente");
    } else {
      console.error("Error al renombrar board", result.reason === "no-version" ? "sin versión" : result.error);
    }
    setRenameBoardId(null);
  };

  const createBoard = async () => {
    const board = await api.createBoard("Nuevo board", studioId, folderId);
    const summary: BoardSummary = {
      id: board.id, name: board.name, version: board.version,
      created_at: "", updated_at: new Date().toISOString(), node_count: 0, edge_count: 0,
    };
    setFolderBoards((prev) => prev ? [summary, ...prev].slice(0, RECENT_LIMIT) : [summary]);
    onBoardClick(board.id);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteBoardId) return;
    const result = await deleteBoardAction(deleteBoardId, folderBoards);
    if (result.ok) {
      setFolderBoards((prev) => prev ? prev.filter((b) => b.id !== deleteBoardId) : prev);
    } else if (result.reason === "conflict") {
      console.error("Conflicto al eliminar: el board fue modificado por otro cliente");
      try {
        const data = await api.getStudioBoards(studioId);
        const all = [...data.root_boards, ...data.folder_boards];
        all.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
        setFolderBoards(all.slice(0, RECENT_LIMIT));
      } catch { /* ignorar */ }
    } else if (result.reason !== "no-version") {
      console.error("Error al eliminar board", result.error);
    }
    setDeleteBoardId(null);
  };

  const deleteName = deleteBoardId
    ? folderBoards?.find((b) => b.id === deleteBoardId)?.name ?? ""
    : "";

  if (!folder || folderBoards === null) {
    return (
      <div className="w-full app-dvh flex items-center justify-center" style={{ background: "var(--bg)" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "var(--sub)" }} />
      </div>
    );
  }

  const latestUpdate = folderBoards.length > 0 ? folderBoards[0].updated_at : null;
  const studioName = studio?.name ?? "";

  return (
    <div className="w-full" style={{ background: "var(--bg)", minHeight: "var(--app-dvh)" }}>
      <div
        style={{
          maxWidth: 1000,
          marginInline: "auto",
          paddingTop: "calc(56px + var(--safe-top) + 48px)",
          paddingBottom: "calc(52px + var(--safe-bottom))",
          paddingLeft: "max(60px, calc(60px + var(--safe-left)))",
          paddingRight: "max(60px, calc(60px + var(--safe-right)))",
        }}
      >
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 mb-8">
          <button
            data-testid="back-to-studio"
            onClick={onBack}
            className="flex items-center gap-1 transition-opacity hover:opacity-70"
            style={{ color: "var(--sub)" }}
          >
            <ChevronLeft size={14} />
          </button>
          <button
            onClick={onBack}
            style={{
              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
              fontSize: 10, fontWeight: 500,
              letterSpacing: "0.14em", textTransform: "uppercase",
              color: "var(--accent)",
              transition: "opacity 0.15s",
            }}
            className="hover:opacity-70 transition-opacity"
          >
            {studioName || "Studio"}
          </button>
          <span
            style={{
              fontFamily: "'JetBrains Mono', ui-monospace, monospace",
              fontSize: 10, fontWeight: 500,
              letterSpacing: "0.14em", textTransform: "uppercase",
              color: "var(--sub)",
            }}
          >
            / Carpeta
          </span>
        </div>

        {/* Folder Header */}
        <div className="flex items-start justify-between gap-4 mb-10">
          <div>
            <h1
              style={{
                margin: 0, fontSize: 36, fontWeight: 700,
                letterSpacing: "-0.025em", color: "var(--text)", lineHeight: 1.1,
              }}
            >
              {folder.name}
            </h1>
            <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--sub)" }}>
              {folderBoards.length} board{folderBoards.length !== 1 ? "s" : ""}
              {latestUpdate && ` · editado ${relativeTime(latestUpdate)}`}
            </p>
          </div>

          <button
            data-testid="create-board-btn"
            onClick={createBoard}
            className="shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-opacity hover:opacity-80"
            style={{
              color: "var(--text)", marginTop: 4,
              background: "transparent",
              border: "1px solid var(--card-border)",
            }}
          >
            + Nuevo Board
          </button>
        </div>

        {/* Boards grid */}
        {folderBoards.length === 0 ? (
          <p style={{ color: "var(--sub)", fontSize: 13 }}>No hay boards en esta carpeta todavía.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {folderBoards.map((b) => (
              <BoardCardLarge
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
      </div>

      <ConfirmDeleteModal
        show={!!deleteBoardId}
        title="Eliminar Board"
        description={`Esta acción eliminará «${deleteName}» y todo su contenido de forma permanente.`}
        itemName={deleteName}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteBoardId(null)}
      />
    </div>
  );
}
