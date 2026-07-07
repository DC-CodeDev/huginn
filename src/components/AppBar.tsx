import { Settings, CircleUser, Sun, Moon } from "lucide-react";
import { ToolBtn } from "./ToolBtn";
import type { Theme } from "../lib/theme";
import { Sep } from "./Sep";

interface AppBarProps {
  T: Theme;
  theme: string;
  onToggleTheme: () => void;
  onSettingsClick: () => void;
  onProfileClick: () => void;
}

export function AppBar({ T, theme, onToggleTheme, onSettingsClick, onProfileClick }: AppBarProps) {
  return (
    <div
      className="fixed top-4 right-4 z-30 flex items-center gap-1 rounded-2xl px-2 py-1.5"
      style={{ background: T.card, border: `1px solid ${T.cardBorder}`, boxShadow: "0 14px 34px -14px rgba(0,0,0,.6)" }}
    >
      <ToolBtn T={T} label={theme === "dark" ? "Tema claro" : "Tema oscuro"} onClick={onToggleTheme}>
        {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
      </ToolBtn>
      <Sep T={T} />
      <ToolBtn T={T} label="Ajustes" onClick={onSettingsClick}><Settings size={16} /></ToolBtn>
      <ToolBtn T={T} label="Perfil" onClick={onProfileClick}><CircleUser size={16} /></ToolBtn>
    </div>
  );
}
