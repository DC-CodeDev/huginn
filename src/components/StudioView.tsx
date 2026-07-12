import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { api } from "../api";
import { renameBoard as renameBoardAction, deleteBoard as deleteBoardAction } from "../lib/board-actions";
import type { Studio, Folder, BoardSummary } from "../types";
import { CreateFolderModal } from "./CreateFolderModal";
import { ConfirmDeleteModal } from "./ConfirmDeleteModal";
import { SectionHeader } from "./SectionHeader";
import { BoardCardLarge } from "./BoardCardLarge";
import { FolderRow } from "./FolderRow";

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

  useEffect(() => {
    if (!menuTarget) return;
    const mouseHandler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-menu-root]')) setMenuTarget(null);
    };
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuTarget(null);
    };
    document.addEventListener("mousedown", mouseHandler);
    document.addEventListener("keydown", keyHandler);
    return () => {
      document.removeEventListener("mousedown", mouseHandler);
      document.removeEventListener("keydown", keyHandler);
    };
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
      id: board.id, name: board.name, version: board.version,
      created_at: "", updated_at: new Date().toISOString(), node_count: 0, edge_count: 0,
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
      <div className="w-full app-dvh flex items-center justify-center" style={{ background: "var(--bg)" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "var(--sub)" }} />
      </div>
    );
  }

  const recentBoards = boards.slice(0, RECENT_LIMIT);
  const latestUpdate = boards.length > 0 ? boards[0].updated_at : null;

  const menuBoardId = menuTarget?.kind === "board" ? menuTarget.id : null;
  const menuFolderId = menuTarget?.kind === "folder" ? menuTarget.id : null;

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
        {/* Studio Header */}
        <div className="mb-10">
          <div className="flex items-center gap-2" style={{ marginBottom: 10 }}>
            <button
              onClick={onBack}
              className="hover:opacity-70 transition-opacity"
              style={{
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                fontSize: 13, fontWeight: 500,
                letterSpacing: "0.12em",
                color: "var(--accent)",
                cursor: "pointer",
              }}
            >
              Studios
            </button>
            <span
              style={{
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                fontSize: 13,
                color: "var(--sub)",
                opacity: 0.5,
              }}
            >
              →
            </span>
            <span
              style={{
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                fontSize: 13, fontWeight: 600,
                color: "var(--text)",
              }}
            >
              {studio.name}
            </span>
          </div>

          <div className="flex items-start justify-between gap-4">
            <div>
              <h1
                style={{
                  margin: 0, fontSize: 36, fontWeight: 700,
                  letterSpacing: "-0.025em", color: "var(--text)", lineHeight: 1.1,
                }}
              >
                {studio.name}
              </h1>
              <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--sub)" }}>
                {folders.length} carpeta{folders.length !== 1 ? "s" : ""} · {boards.length} board{boards.length !== 1 ? "s" : ""}
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
        </div>

        {/* Recent Boards */}
        <section className="mb-10">
          <SectionHeader title="Boards recientes" />
          {recentBoards.length === 0 ? (
            <p style={{ color: "var(--sub)", fontSize: 13 }}>No hay boards en este Studio todavía.</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {recentBoards.map((b) => (
                <BoardCardLarge
                  key={b.id}
                  board={b}
                  menuBoardId={menuBoardId}
                  renameBoardId={renameBoardId}
                  renameValue={renameValue}
                  onMenuToggle={(id) => setMenuTarget(menuBoardId === id ? null : { kind: "board", id })}
                  onRenameStart={(id, name) => { setRenameValue(name); setRenameBoardId(id); setMenuTarget(null); }}
                  onRenameChange={setRenameValue}
                  onRenameFinish={doRename}
                  onRenameCancel={() => setRenameBoardId(null)}
                  onDelete={() => { setDeleteTarget({ kind: "board", id: b.id }); setMenuTarget(null); }}
                  onClick={() => { if (!menuTarget) onBoardClick(b.id); }}
                />
              ))}
            </div>
          )}
        </section>

        {/* Folders */}
        <section>
          <SectionHeader
            title="Carpetas"
            action={
              <button
                data-testid="create-folder-card"
                onClick={() => setShowCreateFolder(true)}
                className="text-xs px-3 py-1.5 rounded-xl transition-opacity hover:opacity-70"
                style={{
                  color: "var(--text)",
                  background: "var(--card)",
                  border: "1px solid var(--card-border)",
                }}
              >
                Nueva carpeta
              </button>
            }
          />
          <div
            style={{
              background: "var(--card)",
              border: "1px solid var(--card-border)",
              borderRadius: 12,
              overflow: "hidden",
            }}
          >
            {folders.length === 0 ? (
              <p style={{ color: "var(--sub)", fontSize: 13, padding: "16px 20px" }}>
                No hay carpetas en este Studio todavía.
              </p>
            ) : (
              folders.map((f) => (
                <FolderRow
                  key={f.id}
                  folder={f}
                  menuFolderId={menuFolderId}
                  onMenuToggle={(id) => setMenuTarget(menuFolderId === id ? null : { kind: "folder", id })}
                  onDelete={() => { setDeleteTarget({ kind: "folder", id: f.id }); setMenuTarget(null); }}
                  onClick={() => onFolderClick(f.id)}
                />
              ))
            )}
          </div>
        </section>
      </div>

      <CreateFolderModal
        show={showCreateFolder}
        studioId={studioId}
        onClose={() => setShowCreateFolder(false)}
        onCreated={handleFolderCreated}
      />

      <ConfirmDeleteModal
        show={!!deleteTarget}
        title={deleteTarget?.kind === "board" ? "Eliminar Board" : "Eliminar Carpeta"}
        description={`Esta acción eliminará «${deleteName}» de forma permanente.`}
        itemName={deleteName}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
