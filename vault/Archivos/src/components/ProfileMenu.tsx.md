import { LogOut, CircleUser } from "lucide-react";
import type { Theme } from "../lib/theme";

interface ProfileMenuProps {
  T: Theme;
  theme: string;
  onCloseProfile: () => void;
  onClose: () => void;
}

export function ProfileMenu({ T, theme, onCloseProfile, onClose }: ProfileMenuProps) {
  return (
    <>
      {/* Backdrop */}
      <div
        className="absolute inset-0 z-40"
        onClick={onClose}
      />
      {/* Dropdown */}
      <div
        className="absolute z-50 rounded-xl py-1.5 min-w-[180px]"
        style={{
          top: 56,
          left: "auto",
          right: 16,
          background: T.card,
          border: `1px solid ${T.cardBorder}`,
          boxShadow: theme === "dark"
            ? "0 18px 40px -14px rgba(0,0,0,.7), 0 4px 12px -6px rgba(0,0,0,.5)"
            : "0 16px 34px -14px rgba(15,17,23,.35), 0 4px 10px -6px rgba(15,17,23,.15)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header info */}
        <div className="flex items-center gap-2.5 px-3.5 py-2.5" style={{ borderBottom: `1px solid ${T.cardBorder}` }}>
          <CircleUser size={20} style={{ color: T.sub }} />
          <div className="flex flex-col">
            <span className="text-sm font-medium leading-tight" style={{ color: T.text }}>Usuario</span>
            <span className="text-[11px]" style={{ color: T.sub }}>huginn@local</span>
          </div>
        </div>

        {/* Actions */}
        <div className="pt-1">
          <button
            className="flex items-center gap-2.5 w-full px-3.5 py-2 text-sm hover:opacity-80 transition-opacity"
            style={{ color: "#F87171" }}
            onClick={() => { onCloseProfile(); onClose(); }}
          >
            <LogOut size={15} /> Cerrar perfil
          </button>
        </div>
      </div>
    </>
  );
}
