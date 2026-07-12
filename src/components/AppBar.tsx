import { Settings, CircleUser, Sun, Moon } from "lucide-react";
import { Presence, SPRING_SNAPPY } from "bylgja";
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
      className="fixed app-safe-top-right z-30 flex items-center gap-1 rounded-2xl px-2 py-1.5"
      style={{ background: T.card, border: `1px solid ${T.cardBorder}`, boxShadow: "0 14px 34px -14px rgba(0,0,0,.6)" }}
    >
      <ToolBtn T={T} label={theme === "dark" ? "Tema claro" : "Tema oscuro"} onClick={onToggleTheme}>
        <div className="theme-icon-wrapper">
          <Presence show={theme !== "dark"} exitConfig={SPRING_SNAPPY} className="theme-icon theme-icon-sun">
            <Sun size={16} />
          </Presence>
          <Presence show={theme === "dark"} exitConfig={SPRING_SNAPPY} className="theme-icon theme-icon-moon">
            <Moon size={16} />
          </Presence>
        </div>
      </ToolBtn>
      <Sep T={T} />
      <ToolBtn T={T} label="Ajustes" onClick={onSettingsClick}><Settings size={16} /></ToolBtn>
      <ToolBtn T={T} label="Perfil" onClick={onProfileClick}><CircleUser size={16} /></ToolBtn>
    </div>
  );
}
