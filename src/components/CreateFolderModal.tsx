import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api } from "../api";
import type { Folder } from "../types";
import { AnimatedModal } from "./AnimatedModal";

interface CreateFolderModalProps {
  show: boolean;
  studioId: string;
  onClose: () => void;
  onCreated: (folder: Folder) => void;
}

export function CreateFolderModal({ show, studioId, onClose, onCreated }: CreateFolderModalProps) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  // Montado permanentemente para animar; reseteamos el formulario al abrir.
  useEffect(() => {
    if (show) {
      setName("");
      setSaving(false);
    }
  }, [show]);

  const handleSubmit = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    try {
      const folder = await api.createFolder(name.trim(), studioId);
      onCreated(folder);
    } catch {
      setSaving(false);
    }
  };

  return (
    <AnimatedModal show={show} onClose={onClose} closeOnEscape={false}>
      <div
        data-testid="create-folder-modal"
        className="w-full max-w-sm mx-4 rounded-2xl p-6"
        style={{ background: "var(--card)", border: "1px solid var(--card-overlay-border)" }}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 style={{ color: "var(--text)" }} className="text-lg font-semibold">Nueva Carpeta</h2>
          <button onClick={onClose} style={{ color: "var(--sub)" }} className="hover:opacity-70 transition-colors">
            <X size={18} />
          </button>
        </div>

        <input
          data-testid="folder-name-input"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre de la carpeta"
          autoFocus
          className="w-full px-3 py-2 rounded-xl text-sm mb-6 outline-none"
          style={{ background: "var(--btn-overlay)", border: "1px solid var(--btn-overlay-border)", color: "var(--text)" }}
          onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
        />

        <button
          data-testid="folder-create-btn"
          onClick={handleSubmit}
          disabled={!name.trim() || saving}
          className="w-full py-2 rounded-xl text-sm font-medium transition-opacity disabled:opacity-30"
          style={{ background: "var(--accent)", color: "var(--bg)" }}
        >
          {saving ? "Creando..." : "Crear Carpeta"}
        </button>
      </div>
    </AnimatedModal>
  );
}
