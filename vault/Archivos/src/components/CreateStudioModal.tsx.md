import { useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";
import type { Studio, StudioColor } from "../types";
import { STUDIO_COLORS } from "../types";

const STUDIO_COLOR_MAP: Record<StudioColor, string> = {
  terracota: "#C4847A",
  azul: "#7A9EC4",
  verde: "#7A9E7E",
  dorado: "#C4A87A",
  violeta: "#A88AC4",
  turquesa: "#7AC0BE",
};

interface CreateStudioModalProps {
  onClose: () => void;
  onCreated: (studio: Studio) => void;
}

export function CreateStudioModal({ onClose, onCreated }: CreateStudioModalProps) {
  const [name, setName] = useState("");
  const [color, setColor] = useState<StudioColor>("azul");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      const studio = await api.createStudio(name.trim(), color);
      onCreated(studio);
    } catch {
      setSaving(false);
    }
  };

  return (
    <div
      data-testid="create-studio-modal"
      className="fixed inset-0 z-50 flex items-center justify-center app-modal-backdrop"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="w-full max-w-sm mx-4 rounded-xl p-6 flex flex-col gap-5"
        style={{ background: "var(--card)", border: "1px solid var(--card-border)" }}
      >
        <div className="flex items-center justify-between">
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--text)" }}>Nuevo Estudio</h2>
          <button
            onClick={onClose}
            className="transition-colors"
            style={{ color: "var(--sub)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--sub)")}
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <label style={{ fontSize: 13, fontWeight: 600, color: "var(--sub)" }}>Nombre</label>
            <input
              data-testid="studio-name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Nombre del Estudio"
              autoFocus
              style={{
                background: "var(--bg)", border: "1px solid var(--card-border)",
                borderRadius: 10, padding: "12px 14px", fontSize: 14,
                color: "var(--text)", outline: "none",
                fontFamily: "inherit", transition: "border-color 0.2s",
              }}
              onFocus={(e) => (e.target.style.borderColor = "#C4847A")}
              onBlur={(e) => (e.target.style.borderColor = "var(--card-border)")}
              onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label style={{ fontSize: 13, fontWeight: 600, color: "var(--sub)" }}>Color</label>
            <div className="flex gap-3">
              {STUDIO_COLORS.map((c) => (
                <button
                  key={c}
                  data-testid={`color-swatch-${c}`}
                  onClick={() => setColor(c)}
                  className="rounded-full transition-all"
                  style={{
                    width: 36, height: 36,
                    background: STUDIO_COLOR_MAP[c],
                    outline: color === c ? "2px solid var(--text)" : "2px solid transparent",
                    outlineOffset: 2,
                    transform: color === c ? "scale(1.15)" : "scale(1)",
                  }}
                />
              ))}
            </div>
          </div>

          <button
            data-testid="studio-create-btn"
            onClick={handleSubmit}
            disabled={!name.trim() || saving}
            className="transition-colors"
            style={{
              background: !name.trim() || saving ? "var(--field)" : STUDIO_COLOR_MAP[color],
              color: !name.trim() || saving ? "var(--sub)" : "var(--bg)",
              border: "none", borderRadius: 10,
              padding: "12px 24px", fontSize: 14, fontWeight: 700,
              cursor: !name.trim() || saving ? "default" : "pointer",
              fontFamily: "inherit", width: "100%",
            }}
            onMouseEnter={(e) => {
              if (!name.trim() || saving) return;
              e.currentTarget.style.background = STUDIO_COLOR_MAP[color] + "DD";
            }}
            onMouseLeave={(e) => {
              if (!name.trim() || saving) return;
              e.currentTarget.style.background = STUDIO_COLOR_MAP[color];
            }}
          >
            {saving ? "Creando..." : "Crear Estudio"}
          </button>
        </div>
      </div>
    </div>
  );
}
