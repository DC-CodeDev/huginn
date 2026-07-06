import { type Theme } from "../lib/theme";
import { FilterX, Filter } from "lucide-react";
import type { FilterMode } from "../lib/filter";

interface FilterPanelProps {
  T: Theme;
  allBoardTags: string[];
  filterTags: string[];
  filterMode: FilterMode;
  onChangeFilterTags: (tags: string[]) => void;
  onChangeFilterMode: (mode: FilterMode) => void;
  onClose: () => void;
}

export function FilterPanel({
  T,
  allBoardTags,
  filterTags,
  filterMode,
  onChangeFilterTags,
  onChangeFilterMode,
  onClose,
}: FilterPanelProps) {
  const toggleTag = (tag: string) => {
    const key = tag.toLowerCase();
    const exists = filterTags.some((t) => t.toLowerCase() === key);
    if (exists) {
      onChangeFilterTags(filterTags.filter((t) => t.toLowerCase() !== key));
    } else {
      onChangeFilterTags([...filterTags, tag]);
    }
  };

  return (
    <div
      className="absolute top-4 right-4 z-30 rounded-2xl w-56 flex flex-col overflow-hidden"
      style={{
        background: T.card,
        border: `1px solid ${T.cardBorder}`,
        boxShadow: "0 14px 34px -14px rgba(0,0,0,.6)",
      }}
    >
      {/* Encabezado */}
      <div
        className="flex items-center gap-2 px-3 h-10 shrink-0"
        style={{ borderBottom: `1px solid ${T.cardBorder}` }}
      >
        <Filter size={14} style={{ color: T.sub }} />
        <span className="text-xs font-medium flex-1" style={{ color: T.text }}>
          Filtrar por tags
        </span>
        <button
          className="p-1 rounded-lg hover:opacity-70"
          style={{ color: T.sub }}
          onClick={onClose}
          title="Cerrar filtro"
        >
          <FilterX size={14} />
        </button>
      </div>

      <div className="px-3 py-2 flex flex-col gap-2.5 max-h-80 overflow-y-auto">
        {/* Selector de modo */}
        <div
          className="flex rounded-lg overflow-hidden text-xs"
          style={{ background: T.field, border: `1px solid ${T.fieldBorder}` }}
        >
          <button
            className="flex-1 py-1.5 text-center font-medium transition-colors"
            style={{
              color: filterMode === "wide" ? T.text : T.sub,
              background: filterMode === "wide" ? "rgba(196,132,122,.14)" : "transparent",
            }}
            onClick={() => onChangeFilterMode("wide")}
          >
            Amplio
          </button>
          <button
            className="flex-1 py-1.5 text-center font-medium transition-colors"
            style={{
              color: filterMode === "strict" ? T.text : T.sub,
              background: filterMode === "strict" ? "rgba(196,132,122,.14)" : "transparent",
            }}
            onClick={() => onChangeFilterMode("strict")}
          >
            Estricto
          </button>
        </div>

        {/* Lista de tags */}
        {allBoardTags.length === 0 ? (
          <span className="text-xs" style={{ color: T.sub }}>
            No hay tags en el tablero.
          </span>
        ) : (
          <div className="flex flex-col gap-0.5">
            {allBoardTags.map((tag) => {
              const checked = filterTags.some((t) => t.toLowerCase() === tag.toLowerCase());
              return (
                <label
                  key={tag}
                  className="flex items-center gap-2 py-1 px-1 rounded-lg cursor-pointer hover:opacity-80 text-xs"
                  style={{ color: T.text }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleTag(tag)}
                    className="rounded accent-[#C4847A]"
                    style={{ accentColor: "#C4847A" }}
                  />
                  {tag}
                </label>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
