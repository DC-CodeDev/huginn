import { useRef, useState, useEffect } from "react";
import { createPortal } from "react-dom";
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

interface MenuPos {
  top: number;
  left: number;
}

export function FolderRow({ folder, menuFolderId, onMenuToggle, onDelete, onClick }: FolderRowProps) {
  const isMenuOpen = menuFolderId === folder.id;
  const wrapRef = useRef<HTMLDivElement>(null);
  const [menuPos, setMenuPos] = useState<MenuPos | null>(null);

  useEffect(() => {
    if (!isMenuOpen || !wrapRef.current) {
      setMenuPos(null);
      return;
    }
    const rect = wrapRef.current.getBoundingClientRect();
    const MENU_W = 128;
    const MENU_H = 36;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let left = rect.right - MENU_W;
    if (left < 8) left = 8;
    if (left + MENU_W > vw - 8) left = vw - MENU_W - 8;

    const spaceBelow = vh - rect.bottom;
    const top = spaceBelow < MENU_H + 8 ? rect.top - MENU_H - 4 : rect.bottom + 4;

    setMenuPos({ top, left });
  }, [isMenuOpen]);

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

      <div data-menu-root="true" ref={wrapRef} className="shrink-0">
        <PressableButton
          className="p-1 rounded-lg hover:opacity-70"
          style={{ color: "var(--sub)" }}
          onClick={(e) => { e.stopPropagation(); onMenuToggle(folder.id); }}
        >
          <Ellipsis size={13} />
        </PressableButton>
      </div>

      {isMenuOpen && menuPos && createPortal(
        <div
          data-menu-root="true"
          className="fixed z-50 rounded-xl overflow-hidden text-xs w-32"
          style={{
            top: menuPos.top,
            left: menuPos.left,
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
        </div>,
        document.body
      )}

      <ChevronRight size={14} style={{ color: "var(--sub)", flexShrink: 0 }} />
    </div>
  );
}
