import { Settings, Sun, Moon } from "lucide-react";
import { Presence, SPRING_SNAPPY } from "bylgja";
import type { User } from "../lib/auth-context";
import { PressableButton } from "./PressableButton";

interface NavBarProps {
  user: User;
  theme: string;
  onHomeClick: () => void;
  onToggleTheme: () => void;
  onSettingsClick: () => void;
  onProfileClick: () => void;
}

export function NavBar({ user, theme, onHomeClick, onToggleTheme, onSettingsClick, onProfileClick }: NavBarProps) {
  const initials = user.name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div
      className="fixed top-0 left-0 right-0 z-30"
      style={{ background: "var(--bg)", borderBottom: "1px solid var(--card-border)" }}
    >
      <div style={{ paddingTop: "var(--safe-top)" }}>
        <div
          className="flex items-center justify-between"
          style={{ height: 56, paddingLeft: "max(60px, calc(60px + var(--safe-left)))", paddingRight: "max(60px, calc(60px + var(--safe-right)))" }}
        >
          {/* Brand */}
          <button
            onClick={onHomeClick}
            className="flex items-center gap-2.5 transition-opacity hover:opacity-80"
          >
            <span
              style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--accent)", flexShrink: 0 }}
            />
            <span
              style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", letterSpacing: "-0.01em" }}
            >
              Huginn
            </span>
            <span style={{ fontSize: 11, color: "var(--sub)" }}>
              yggdrasil suite
            </span>
          </button>

          {/* Actions + User */}
          <div className="flex items-center gap-1">
            <PressableButton
              className="p-2 rounded-lg transition-opacity hover:opacity-70"
              style={{ color: "var(--sub)" }}
              onClick={onToggleTheme}
              aria-label={theme === "dark" ? "Tema claro" : "Tema oscuro"}
            >
              <div className="theme-icon-wrapper">
                <Presence show={theme !== "dark"} exitConfig={SPRING_SNAPPY} className="theme-icon theme-icon-sun">
                  <Sun size={14} />
                </Presence>
                <Presence show={theme === "dark"} exitConfig={SPRING_SNAPPY} className="theme-icon theme-icon-moon">
                  <Moon size={14} />
                </Presence>
              </div>
            </PressableButton>
            <PressableButton
              className="p-2 rounded-lg transition-opacity hover:opacity-70"
              style={{ color: "var(--sub)" }}
              onClick={onSettingsClick}
              aria-label="Ajustes"
            >
              <Settings size={14} />
            </PressableButton>

            <div style={{ width: 1, height: 16, background: "var(--card-border)", margin: "0 6px" }} />

            <PressableButton
              className="flex items-center gap-2 transition-opacity hover:opacity-80"
              onClick={onProfileClick}
            >
              <span style={{ fontSize: 12.5, color: "var(--sub)" }}>
                {user.name.toLowerCase()}
              </span>
              <span
                style={{
                  width: 28, height: 28, borderRadius: "50%",
                  background: "var(--card)", border: "1px solid var(--card-border)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, fontWeight: 700, color: "var(--sub)", letterSpacing: "0.05em",
                }}
              >
                {initials}
              </span>
            </PressableButton>
          </div>
        </div>
      </div>
    </div>
  );
}
