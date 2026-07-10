import { useEffect, useRef, useState } from "react";
import { Trash2, X } from "lucide-react";
import { PressableButton } from "./PressableButton";
import { AnimatedModal } from "./AnimatedModal";

interface ConfirmDeleteModalProps {
  show: boolean;
  /** Si se pasa, el modal exige escribir "BORRAR <typeToConfirmName>" para habilitar el botón */
  typeToConfirmName?: string;
  title: string;
  description: string;
  itemName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDeleteModal({
  show,
  typeToConfirmName,
  title,
  description,
  itemName,
  onConfirm,
  onCancel,
}: ConfirmDeleteModalProps) {
  const [inputValue, setInputValue] = useState("");

  // El input arranca vacío cada vez que se abre (antes se reseteaba al
  // desmontarse; ahora el modal queda montado para animar entrada/salida).
  useEffect(() => {
    if (show) setInputValue("");
  }, [show]);

  // Congela el contenido mostrado mientras está visible, para que el texto no
  // parpadee vacío durante la animación de salida cuando el estado del padre
  // (el item a borrar) ya se puso en null.
  const cacheRef = useRef({ typeToConfirmName, title, description, itemName });
  if (show) cacheRef.current = { typeToConfirmName, title, description, itemName };
  const view = cacheRef.current;

  const required = view.typeToConfirmName ? `BORRAR ${view.typeToConfirmName}` : null;
  const canConfirm = required ? inputValue === required : true;

  return (
    <AnimatedModal show={show} onClose={onCancel} overlayClassName="app-modal-backdrop" closeOnEscape={false}>
      <div
        className="rounded-2xl w-[min(400px,90vw)] flex flex-col overflow-hidden"
        style={{
          background: "var(--card)",
          border: "1px solid var(--card-border)",
          boxShadow: "0 24px 60px -18px rgba(0,0,0,.8), 0 6px 16px -8px rgba(0,0,0,.6)",
        }}
      >
        {/* Encabezado */}
        <div className="flex items-center gap-2 px-4 h-12 shrink-0" style={{ borderBottom: "1px solid #242938" }}>
          <Trash2 size={14} style={{ color: "#F87171" }} />
          <span className="text-sm font-medium flex-1" style={{ color: "var(--text)" }}>
            {view.title}
          </span>
          <PressableButton className="p-1 rounded-lg hover:opacity-70" style={{ color: "var(--sub)" }} onClick={onCancel}>
            <X size={15} />
          </PressableButton>
        </div>

        {/* Cuerpo */}
        <div className="px-4 py-4 flex flex-col gap-3">
          <p className="text-sm leading-relaxed" style={{ color: "var(--sub)" }}>
            {view.description}
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
              ¿Eliminar <span className="font-semibold" style={{ color: "#F87171" }}>"{view.itemName}"</span>?
            </p>
          )}
        </div>

        {/* Acciones */}
        <div className="flex items-center justify-end gap-2 px-4 py-3" style={{ borderTop: "1px solid #242938" }}>
          <PressableButton
            className="px-3 py-1.5 rounded-xl text-xs font-medium hover:opacity-80"
            style={{ background: "var(--field)", border: "1px solid var(--field-border)", color: "var(--sub)" }}
            onClick={onCancel}
          >
            Cancelar
          </PressableButton>
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
    </AnimatedModal>
  );
}
