import { useState } from "react";
import { X } from "lucide-react";
import { PORT_COLORS } from "../types";
import type { Node, TimelineStage } from "../types";
import type { Theme } from "../lib/theme";
import { uid } from "../lib/id";

interface TimelineProps {
  node: Extract<Node, { type: "timeline" }>;
  T: Theme;
  update: (fn: (n: Node) => Node) => void;
}

export function Timeline({ node, T, update }: TimelineProps) {
  const [tagDrafts, setTagDrafts] = useState<Record<string, string>>({});
  const stageColor = (i: number) => PORT_COLORS[i % (PORT_COLORS.length - 1)];

  const setStage = (id: string, fn: (s: TimelineStage) => TimelineStage) =>
    update((n) => n.type === "timeline" ? { ...n, stages: n.stages.map((s) => s.id === id ? fn(s) : s) } : n);

  return (
    <div className="relative py-2">
      {/* línea central punteada */}
      <div className="absolute left-1/2 top-0 bottom-0 -translate-x-1/2 border-l border-dashed"
        style={{ borderColor: T.fieldBorder }} />
      <div className="flex flex-col gap-5">
        {node.stages.map((s, i) => {
          const left = i % 2 === 0;
          const color = stageColor(i);
          return (
            <div key={s.id} className="relative flex" style={{ justifyContent: left ? "flex-start" : "flex-end" }}>
              {/* hito */}
              <span className="absolute left-1/2 top-1 -translate-x-1/2 w-3 h-3 rounded-full z-10"
                style={{ background: T.card, border: `2px solid ${T.text}` }} />
              <div className={`w-[46%] group ${left ? "pr-2 text-right" : "pl-2 text-left"}`}>
                <div className="text-xs font-semibold" style={{ color }}>
                  {String(i + 1).padStart(2, "0")}
                </div>
                <input
                  value={s.title}
                  onChange={(e) => setStage(s.id, (x) => ({ ...x, title: e.target.value }))}
                  className={`bg-transparent outline-none text-sm font-medium w-full ${left ? "text-right" : ""}`}
                  style={{ color: T.text }}
                />
                <div className={`flex flex-wrap gap-1 mt-1.5 ${left ? "justify-end" : ""}`}>
                  {s.tags.map((t, ti) => (
                    <span key={ti}
                      className="group/tag inline-flex items-center gap-1 text-[10px] rounded-full px-2 py-0.5 cursor-default"
                      style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.sub }}
                    >
                      {t}
                      <button className="opacity-0 group-hover/tag:opacity-100" style={{ color: T.sub }}
                        onClick={() => setStage(s.id, (x) => ({ ...x, tags: x.tags.filter((_, j) => j !== ti) }))}>
                        <X size={9} />
                      </button>
                    </span>
                  ))}
                  <input
                    value={tagDrafts[s.id] || ""}
                    placeholder="+ tag"
                    onChange={(e) => setTagDrafts((d) => ({ ...d, [s.id]: e.target.value }))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (tagDrafts[s.id] || "").trim()) {
                        setStage(s.id, (x) => ({ ...x, tags: [...x.tags, tagDrafts[s.id].trim()] }));
                        setTagDrafts((d) => ({ ...d, [s.id]: "" }));
                      }
                    }}
                    className={`bg-transparent outline-none text-[10px] w-12 ${left ? "text-right" : ""}`}
                    style={{ color: T.sub }}
                  />
                </div>
                <button
                  className="mt-1 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity hover:opacity-100"
                  style={{ color: "#F87171" }}
                  onClick={() => update((n) => n.type === "timeline" ? { ...n, stages: n.stages.filter((x) => x.id !== s.id) } : n)}
                >
                  quitar etapa
                </button>
              </div>
            </div>
          );
        })}
      </div>
      <button
        className="mt-3 w-full text-[11px] rounded-lg py-1.5 hover:opacity-75"
        style={{ border: `1px dashed ${T.fieldBorder}`, color: T.sub }}
        onClick={() => update((n) => n.type === "timeline" ? { ...n, stages: [...n.stages, { id: uid(), title: `Etapa ${n.stages.length + 1}`, tags: [] }] } : n)}
      >
        + Añadir etapa
      </button>
    </div>
  );
}
