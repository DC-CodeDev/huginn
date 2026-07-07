import { useState } from "react";
import { Trash2, X } from "lucide-react";

interface ConfirmDeleteModalProps {
  /** Si se pasa, el modal exige escribir "BORRAR <typeToConfirmName>" para habilitar el botón */
  typeToConfirmName?: string;
  title: string;
  description: string;
  itemName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDeleteModal({
  typeToConfirmName,
  title,
  description,
  itemName,
  onConfirm,
  onCancel,
}: ConfirmDeleteModalProps) {
  const [inputValue, setInputValue] = useState("");
  const required = typeToConfirmName ? `BORRAR ${typeToConfirmName}` : null;
  const canConfirm = required ? inputValue === required : true;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.55)" }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div
        className="rounded-2xl w-[min(400px,90vw)] flex flex-col overflow-hidden"
        style={{
          background: "var(--card)",
          border: "1px solid var(--card-border)",
          boxShadow: "0 24px 60px -18px rgba(0,0,0,.8), 0 6px 16px -8px rgba(0,0,0,.6)",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Encabezado */}
        <div className="flex items-center gap-2 px-4 h-12 shrink-0" style={{ borderBottom: "1px solid #242938" }}>
          <Trash2 size={14} style={{ color: "#F87171" }} />
          <span className="text-sm font-medium flex-1" style={{ color: "var(--text)" }}>
            {title}
          </span>
          <button className="p-1 rounded-lg hover:opacity-70" style={{ color: "var(--sub)" }} onClick={onCancel}>
            <X size={15} />
          </button>
        </div>

        {/* Cuerpo */}
        <div className="px-4 py-4 flex flex-col gap-3">
          <p className="text-sm leading-relaxed" style={{ color: "var(--sub)" }}>
            {description}
          </p>

          {required ? (
            <>
              <p className="text-xs" style={{ color: "var(--text)" }}>
                Escribí <span className="font-semibold" style={{ color: "#F87171" }}>{required}</span> para confirmar:
              </p>
              <input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                placeholder={required}
                className="w-full rounded-xl px-3 py-2.5 text-sm outline-none"
                style={{ background: "var(--field)", border: "1px solid var(--field-border)", color: "var(--text)" }}
                autoFocus
              />
            </>
          ) : (
            <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
              ¿Eliminar <span className="font-semibold" style={{ color: "#F87171" }}>"{itemName}"</span>?
            </p>
          )}
        </div>

        {/* Acciones */}
        <div className="flex items-center justify-end gap-2 px-4 py-3" style={{ borderTop: "1px solid #242938" }}>
          <button
            className="px-3 py-1.5 rounded-xl text-xs font-medium hover:opacity-80"
            style={{ background: "var(--field)", border: "1px solid var(--field-border)", color: "var(--sub)" }}
            onClick={onCancel}
          >
            Cancelar
          </button>
          <button
            className="px-3 py-1.5 rounded-xl text-xs font-medium transition-opacity"
            style={{
              background: "rgba(248,113,113,.14)",
              border: "1px solid rgba(248,113,113,.4)",
              color: "#F87171",
              opacity: canConfirm ? 1 : 0.4,
              cursor: canConfirm ? "pointer" : "default",
            }}
            disabled={!canConfirm}
            onClick={canConfirm ? onConfirm : undefined}
          >
            Eliminar
          </button>
        </div>
      </div>
    </div>
  );
}
