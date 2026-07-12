import { ChevronRight, Ellipsis, Trash2 } from "lucide-react";
import type { Folder } from "../types";
import { PressableButton } from "./PressableButton";

interface FolderRowProps {
  folder: Folder;
  menuFolderId: string | null;
  onMenuToggle: (id: string) => void;
  onDelete: () => void;
  onClick: () => void;
}

export function FolderRow({ folder, menuFolderId, onMenuToggle, onDelete, onClick }: FolderRowProps) {
  const isMenuOpen = menuFolderId === folder.id;

  return (
    <div
      data-testid={`folder-card-${folder.id}`}
      className="flex items-center gap-3 px-4 py-3.5 cursor-pointer transition-opacity hover:opacity-80"
      style={{ borderBottom: "1px solid var(--card-border)" }}
      onClick={() => { if (!isMenuOpen) onClick(); }}
    >
      <span style={{ fontSize: 10, color: "var(--sub)", flexShrink: 0 }}>▸</span>
      <span
        className="flex-1 min-w-0 truncate text-sm font-medium"
        style={{ color: "var(--text)" }}
      >
        {folder.name}
      </span>
      <span
        className="text-xs shrink-0"
        style={{ color: "var(--sub)" }}
      >
        Carpeta
      </span>

      <div data-menu-root="true" style={{ position: "relative" }} className="shrink-0">
        <PressableButton
          className="p-1 rounded-lg hover:opacity-70"
          style={{ color: "var(--sub)" }}
          onClick={(e) => { e.stopPropagation(); onMenuToggle(folder.id); }}
        >
          <Ellipsis size={13} />
        </PressableButton>
        {isMenuOpen && (
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
              style={{ color: "#F87171" }}
              onClick={onDelete}
            >
              <Trash2 size={13} /> Eliminar
            </PressableButton>
          </div>
        )}
      </div>

      <ChevronRight size={14} style={{ color: "var(--sub)", flexShrink: 0 }} />
    </div>
  );
}
