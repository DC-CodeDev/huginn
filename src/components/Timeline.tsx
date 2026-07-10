import { useState } from "react";
import { X } from "lucide-react";
import { PORT_COLORS } from "../types";
import type { Node, TimelineStage } from "../types";
import type { Theme } from "../lib/theme";
import { uid } from "../lib/id";
import { PressableButton } from "./PressableButton";

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

  const currentY = node.orientation === "vertical";
  const currentH = node.orientation === "horizontal";

  // ---------- Overlay de elección de orientación ----------
  if (!node.orientation) {
    return (
      <div className="relative py-6 px-3 flex flex-col items-center gap-4 pointer-events-auto">
        <div className="text-xs font-medium" style={{ color: T.sub }}>
          Elegir orientación del timeline
        </div>
        <div className="flex gap-3 w-full">
          <button
            data-testid={`orient-vertical-${node.id}`}
            className="flex-1 rounded-xl py-3 text-sm font-semibold transition-all hover:scale-[1.02] active:scale-[0.98]"
            style={{
              background: T.field,
              border: `1px solid ${T.fieldBorder}`,
              color: T.text,
            }}
            onClick={(e) => { e.stopPropagation(); update((n) => n.type === "timeline" ? { ...n, orientation: "vertical" } : n); }}
          >
            Vertical
          </button>
          <button
            data-testid={`orient-horizontal-${node.id}`}
            className="flex-1 rounded-xl py-3 text-sm font-semibold transition-all hover:scale-[1.02] active:scale-[0.98]"
            style={{
              background: T.field,
              border: `1px solid ${T.fieldBorder}`,
              color: T.text,
            }}
            onClick={(e) => { e.stopPropagation(); update((n) => n.type === "timeline" ? { ...n, orientation: "horizontal" } : n); }}
          >
            Horizontal
          </button>
        </div>
      </div>
    );
  }

  // ---------- Layout vertical (existente) ----------
  if (currentY) {
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
                        <PressableButton className="opacity-0 group-hover/tag:opacity-100" style={{ color: T.sub }}
                          onClick={() => setStage(s.id, (x) => ({ ...x, tags: x.tags.filter((_, j) => j !== ti) }))}>
                          <X size={9} />
                        </PressableButton>
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
                  <PressableButton
                    className="mt-1 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity hover:opacity-100"
                    style={{ color: "#F87171" }}
                    onClick={() => update((n) => n.type === "timeline" ? { ...n, stages: n.stages.filter((x) => x.id !== s.id) } : n)}
                  >
                    quitar etapa
                  </PressableButton>
                </div>
              </div>
            );
          })}
        </div>
        <PressableButton
          className="mt-3 w-full text-[11px] rounded-lg py-1.5 hover:opacity-75"
          style={{ border: `1px dashed ${T.fieldBorder}`, color: T.sub }}
          onClick={() => update((n) => n.type === "timeline" ? { ...n, stages: [...n.stages, { id: uid(), title: `Etapa ${n.stages.length + 1}`, tags: [] }] } : n)}
        >
          + Añadir etapa
        </PressableButton>
      </div>
    );
  }

  // ---------- Layout horizontal ----------
  if (currentH) {
    return (
      <div className="relative py-2 overflow-x-auto">
        {/* línea horizontal punteada */}
        <div className="absolute left-0 top-[22px] right-0 border-t border-dashed"
          style={{ borderColor: T.fieldBorder }} />
        <div className="flex gap-4 min-w-min px-1 pb-1 relative">
          {node.stages.map((s, i) => {
            const color = stageColor(i);
            return (
              <div key={s.id} className="flex flex-col items-center min-w-0 shrink-0" style={{ width: 140 }}>
                {/* hito */}
                <span className="w-3 h-3 rounded-full mb-2 z-10"
                  style={{ background: T.card, border: `2px solid ${T.text}` }} />
                {/* contenido de la etapa */}
                <div className="w-full rounded-xl px-2.5 py-2 group"
                  style={{ background: T.field, border: `1px solid ${T.fieldBorder}` }}>
                  <div className="text-[10px] font-semibold mb-1" style={{ color }}>
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <input
                    value={s.title}
                    onChange={(e) => setStage(s.id, (x) => ({ ...x, title: e.target.value }))}
                    className="bg-transparent outline-none text-xs font-medium w-full"
                    style={{ color: T.text }}
                  />
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {s.tags.map((t, ti) => (
                      <span key={ti}
                        className="group/tag inline-flex items-center gap-1 text-[9px] rounded-full px-1.5 py-0.5 cursor-default"
                        style={{ background: T.card, border: `1px solid ${T.fieldBorder}`, color: T.sub }}
                      >
                        {t}
                        <PressableButton className="opacity-0 group-hover/tag:opacity-100" style={{ color: T.sub }}
                          onClick={() => setStage(s.id, (x) => ({ ...x, tags: x.tags.filter((_, j) => j !== ti) }))}>
                          <X size={8} />
                        </PressableButton>
                      </span>
                    ))}
                    <input
                      value={tagDrafts[s.id] || ""}
                      placeholder="+tag"
                      onChange={(e) => setTagDrafts((d) => ({ ...d, [s.id]: e.target.value }))}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (tagDrafts[s.id] || "").trim()) {
                          setStage(s.id, (x) => ({ ...x, tags: [...x.tags, tagDrafts[s.id].trim()] }));
                          setTagDrafts((d) => ({ ...d, [s.id]: "" }));
                        }
                      }}
                      className="bg-transparent outline-none text-[9px] w-10"
                      style={{ color: T.sub }}
                    />
                  </div>
                  <PressableButton
                    className="mt-1 text-[9px] opacity-0 group-hover:opacity-100 transition-opacity hover:opacity-100"
                    style={{ color: "#F87171" }}
                    onClick={() => update((n) => n.type === "timeline" ? { ...n, stages: n.stages.filter((x) => x.id !== s.id) } : n)}
                  >
                    quitar
                  </PressableButton>
                </div>
              </div>
            );
          })}
          {/* botón añadir etapa */}
          <div className="flex flex-col items-center shrink-0 self-start" style={{ width: 140 }}>
            <span className="w-3 h-3 rounded-full mb-2 z-10"
              style={{ background: T.card, border: `2px solid ${T.fieldBorder}` }} />
            <PressableButton
              className="w-full text-[10px] rounded-xl py-2 hover:opacity-75"
              style={{ border: `1px dashed ${T.fieldBorder}`, color: T.sub }}
              onClick={() => update((n) => n.type === "timeline" ? { ...n, stages: [...n.stages, { id: uid(), title: `Etapa ${n.stages.length + 1}`, tags: [] }] } : n)}
            >
              + Añadir etapa
            </PressableButton>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
