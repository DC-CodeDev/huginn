import { useEffect, useMemo, useRef, useState } from "react";
import { X, Tag, Plus, Loader2 } from "lucide-react";
import { api } from "../api";
import type { Theme } from "../lib/theme";
import { PressableButton } from "./PressableButton";

interface TagsModalProps {
  T: Theme;
  theme: string;
  boardId: string | null;
  nodeTitle: string;
  tags: string[];                 // tags asignados al nodo (fuente: estado del tablero)
  localBoardTags: string[];       // tags derivados del estado local (unión con los del servidor)
  setTags: (tags: string[]) => void; // persiste vía el autosave del tablero (update en NodeBoard)
  onClose: () => void;
}

type FetchState = "loading" | "ready" | "error";

/**
 * Modal de edición de tags de un nodo (Fase 2).
 *
 * - Al abrir pide GET /api/boards/{boardId}/tags (loading/error). La lista de sugerencias
 *   es la UNIÓN de esos tags con los derivados del estado local (`localBoardTags`): así un
 *   tag recién creado en otro nodo aparece de inmediato aunque el autosave del tablero
 *   (PUT debounced) todavía no haya persistido, y si el fetch falla el modal sigue usable.
 * - Guardar no llama PATCH: muta el nodo vía `setTags`, que fluye por el mismo autosave que
 *   usa el resto de la app (título, bloques, puertos…). Cada acción es inmediata.
 */
export function TagsModal({ T, theme, boardId, nodeTitle, tags, localBoardTags, setTags, onClose }: TagsModalProps) {
  const [query, setQuery] = useState("");
  const [serverTags, setServerTags] = useState<string[]>([]);
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!boardId) { setFetchState("ready"); return; } // tablero aún no cargado: solo estado local
    const controller = new AbortController();
    setFetchState("loading");
    void api.getBoardTags(boardId)
      .then((list) => { if (!controller.signal.aborted) { setServerTags(list); setFetchState("ready"); } })
      .catch((error) => {
        if (!controller.signal.aborted) {
          console.error("No se pudieron cargar los tags del tablero", error);
          setFetchState("error");
        }
      });
    return () => controller.abort();
  }, [boardId]);

  // Pool de sugerencias: unión servidor + local, sin los ya asignados (case-insensitive).
  const suggestions = useMemo(() => {
    const assigned = new Set(tags.map((t) => t.toLowerCase()));
    const pool = new Map<string, string>(); // lower -> casing a mostrar
    for (const t of [...serverTags, ...localBoardTags]) {
      const key = t.toLowerCase();
      if (!assigned.has(key) && !pool.has(key)) pool.set(key, t);
    }
    const q = query.trim().toLowerCase();
    const list = [...pool.values()];
    const filtered = q ? list.filter((t) => t.toLowerCase().includes(q)) : list;
    return filtered.sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
  }, [serverTags, localBoardTags, tags, query]);

  const q = query.trim();
  const existsSomewhere = useMemo(() => {
    const key = q.toLowerCase();
    return [...tags, ...serverTags, ...localBoardTags].some((t) => t.toLowerCase() === key);
  }, [q, tags, serverTags, localBoardTags]);
  const canCreate = q.length > 0 && !existsSomewhere;

  const addTag = (raw: string) => {
    const t = raw.trim();
    if (!t) return;
    if (tags.some((x) => x.toLowerCase() === t.toLowerCase())) { setQuery(""); return; }
    setTags([...tags, t]);
    setQuery("");
  };

  const removeTag = (t: string) => setTags(tags.filter((x) => x !== t));

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (!q) return;
      // Enter reutiliza un tag existente que matchee exacto (case-insensitive); si no, crea.
      const exact = suggestions.find((t) => t.toLowerCase() === q.toLowerCase());
      addTag(exact ?? q);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  const chipBase = "flex items-center gap-1 rounded-full text-xs pl-2.5 pr-1 py-1 transition-opacity";
  const suggBase = "rounded-full text-xs px-2.5 py-1 hover:opacity-80 transition-opacity";

  return (
    <div
      className="absolute inset-0 z-40 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.45)" }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="rounded-2xl w-[min(420px,90vw)] max-h-[80vh] flex flex-col overflow-hidden"
        style={{
          background: T.card,
          border: `1px solid ${T.cardBorder}`,
          boxShadow: theme === "dark"
            ? "0 24px 60px -18px rgba(0,0,0,.8), 0 6px 16px -8px rgba(0,0,0,.6)"
            : "0 22px 50px -18px rgba(15,17,23,.4), 0 6px 14px -8px rgba(15,17,23,.2)",
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Encabezado */}
        <div className="flex items-center gap-2 px-4 h-12 shrink-0" style={{ borderBottom: `1px solid ${T.cardBorder}` }}>
          <Tag size={14} style={{ color: T.sub }} />
          <span className="text-sm font-medium flex-1 min-w-0 truncate" style={{ color: T.text }}>
            Tags · {nodeTitle || "Nodo"}
          </span>
          <PressableButton className="p-1 rounded-lg hover:opacity-70" style={{ color: T.sub }} onClick={onClose} title="Cerrar">
            <X size={15} />
          </PressableButton>
        </div>

        <div className="px-4 py-3 flex flex-col gap-3 overflow-y-auto">
          {/* Tags asignados */}
          <div className="flex flex-wrap gap-1.5">
            {tags.length === 0 ? (
              <span className="text-xs" style={{ color: T.sub }}>Sin tags todavía.</span>
            ) : (
              tags.map((t) => (
                <span key={t} className={chipBase} style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.text }}>
                  {t}
                  <PressableButton
                    className="rounded-full p-0.5 hover:opacity-70"
                    style={{ color: T.sub }}
                    onClick={() => removeTag(t)}
                    title={`Quitar "${t}"`}
                    data-testid={`tag-remove-${t}`}
                  >
                    <X size={11} />
                  </PressableButton>
                </span>
              ))
            )}
          </div>

          {/* Campo de texto */}
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Buscar o crear un tag…"
            className="w-full rounded-xl px-3 py-2 text-sm outline-none"
            style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.text }}
            data-testid="tags-input"
          />

          {/* Crear nuevo */}
          {canCreate && (
            <PressableButton
              className="flex items-center gap-1.5 self-start rounded-full text-xs px-2.5 py-1.5 hover:opacity-85"
              style={{ background: "rgba(196,132,122,.14)", border: "1px solid rgba(196,132,122,.4)", color: "#C4847A" }}
              onClick={() => addTag(q)}
              data-testid="tags-create"
            >
              <Plus size={12} /> Crear: “{q}”
            </PressableButton>
          )}

          {/* Sugerencias del tablero */}
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] uppercase tracking-wide" style={{ color: T.sub }}>Tags del tablero</span>
            {fetchState === "loading" ? (
              <span className="flex items-center gap-1.5 text-xs" style={{ color: T.sub }}>
                <Loader2 size={12} className="animate-spin" /> Cargando tags…
              </span>
            ) : (
              <>
                {fetchState === "error" && (
                  <span className="text-xs" style={{ color: "#F87171" }} data-testid="tags-error">
                    No se pudieron cargar los tags del tablero; se muestran los disponibles localmente.
                  </span>
                )}
                {suggestions.length === 0 ? (
                  <span className="text-xs" style={{ color: T.sub }}>
                    {q ? "Ningún tag existente coincide." : "No hay otros tags en el tablero."}
                  </span>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {suggestions.map((t) => (
                      <PressableButton
                        key={t}
                        className={suggBase}
                        style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.text }}
                        onClick={() => addTag(t)}
                        data-testid={`tag-suggest-${t}`}
                      >
                        {t}
                      </PressableButton>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
