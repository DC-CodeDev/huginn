import { X, Spline, Minus, Grid3x3, EyeOff, Eye, RotateCcw, Sun, Moon } from "lucide-react";
import type { Theme } from "../lib/theme";

interface SettingsModalProps {
  T: Theme;
  theme: string;
  mode: "app" | "board";
  showGrid?: boolean;
  defaultCurved?: boolean;
  showHelp?: boolean;
  onChangeShowGrid?: (v: boolean) => void;
  onChangeDefaultCurved?: (v: boolean) => void;
  onChangeShowHelp?: (v: boolean) => void;
  onReset?: () => void;
  onToggleTheme?: () => void;
  onClose: () => void;
}

export function SettingsModal({
  T, theme, mode,
  showGrid, defaultCurved, showHelp,
  onChangeShowGrid, onChangeDefaultCurved, onChangeShowHelp,
  onReset, onToggleTheme, onClose,
}: SettingsModalProps) {
  const row = "flex items-center justify-between px-4 py-3 rounded-xl";
  const label = "text-sm font-medium";
  const toggleBase = "relative w-9 h-5 rounded-full transition-colors cursor-pointer";
  const thumb = "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform";

  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.45)" }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="rounded-2xl w-[min(380px,90vw)] flex flex-col overflow-hidden"
        style={{
          background: T.card,
          border: `1px solid ${T.cardBorder}`,
          boxShadow: theme === "dark"
            ? "0 24px 60px -18px rgba(0,0,0,.8), 0 6px 16px -8px rgba(0,0,0,.6)"
            : "0 22px 50px -18px rgba(15,17,23,.4), 0 6px 14px -8px rgba(15,17,23,.2)",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-2 px-4 h-12 shrink-0" style={{ borderBottom: `1px solid ${T.cardBorder}` }}>
          <span className="text-sm font-medium flex-1" style={{ color: T.text }}>
            Ajustes
          </span>
          <button className="p-1 rounded-lg hover:opacity-70" style={{ color: T.sub }} onClick={onClose} title="Cerrar">
            <X size={15} />
          </button>
        </div>

        {/* Body */}
        <div className="p-3 flex flex-col gap-1.5">
          {/* Theme toggle (app mode) */}
          {mode === "app" && (
            <div className={row} style={{ background: T.field }}>
              <div className="flex items-center gap-2.5">
                {theme === "dark" ? <Sun size={15} style={{ color: T.sub }} /> : <Moon size={15} style={{ color: T.sub }} />}
                <span className={label} style={{ color: T.text }}>Tema {theme === "dark" ? "oscuro" : "claro"}</span>
              </div>
              <button
                className={toggleBase}
                style={{ background: "#C4847A" }}
                onClick={onToggleTheme}
                role="switch"
                aria-checked={theme === "dark"}
              >
                <span className={thumb} style={{ transform: theme === "dark" ? "translateX(16px)" : "translateX(0)" }} />
              </button>
            </div>
          )}

          {/* Board-specific settings */}
          {mode === "board" && (
            <>
              {/* Grid dots */}
              <div className={row} style={{ background: T.field }}>
                <div className="flex items-center gap-2.5">
                  <Grid3x3 size={15} style={{ color: T.sub }} />
                  <span className={label} style={{ color: T.text }}>Cuadrícula de puntos</span>
                </div>
                <button
                  className={toggleBase}
                  style={{ background: showGrid ? "#C4847A" : T.cardBorder }}
                  onClick={() => onChangeShowGrid?.(!showGrid)}
                  role="switch"
                  aria-checked={showGrid}
                >
                  <span className={thumb} style={{ transform: showGrid ? "translateX(16px)" : "translateX(0)" }} />
                </button>
              </div>

              {/* Default edge curvature */}
              <div className={row} style={{ background: T.field }}>
                <div className="flex items-center gap-2.5">
                  {defaultCurved ? <Spline size={15} style={{ color: T.sub }} /> : <Minus size={15} style={{ color: T.sub }} />}
                  <span className={label} style={{ color: T.text }}>Aristas curvas por defecto</span>
                </div>
                <button
                  className={toggleBase}
                  style={{ background: defaultCurved ? "#C4847A" : T.cardBorder }}
                  onClick={() => onChangeDefaultCurved?.(!defaultCurved)}
                  role="switch"
                  aria-checked={defaultCurved}
                >
                  <span className={thumb} style={{ transform: defaultCurved ? "translateX(16px)" : "translateX(0)" }} />
                </button>
              </div>

              {/* Show help */}
              <div className={row} style={{ background: T.field }}>
                <div className="flex items-center gap-2.5">
                  {showHelp ? <Eye size={15} style={{ color: T.sub }} /> : <EyeOff size={15} style={{ color: T.sub }} />}
                  <span className={label} style={{ color: T.text }}>Mostrar ayuda en canvas</span>
                </div>
                <button
                  className={toggleBase}
                  style={{ background: showHelp ? "#C4847A" : T.cardBorder }}
                  onClick={() => onChangeShowHelp?.(!showHelp)}
                  role="switch"
                  aria-checked={showHelp}
                >
                  <span className={thumb} style={{ transform: showHelp ? "translateX(16px)" : "translateX(0)" }} />
                </button>
              </div>

              {/* Reset */}
              <button
                className="flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium mt-2 hover:opacity-85 transition-opacity"
                style={{ background: "rgba(196,132,122,.12)", border: "1px solid rgba(196,132,122,.35)", color: "#C4847A" }}
                onClick={onReset}
              >
                <RotateCcw size={14} /> Restablecer valores predeterminados
              </button>
            </>
          )}

          {/* Version info (app mode) */}
          {mode === "app" && (
            <div className="text-center mt-3" style={{ color: T.sub }}>
              <span className="text-[11px]">Huginn Nodeboard v1.0.0</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
