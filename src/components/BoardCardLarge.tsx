import { FileText, Ellipsis, Trash2 } from "lucide-react";
import type { BoardSummary } from "../types";
import { PressableButton } from "./PressableButton";
import { BoardThumbnail } from "./BoardThumbnail";

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

interface BoardCardLargeProps {
  board: BoardSummary;
  menuBoardId: string | null;
  renameBoardId: string | null;
  renameValue: string;
  onMenuToggle: (id: string) => void;
  onRenameStart: (id: string, name: string) => void;
  onRenameChange: (val: string) => void;
  onRenameFinish: (id: string) => void;
  onRenameCancel: () => void;
  onDelete: () => void;
  onClick: () => void;
}

export function BoardCardLarge({
  board, menuBoardId, renameBoardId, renameValue,
  onMenuToggle, onRenameStart, onRenameChange, onRenameFinish, onRenameCancel,
  onDelete, onClick,
}: BoardCardLargeProps) {
  const isMenuOpen = menuBoardId === board.id;
  const isRenaming = renameBoardId === board.id;

  return (
    <div
      data-testid={`board-card-${board.id}`}
      className="flex flex-col rounded-xl overflow-hidden cursor-pointer transition-all hover:scale-[1.02]"
      style={{
        background: "var(--card)",
        border: "1px solid var(--card-border)",
        boxShadow: "0 4px 20px rgba(0,0,0,.4)",
        minHeight: 200,
      }}
      onClick={onClick}
    >
      {/* Preview */}
      <BoardThumbnail boardId={board.id} nodeCount={board.node_count} edgeCount={board.edge_count} />

      {/* Info */}
      <div
        className="flex flex-col gap-1 px-4 py-3"
        style={{ borderTop: "1px solid var(--card-border)" }}
      >
        <div className="flex items-center justify-between gap-1">
          {isRenaming ? (
            <input
              autoFocus
              value={renameValue}
              onChange={(e) => onRenameChange(e.target.value)}
              onBlur={() => onRenameFinish(board.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onRenameFinish(board.id);
                if (e.key === "Escape") onRenameCancel();
              }}
              onClick={(e) => e.stopPropagation()}
              className="text-sm font-medium bg-transparent outline-none border-b flex-1 min-w-0"
              style={{ color: "var(--text)", borderColor: "var(--dashed-border)" }}
            />
          ) : (
            <span
              className="text-sm font-medium truncate flex-1 min-w-0"
              style={{ color: "var(--text)" }}
            >
              {board.name}
            </span>
          )}
          <div data-menu-root="true" style={{ position: "relative" }} className="shrink-0">
            <PressableButton
              className="p-1 rounded-lg hover:opacity-70"
              style={{ color: "var(--sub)" }}
              onClick={(e) => { e.stopPropagation(); onMenuToggle(board.id); }}
            >
              <Ellipsis size={13} />
            </PressableButton>
            {isMenuOpen && (
              <div
                className="absolute right-0 bottom-7 z-20 rounded-xl overflow-hidden text-xs w-32"
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
                  onClick={() => onRenameStart(board.id, board.name)}
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
        <span style={{ fontSize: 11.5, color: "var(--sub)" }}>
          {board.node_count} nodo{board.node_count !== 1 ? "s" : ""} · {relativeTime(board.updated_at)}
        </span>
      </div>
    </div>
  );
}
