import type { MouseEvent as ReactMouseEvent } from "react";
import { Plus, Trash2, Type, Hash, Table2, Image as ImageIcon, Clock, CircleDot, Tag } from "lucide-react";
import { PORT_COLORS } from "../types";
import type { Node, Port } from "../types";
import type { Pending } from "../lib/canvas-types";
import { PORT_Y0, PORT_DY } from "../lib/geometry";
import type { Theme } from "../lib/theme";
import { uid } from "../lib/id";
import { MenuItem } from "./MenuItem";
import { Block } from "./Block";
import { Timeline } from "./Timeline";

interface NodeCardProps {
  node: Node;
  T: Theme;
  theme: string;
  selected: boolean;
  opacity: number;
  onSelect: (e: ReactMouseEvent) => void;
  onStartDrag: (e: ReactMouseEvent) => void;
  onDelete: () => void;
  update: (fn: (n: Node) => Node) => void;
  onPortClick: (port: Port) => void;
  onPortCycle: (portId: string) => void;
  onPortContext: (portId: string, e: ReactMouseEvent) => void;
  pending: Pending;
  menuOpen: boolean;
  onOpenMenu: () => void;
  onOpenTags: () => void;
}

export function NodeCard({ node, T, theme, selected, opacity, onSelect, onStartDrag, onDelete, update, onPortClick, onPortCycle, onPortContext, pending, menuOpen, onOpenMenu, onOpenTags }: NodeCardProps) {
  const leftPorts = node.ports.filter((p) => p.side === "left");
  const rightPorts = node.ports.filter((p) => p.side === "right");
  const maxPorts = Math.max(leftPorts.length, rightPorts.length);
  const portsZone = maxPorts > 0 ? 12 + maxPorts * PORT_DY : 4;

  const stopIfField = (e: ReactMouseEvent) => {
    if ((e.target as HTMLElement).closest("input,textarea,button,select,label")) return true;
    return false;
  };

  return (
    <div
      data-testid={`node-${node.id}`}
      data-selected={selected}
      data-node-x={node.x}
      data-node-y={node.y}
      className="absolute rounded-2xl"
      style={{
        left: node.x, top: node.y, width: node.w,
        opacity,
        background: T.card,
        border: `1px solid ${selected ? "#C4847A" : T.cardBorder}`,
        boxShadow: selected
          ? "0 0 0 1px rgba(196,132,122,.4), 0 0 28px -4px rgba(196,132,122,.4), 0 22px 44px -14px rgba(0,0,0,.65)"
          : theme === "dark"
            ? "0 22px 44px -16px rgba(0,0,0,.65), 0 4px 12px -6px rgba(0,0,0,.5)"
            : "0 18px 36px -18px rgba(15,17,23,.35), 0 4px 10px -6px rgba(15,17,23,.15)",
        transition: "box-shadow .15s, border-color .15s",
      }}
      onMouseDown={(e) => {
        e.stopPropagation();
        if (stopIfField(e)) { onSelect(e); return; }
        onStartDrag(e);
      }}
    >
      {/* Encabezado */}
      <div className="flex items-center gap-2 px-3 h-10 cursor-grab active:cursor-grabbing">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: T.text, opacity: 0.85 }} />
        <input
          value={node.title}
          onChange={(e) => update((n) => ({ ...n, title: e.target.value }))}
          className="bg-transparent outline-none text-sm font-medium flex-1 min-w-0"
          style={{ color: T.text }}
        />
        <button data-testid={`menu-${node.id}`} className="p-1 rounded-lg hover:opacity-70" style={{ color: T.sub }} onClick={(e) => { e.stopPropagation(); onOpenMenu(); }}>
          <Plus size={15} />
        </button>
        <button className="p-1 rounded-lg hover:opacity-70" style={{ color: T.sub }} onClick={(e) => { e.stopPropagation(); onDelete(); }}>
          <Trash2 size={14} />
        </button>
      </div>

      {/* Menú añadir */}
      {menuOpen && (
        <div
          className="absolute right-2 top-10 z-20 rounded-xl overflow-hidden text-xs w-44"
          style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, boxShadow: "0 14px 30px -12px rgba(0,0,0,.6)" }}
          onMouseDown={(e) => e.stopPropagation()}
        >
          <MenuItem T={T} icon={<Tag size={13} />} label="Tags" onClick={onOpenTags} />
          <div style={{ height: 1, background: T.fieldBorder }} />
          {node.type === "card" && (
            <>
              <MenuItem T={T} icon={<Type size={13} />} label="Bloque de texto"
                onClick={() => update((n) => n.type === "card" ? { ...n, blocks: [...n.blocks, { id: uid(), type: "text", value: "" }] } : n)} />
              <MenuItem T={T} icon={<Hash size={13} />} label="Dato numérico"
                onClick={() => update((n) => n.type === "card" ? { ...n, blocks: [...n.blocks, { id: uid(), type: "number", value: "0", label: "Etiqueta" }] } : n)} />
              <MenuItem T={T} icon={<Table2 size={13} />} label="Cuadro / tabla"
                onClick={() => update((n) => n.type === "card" ? { ...n, blocks: [...n.blocks, { id: uid(), type: "table", data: [["", ""], ["", ""]] }] } : n)} />
              <MenuItem T={T} icon={<ImageIcon size={13} />} label="Imagen"
                onClick={() => update((n) => n.type === "card" ? { ...n, blocks: [...n.blocks, { id: uid(), type: "image", src: null }] } : n)} />
              <div style={{ height: 1, background: T.fieldBorder }} />
            </>
          )}
          {node.type === "timeline" && (
            <MenuItem T={T} icon={<Clock size={13} />} label="Añadir etapa"
              onClick={() => update((n) => n.type === "timeline" ? { ...n, stages: [...n.stages, { id: uid(), title: `Etapa ${n.stages.length + 1}`, tags: [] }] } : n)} />
          )}
          <MenuItem T={T} icon={<CircleDot size={13} />} label="Puerto de entrada"
            onClick={() => update((n) => ({ ...n, ports: [...n.ports, { id: uid(), side: "left", color: PORT_COLORS[n.ports.length % PORT_COLORS.length], label: "in" }] }))} />
          <MenuItem T={T} icon={<CircleDot size={13} />} label="Puerto de salida"
            onClick={() => update((n) => ({ ...n, ports: [...n.ports, { id: uid(), side: "right", color: PORT_COLORS[n.ports.length % PORT_COLORS.length], label: "out" }] }))} />
        </div>
      )}

      {/* Zona de puertos: etiquetas */}
      {maxPorts > 0 && (
        <div className="relative" style={{ height: portsZone }}>
          {leftPorts.map((p, i) => (
            <input
              key={p.id}
              value={p.label}
              onChange={(e) => update((n) => ({ ...n, ports: n.ports.map((q) => q.id === p.id ? { ...q, label: e.target.value } : q) }))}
              className="absolute bg-transparent outline-none text-[11px] w-24"
              style={{ left: 16, top: PORT_Y0 - 48 + i * PORT_DY, color: T.sub }}
            />
          ))}
          {rightPorts.map((p, i) => (
            <input
              key={p.id}
              value={p.label}
              onChange={(e) => update((n) => ({ ...n, ports: n.ports.map((q) => q.id === p.id ? { ...q, label: e.target.value } : q) }))}
              className="absolute bg-transparent outline-none text-[11px] w-24 text-right"
              style={{ right: 16, top: PORT_Y0 - 48 + i * PORT_DY, color: T.sub }}
            />
          ))}
        </div>
      )}

      {/* Puntos de conexión (dots) */}
      {node.ports.map((p) => {
        const sameSide = node.ports.filter((q) => q.side === p.side);
        const i = sameSide.findIndex((q) => q.id === p.id);
        const isPendingSrc = pending && pending.portId === p.id;
        return (
          <div
            key={p.id}
            data-testid={`port-${node.id}-${p.id}`}
            title="Clic: conectar · Botón derecho: elegir color"
            className="absolute rounded-full cursor-crosshair z-10"
            style={{
              width: 12, height: 12,
              top: PORT_Y0 + i * PORT_DY - 6,
              [p.side === "left" ? "left" : "right"]: -6,
              background: p.color,
              border: `2px solid ${T.card}`,
              boxShadow: isPendingSrc ? `0 0 10px 2px ${p.color}` : `0 0 6px -1px ${p.color}`,
            }}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.stopPropagation(); onPortClick(p); }}
            onDoubleClick={(e) => { e.stopPropagation(); onPortCycle(p.id); }}
            onContextMenu={(e) => onPortContext(p.id, e)}
          />
        );
      })}

      {/* Contenido */}
      <div className="px-3 pb-3 flex flex-col gap-2" onMouseDown={(e) => e.stopPropagation()}>
        {node.type === "card" && node.blocks.map((b) => (
          <Block key={b.id} block={b} T={T}
            update={(fn) => update((n) => n.type === "card" ? { ...n, blocks: n.blocks.map((x) => x.id === b.id ? fn(x) : x) } : n)}
            remove={() => update((n) => n.type === "card" ? { ...n, blocks: n.blocks.filter((x) => x.id !== b.id) } : n)}
          />
        ))}
        {node.type === "timeline" && (
          <Timeline node={node} T={T} update={update} />
        )}
      </div>
    </div>
  );
}
