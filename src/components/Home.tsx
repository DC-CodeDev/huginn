import { useState, useEffect } from "react";
import { Loader2, Ellipsis, Trash2 } from "lucide-react";
import { api } from "../api";
import type { Studio, StudioColor } from "../types";
import { STUDIO_COLORS } from "../types";
import { CreateStudioModal } from "./CreateStudioModal";
import { ConfirmDeleteModal } from "./ConfirmDeleteModal";
import { PressableButton } from "./PressableButton";

const STUDIO_COLOR_MAP: Record<StudioColor, string> = {
  terracota: "#C4847A",
  azul: "#7A9EC4",
  verde: "#7A9E7E",
  dorado: "#C4A87A",
  violeta: "#A88AC4",
  turquesa: "#7AC0BE",
};

interface HomeProps {
  onStudioClick: (studioId: string) => void;
}

export function Home({ onStudioClick }: HomeProps) {
  const [studios, setStudios] = useState<Studio[] | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [menuStudioId, setMenuStudioId] = useState<string | null>(null);
  const [deleteStudioId, setDeleteStudioId] = useState<string | null>(null);

  const loadStudios = () => {
    api.listStudios()
      .then(setStudios)
      .catch(() => setStudios([]));
  };

  useEffect(() => { loadStudios(); }, []);

  // Cerrar menú contextual al hacer clic fuera
  useEffect(() => {
    if (!menuStudioId) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-menu-root]')) setMenuStudioId(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuStudioId]);

  const handleCreated = (studio: Studio) => {
    setStudios((prev) => prev ? [...prev, studio] : [studio]);
    setShowCreate(false);
  };

  if (studios === null) {
    return (
      <div className="w-full app-dvh app-safe-page flex items-center justify-center" style={{ background: "var(--bg)" }}>
        <Loader2 className="animate-spin" size={32} style={{ color: "var(--sub)" }} />
      </div>
    );
  }

  const isEmpty = studios.length === 0 && !showCreate;

  return (
    <div className="w-full app-dvh" style={{ background: "var(--bg)" }}>
      {isEmpty ? (
        /* ── 1d: Empty State ── */
        <div
          style={{
            width: "100%", minHeight: "var(--app-dvh)",
            background: "var(--bg)",
            display: "flex", flexDirection: "column",
            padding: "calc(52px + var(--safe-top)) calc(60px + var(--safe-right)) calc(52px + var(--safe-bottom)) calc(60px + var(--safe-left))",
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            color: "var(--text)",
          }}
        >
          <div style={{ maxWidth: 1000 }}>
            <div
              style={{
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                fontSize: 10, fontWeight: 500,
                letterSpacing: "0.16em", textTransform: "uppercase",
                color: "var(--accent)", marginBottom: 12,
              }}
            >
              Huginn
            </div>
            <h1 style={{ margin: 0, fontSize: 32, fontWeight: 700, letterSpacing: "-0.025em", color: "var(--text)" }}>
              Studios
            </h1>
          </div>

          <div
            style={{
              flex: "1 1 0%", display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
              textAlign: "center", gap: 6,
            }}
          >
            <span
              style={{
                width: 66, height: 66, borderRadius: 18,
                background: "var(--card)", border: "1px solid var(--card-border)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                color: "var(--accent)", marginBottom: 14,
              }}
            >
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
              >
                <circle cx="12" cy="4.5" r="2.5" />
                <path d="m10.2 6.3-3.9 3.9" />
                <circle cx="4.5" cy="12" r="2.5" />
                <path d="M7 12h10" />
                <circle cx="19.5" cy="12" r="2.5" />
                <path d="m13.8 17.7 3.9-3.9" />
                <circle cx="12" cy="19.5" r="2.5" />
              </svg>
            </span>
            <div style={{ fontSize: 19, fontWeight: 600, color: "var(--text)", letterSpacing: "-0.01em" }}>
              Todavía no creaste ningún Estudio
            </div>
            <p style={{ margin: "6px 0 26px", fontSize: 13.5, lineHeight: 1.6, color: "var(--sub)", maxWidth: 380 }}>
              Un Estudio es un universo propio para tus pizarras y carpetas, aislado del resto. Empezá creando el primero.
            </p>
            <button
              data-testid="empty-create-studio"
              className="empty-state-btn"
              onClick={() => setShowCreate(true)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
              >
                <path d="M5 12h14" />
                <path d="M12 5v14" />
              </svg>
              <span>Crear tu primer Estudio</span>
            </button>
          </div>
        </div>
      ) : (
        /* ── 1c: Dashboard con Estudios (Variante B — ficha con color) ── */
        <div
          style={{
            width: "100%", minHeight: "var(--app-dvh)",
            background: "var(--bg)",
            padding: "calc(52px + var(--safe-top)) calc(60px + var(--safe-right)) calc(52px + var(--safe-bottom)) calc(60px + var(--safe-left))",
            fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
            color: "var(--text)",
          }}
        >
          <div style={{ maxWidth: 1000 }}>
            <div
              style={{
                fontFamily: "'JetBrains Mono', ui-monospace, monospace",
                fontSize: 10, fontWeight: 500,
                letterSpacing: "0.16em", textTransform: "uppercase",
                color: "var(--accent)", marginBottom: 12,
              }}
            >
              Huginn
            </div>
            <h1 style={{ margin: 0, fontSize: 32, fontWeight: 700, letterSpacing: "-0.025em", color: "var(--text)" }}>
              Studios
            </h1>
            <p style={{ margin: "9px 0 38px", fontSize: 13.5, color: "var(--sub)", maxWidth: 560, lineHeight: 1.55 }}>
              Cada Estudio es un universo propio — sus carpetas y pizarras, aislados del resto. Elegí uno para empezar.
            </p>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                gap: 14,
              }}
            >
              {studios.map((s) => {
                const hex = STUDIO_COLOR_MAP[s.color];
                return (
                  <div
                    key={s.id}
                    data-testid={`studio-card-${s.id}`}
                    className="studio-card"
                    style={{
                      display: "flex", flexDirection: "column",
                      justifyContent: "space-between",
                      minHeight: 146, padding: 18,
                      background: "var(--card)",
                      border: "1px solid var(--card-border)",
                      borderRadius: 12,
                      cursor: "pointer",
                      fontFamily: "inherit",
                      textAlign: "left",
                      color: "var(--text)",
                      position: "relative",
                      boxShadow: "0 4px 16px rgba(0,0,0,.45)",
                    }}
                    onClick={() => { if (!menuStudioId) onStudioClick(s.id); }}
                  >
                    <div className="flex items-start justify-between">
                      <span
                        style={{
                          width: 42, height: 42, borderRadius: 11,
                          background: `${hex}26`,
                          border: `1px solid ${hex}59`,
                          display: "inline-flex", alignItems: "center", justifyContent: "center",
                          color: hex,
                        }}
                      >
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
                          stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
                        >
                          <circle cx="12" cy="4.5" r="2.5" />
                          <path d="m10.2 6.3-3.9 3.9" />
                          <circle cx="4.5" cy="12" r="2.5" />
                          <path d="M7 12h10" />
                          <circle cx="19.5" cy="12" r="2.5" />
                          <path d="m13.8 17.7 3.9-3.9" />
                          <circle cx="12" cy="19.5" r="2.5" />
                        </svg>
                      </span>
                      {/* Three-dot menu */}
                      <div data-menu-root="true" style={{ position: "relative" }}>
                        <PressableButton
                          className="p-1 rounded-lg hover:opacity-70"
                          style={{ color: "var(--sub)" }}
                          onClick={(e) => { e.stopPropagation(); setMenuStudioId(menuStudioId === s.id ? null : s.id); }}
                        >
                          <Ellipsis size={16} />
                        </PressableButton>
                        {menuStudioId === s.id && (
                          <div
                            className="absolute right-0 top-8 z-20 rounded-xl overflow-hidden text-xs w-32"
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
                              onClick={() => { setDeleteStudioId(s.id); setMenuStudioId(null); }}
                            >
                              <Trash2 size={13} /> Eliminar
                            </PressableButton>
                          </div>
                        )}
                      </div>
                    </div>
                    <span style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", letterSpacing: "-0.005em" }}>
                      {s.name}
                    </span>
                  </div>
                );
              })}

              <button
                data-testid="create-studio-card"
                onClick={() => setShowCreate(true)}
                className="new-studio-card"
                style={{
                  display: "flex", flexDirection: "column",
                  justifyContent: "space-between",
                  minHeight: 146, padding: 18,
                  background: "transparent",
                  border: "1px dashed rgba(86,92,112,0.55)",
                  borderRadius: 12,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  textAlign: "left",
                  color: "var(--text)",
                }}
              >
                <span
                  style={{
                    width: 42, height: 42, borderRadius: 11,
                    background: "var(--field)", border: "1px solid var(--card-border)",
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    color: "var(--accent)",
                  }}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
                  >
                    <path d="M5 12h14" />
                    <path d="M12 5v14" />
                  </svg>
                </span>
                <span>
                  <span style={{ display: "block", fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
                    Nuevo Estudio
                  </span>
                  <span style={{ display: "block", marginTop: 3, fontSize: 11.5, color: "var(--sub)" }}>
                    Se crea vacío.
                  </span>
                </span>
              </button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <CreateStudioModal
          onClose={() => setShowCreate(false)}
          onCreated={handleCreated}
        />
      )}

      {deleteStudioId && (() => {
        const studio = studios?.find((s) => s.id === deleteStudioId);
        if (!studio) return null;
        const handleDelete = async () => {
          try {
            await api.deleteStudio(deleteStudioId);
            setStudios((prev) => prev ? prev.filter((s) => s.id !== deleteStudioId) : prev);
          } catch (e) {
            console.error("Error al eliminar estudio", e);
          }
          setDeleteStudioId(null);
        };
        return (
          <ConfirmDeleteModal
            typeToConfirmName={studio.name}
            title="Eliminar Estudio"
            description={`Esta acción eliminará «${studio.name}» y todo su contenido (carpetas y boards) de forma permanente.`}
            itemName={studio.name}
            onConfirm={handleDelete}
            onCancel={() => setDeleteStudioId(null)}
          />
        );
      })()}
    </div>
  );
}
