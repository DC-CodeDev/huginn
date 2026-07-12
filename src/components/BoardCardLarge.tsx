import { FileText, Ellipsis, Trash2 } from "lucide-react";
import type { BoardSummary } from "../types";
import { PressableButton } from "./PressableButton";

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

/* Deterministic mini graph layout based on board id hash */
function hashId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h;
}

function BoardPreview({ boardId }: { boardId: string }) {
  const seed = hashId(boardId);
  const variant = seed % 4;

  const accentColor = "var(--accent)";
  const nodeStroke = "var(--card-border)";
  const nodeFill = "var(--card)";
  const edgeColor = "var(--sub)";

  const layouts = [
    /* variant 0: 1 left, 2 right */
    <svg key="0" viewBox="0 0 260 120" fill="none" style={{ width: "100%", height: "100%" }}>
      <rect x="16" y="35" width="88" height="50" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <rect x="156" y="14" width="88" height="40" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <rect x="156" y="66" width="88" height="40" rx="7" fill={`${accentColor}1A`} stroke={`${accentColor}50`} strokeWidth="1.5" />
      <path d="M104 52 C130 52 130 34 156 34" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
      <path d="M104 62 C130 62 130 86 156 86" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
    </svg>,
    /* variant 1: 3 in a line */
    <svg key="1" viewBox="0 0 260 120" fill="none" style={{ width: "100%", height: "100%" }}>
      <rect x="10" y="40" width="72" height="40" rx="7" fill={`${accentColor}1A`} stroke={`${accentColor}50`} strokeWidth="1.5" />
      <rect x="94" y="40" width="72" height="40" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <rect x="178" y="40" width="72" height="40" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <path d="M82 60 L94 60" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
      <path d="M166 60 L178 60" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
    </svg>,
    /* variant 2: top-center feeds 2 below */
    <svg key="2" viewBox="0 0 260 120" fill="none" style={{ width: "100%", height: "100%" }}>
      <rect x="86" y="10" width="88" height="36" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <rect x="16" y="68" width="100" height="40" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <rect x="144" y="68" width="100" height="40" rx="7" fill={`${accentColor}1A`} stroke={`${accentColor}50`} strokeWidth="1.5" />
      <path d="M110 46 C80 46 80 68 66 68" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
      <path d="M150 46 C180 46 180 68 194 68" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
    </svg>,
    /* variant 3: chain with curve */
    <svg key="3" viewBox="0 0 260 120" fill="none" style={{ width: "100%", height: "100%" }}>
      <rect x="10" y="16" width="80" height="36" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <rect x="90" y="62" width="80" height="36" rx="7" fill={nodeFill} stroke={nodeStroke} strokeWidth="1.5" />
      <rect x="170" y="16" width="80" height="36" rx="7" fill={`${accentColor}1A`} stroke={`${accentColor}50`} strokeWidth="1.5" />
      <path d="M90 34 C130 34 70 80 90 80" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
      <path d="M170 80 C190 80 190 34 170 34" stroke={edgeColor} strokeWidth="1" opacity="0.5" />
    </svg>,
  ];

  return (
    <div
      style={{
        flex: "1 1 0",
        background: "var(--field)",
        backgroundImage: "radial-gradient(rgba(255,255,255,0.025) 1.5px, transparent 1.5px)",
        backgroundSize: "22px 22px",
        padding: "12px 10px",
        overflow: "hidden",
      }}
    >
      {layouts[variant]}
    </div>
  );
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
      <BoardPreview boardId={board.id} />

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
