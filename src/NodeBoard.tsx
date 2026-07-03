import { useState, useRef, useEffect, useCallback } from "react";
import {
  Plus, Trash2, Moon, Sun, Spline, Minus, ZoomIn, ZoomOut, Maximize2, Clock,
} from "lucide-react";
import { useBoardPersistence } from "./api";
import { PORT_COLORS } from "./types";
import type { Node, Edge, Port } from "./types";
import type { Pending, DragState, Selection, ColorMenu } from "./lib/canvas-types";
import { portPos, edgePath } from "./lib/geometry";
import { THEMES } from "./lib/theme";
import { uid } from "./lib/id";
import { NodeCard } from "./components/NodeCard";
import { ToolBtn } from "./components/ToolBtn";
import { Sep } from "./components/Sep";

/* ------------------------------------------------------------------ */
/*  Constantes de geometría y tema                                     */
/* ------------------------------------------------------------------ */

const CARD_W = 280;
const TIMELINE_W = 360;

/* ------------------------------------------------------------------ */
/*  Datos iniciales (demo estilo referencia)                           */
/* ------------------------------------------------------------------ */

const initialNodes: Node[] = [
  {
    id: "n1", type: "card", x: 120, y: 260, w: CARD_W, title: "Model",
    tags: [],
    ports: [
      { id: "p1", side: "right", color: "#C4847A", label: "model" },
      { id: "p2", side: "right", color: "#4ADE80", label: "positive" },
      { id: "p3", side: "right", color: "#F87171", label: "negative" },
    ],
    blocks: [{ id: uid(), type: "text", value: "DreamShaper 6 (SD1.5)" }],
  },
  {
    id: "n2", type: "card", x: 560, y: 120, w: CARD_W, title: "Positive",
    tags: [],
    ports: [
      { id: "p4", side: "left", color: "#4ADE80", label: "in" },
      { id: "p5", side: "right", color: "#4ADE80", label: "out" },
    ],
    blocks: [{ id: uid(), type: "text", value: "A black bear with a pink snout, minimalist style, soft gradients, clear blue sky" }],
  },
  {
    id: "n3", type: "card", x: 560, y: 420, w: CARD_W, title: "Negative",
    tags: [],
    ports: [
      { id: "p6", side: "left", color: "#F87171", label: "in" },
      { id: "p7", side: "right", color: "#F87171", label: "out" },
    ],
    blocks: [{ id: uid(), type: "text", value: "No text, unnecessary details, background objects, other animals or people." }],
  },
  {
    id: "n4", type: "card", x: 990, y: 220, w: CARD_W, title: "Image Generator",
    tags: [],
    ports: [
      { id: "p8", side: "left", color: "#C4847A", label: "model" },
      { id: "p9", side: "left", color: "#4ADE80", label: "positive" },
      { id: "p10", side: "left", color: "#F87171", label: "negative" },
      { id: "p11", side: "right", color: "#60A5FA", label: "image" },
    ],
    blocks: [
      { id: uid(), type: "number", value: "12345", label: "Randomness" },
      { id: uid(), type: "number", value: "30", label: "Quality steps" },
      { id: uid(), type: "number", value: "8.0", label: "Prompt strength" },
    ],
  },
  {
    id: "n5", type: "timeline", x: 120, y: 640, w: TIMELINE_W, title: "Work Stages",
    tags: [],
    ports: [],
    stages: [
      { id: uid(), title: "Define", tags: ["Goals", "Roadmap", "Frameworks"] },
      { id: uid(), title: "Research", tags: ["Survey", "Interview", "CJM"] },
      { id: uid(), title: "Design", tags: ["Sketches", "Wireframes", "UI Kit"] },
      { id: uid(), title: "Testing", tags: ["Usability", "Split testing"] },
    ],
  },
];

const initialEdges: Edge[] = [
  { id: "e1", from: { nodeId: "n1", portId: "p2" }, to: { nodeId: "n2", portId: "p4" }, curved: true, label: "" },
  { id: "e2", from: { nodeId: "n1", portId: "p3" }, to: { nodeId: "n3", portId: "p6" }, curved: true, label: "" },
  { id: "e3", from: { nodeId: "n1", portId: "p1" }, to: { nodeId: "n4", portId: "p8" }, curved: true, label: "" },
  { id: "e4", from: { nodeId: "n2", portId: "p5" }, to: { nodeId: "n4", portId: "p9" }, curved: true, label: "" },
  { id: "e5", from: { nodeId: "n3", portId: "p7" }, to: { nodeId: "n4", portId: "p10" }, curved: true, label: "" },
];

/* ------------------------------------------------------------------ */
/*  Componente principal                                               */
/* ------------------------------------------------------------------ */

export default function NodeBoard() {
  const [theme, setTheme] = useState("dark");
  const T = THEMES[theme] || THEMES.dark;

  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges);
  const { status } = useBoardPersistence({ nodes, edges, setNodes, setEdges });
  const [selection, setSelection] = useState<Selection>(null); // {type:'node'|'edge', id}
  const [pending, setPending] = useState<Pending>(null);     // conexión en curso
  const [mouseWorld, setMouseWorld] = useState({ x: 0, y: 0 });
  const [menuNode, setMenuNode] = useState<string | null>(null);
  const [colorMenu, setColorMenu] = useState<ColorMenu>(null); // {nodeId, portId, x, y} en coords de pantalla
  const [defaultCurved, setDefaultCurved] = useState(true);

  const [view, setView] = useState({ x: 40, y: 20, z: 1 });
  const viewRef = useRef(view);
  viewRef.current = view;

  const canvasRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState>(null);

  const toWorld = useCallback((sx: number, sy: number) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const v = viewRef.current;
    return { x: (sx - rect.left - v.x) / v.z, y: (sy - rect.top - v.y) / v.z };
  }, []);

  /* ---------------- Zoom con rueda (listener nativo, no pasivo) ---- */
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setView((v) => {
        const nz = Math.min(2.5, Math.max(0.25, v.z * (e.deltaY < 0 ? 1.1 : 0.9)));
        const k = nz / v.z;
        return { x: mx - (mx - v.x) * k, y: my - (my - v.y) * k, z: nz };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  /* ---------------- Drag global (pan y nodos) ---------------------- */
  useEffect(() => {
    const move = (e: MouseEvent) => {
      setMouseWorld(toWorld(e.clientX, e.clientY));
      const d = dragRef.current;
      if (!d) return;
      if (d.kind === "pan") {
        setView((v) => ({ ...v, x: d.vx + (e.clientX - d.sx), y: d.vy + (e.clientY - d.sy) }));
      } else if (d.kind === "node") {
        const w = toWorld(e.clientX, e.clientY);
        setNodes((ns) => ns.map((n) => (n.id === d.id ? { ...n, x: w.x - d.ox, y: w.y - d.oy } : n)));
      }
    };
    const up = () => { dragRef.current = null; };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [toWorld]);

  /* ---------------- Teclado: suprimir ------------------------------ */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if ((e.key === "Delete" || e.key === "Backspace") && selection) {
        e.preventDefault();
        deleteSelection();
      }
      if (e.key === "Escape") { setPending(null); setSelection(null); setMenuNode(null); setColorMenu(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  /* ---------------- Mutadores --------------------------------------- */
  const updateNode = (id: string, fn: (n: Node) => Node) => setNodes((ns) => ns.map((n) => (n.id === id ? fn(n) : n)));

  const deleteSelection = () => {
    if (!selection) return;
    if (selection.type === "node") {
      setNodes((ns) => ns.filter((n) => n.id !== selection.id));
      setEdges((es) => es.filter((e) => e.from.nodeId !== selection.id && e.to.nodeId !== selection.id));
    } else {
      setEdges((es) => es.filter((e) => e.id !== selection.id));
    }
    setSelection(null);
  };

  const addNode = (type: "card" | "timeline", at?: { x: number; y: number }) => {
    const pos = at || toWorld(
      canvasRef.current!.getBoundingClientRect().left + 320,
      canvasRef.current!.getBoundingClientRect().top + 200
    );
    const base = { id: uid(), x: pos.x, y: pos.y, title: type === "timeline" ? "Línea temporal" : "Nuevo nodo", tags: [] as string[] };
    if (type === "timeline") {
      setNodes((ns) => [...ns, { ...base, type: "timeline", w: TIMELINE_W, ports: [], stages: [
        { id: uid(), title: "Etapa 1", tags: ["Tag"] },
      ] }]);
    } else {
      setNodes((ns) => [...ns, { ...base, type: "card", w: CARD_W,
        ports: [
          { id: uid(), side: "left", color: "#E8EBF0", label: "in" },
          { id: uid(), side: "right", color: "#4ADE80", label: "out" },
        ],
        blocks: [{ id: uid(), type: "text", value: "" }] }]);
    }
  };

  const onPortClick = (node: Node, port: Port) => {
    if (pending) {
      if (pending.nodeId === node.id && pending.portId === port.id) { setPending(null); return; }
      setEdges((es) => [...es, {
        id: uid(),
        from: { nodeId: pending.nodeId, portId: pending.portId },
        to: { nodeId: node.id, portId: port.id },
        curved: defaultCurved,
        label: "",
      }]);
      setPending(null);
    } else {
      setPending({ nodeId: node.id, portId: port.id, color: port.color });
    }
  };

  const cyclePortColor = (nodeId: string, portId: string) => {
    updateNode(nodeId, (n) => ({
      ...n,
      ports: n.ports.map((p) => p.id === portId
        ? { ...p, color: PORT_COLORS[(PORT_COLORS.indexOf(p.color) + 1) % PORT_COLORS.length] }
        : p),
    }));
  };

  /* ---------------- Render de aristas ------------------------------- */
  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const renderedEdges = edges.map((e) => {
    const a = nodeById[e.from.nodeId] && portPos(nodeById[e.from.nodeId], e.from.portId);
    const b = nodeById[e.to.nodeId] && portPos(nodeById[e.to.nodeId], e.to.portId);
    if (!a || !b) return null;
    return { ...e, a, b, color: a.color };
  }).filter((e): e is NonNullable<typeof e> => e !== null);

  const pendingPos = pending && nodeById[pending.nodeId] ? portPos(nodeById[pending.nodeId], pending.portId) : null;

  const selectedEdge = selection?.type === "edge" ? edges.find((e) => e.id === selection.id) : null;

  /* ================================================================== */
  return (
    <div
      ref={canvasRef}
      className="relative w-full h-screen overflow-hidden select-none"
      style={{
        background: T.bg,
        backgroundImage: `radial-gradient(${T.dot} 1.6px, transparent 1.6px)`,
        backgroundSize: `${26 * view.z}px ${26 * view.z}px`,
        backgroundPosition: `${view.x}px ${view.y}px`,
        color: T.text,
        fontFamily: "'Inter','Segoe UI',system-ui,sans-serif",
        cursor: dragRef.current?.kind === "pan" ? "grabbing" : "default",
      }}
      onMouseDown={(e) => {
        if (e.target === canvasRef.current) {
          dragRef.current = { kind: "pan", sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
          setSelection(null); setMenuNode(null); setPending(null); setColorMenu(null);
        }
      }}
      onDoubleClick={(e) => {
        if (e.target === canvasRef.current) addNode("card", toWorld(e.clientX, e.clientY));
      }}
    >
      {/* ---------- Capa transformada (mundo) ---------- */}
      <div
        className="absolute top-0 left-0"
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})`, transformOrigin: "0 0" }}
      >
        {/* Aristas */}
        <svg className="absolute top-0 left-0 overflow-visible pointer-events-none" width="1" height="1">
          {renderedEdges.map((e) => (
            <g key={e.id}>
              <path
                d={edgePath(e.a, e.b, e.curved)}
                stroke="transparent" strokeWidth={14} fill="none"
                className="pointer-events-auto cursor-pointer"
                onClick={(ev) => { ev.stopPropagation(); setSelection({ type: "edge", id: e.id }); }}
              />
              <path
                d={edgePath(e.a, e.b, e.curved)}
                stroke={e.color} fill="none"
                strokeWidth={selection?.type === "edge" && selection.id === e.id ? 2.6 : 1.6}
                opacity={selection?.type === "edge" && selection.id === e.id ? 1 : 0.75}
                style={selection?.type === "edge" && selection.id === e.id
                  ? { filter: `drop-shadow(0 0 6px ${e.color})` } : undefined}
              />
            </g>
          ))}
          {pendingPos && (
            <path
              d={edgePath(pendingPos, { ...mouseWorld, side: "left" }, defaultCurved)}
              stroke={pendingPos.color} strokeWidth={1.6} strokeDasharray="6 6" fill="none" opacity={0.9}
            />
          )}
        </svg>

        {/* Nodos */}
        {nodes.map((node) => (
          <NodeCard
            key={node.id}
            node={node} T={T} theme={theme}
            selected={selection?.type === "node" && selection.id === node.id}
            menuOpen={menuNode === node.id}
            onOpenMenu={() => setMenuNode(menuNode === node.id ? null : node.id)}
            onSelect={() => { setSelection({ type: "node", id: node.id }); setMenuNode(null); }}
            onStartDrag={(e) => {
              const w = toWorld(e.clientX, e.clientY);
              dragRef.current = { kind: "node", id: node.id, ox: w.x - node.x, oy: w.y - node.y };
              setSelection({ type: "node", id: node.id });
            }}
            onDelete={() => { setSelection({ type: "node", id: node.id }); setNodes((ns) => ns.filter((n) => n.id !== node.id)); setEdges((es) => es.filter((e2) => e2.from.nodeId !== node.id && e2.to.nodeId !== node.id)); setSelection(null); }}
            update={(fn) => updateNode(node.id, fn)}
            onPortClick={(port) => onPortClick(node, port)}
            onPortCycle={(portId) => cyclePortColor(node.id, portId)}
            onPortContext={(portId, e) => {
              e.preventDefault(); e.stopPropagation();
              const rect = canvasRef.current!.getBoundingClientRect();
              setColorMenu({ nodeId: node.id, portId, x: e.clientX - rect.left, y: e.clientY - rect.top });
            }}
            pending={pending}
          />
        ))}
      </div>

      {/* ---------- Menú contextual de colores ---------- */}
      {colorMenu && (
        <div
          className="absolute z-30 flex items-center gap-2 rounded-full px-3 py-2"
          style={{
            left: colorMenu.x, top: colorMenu.y,
            transform: "translate(-50%, calc(-100% - 10px))",
            background: T.card,
            border: `1px solid ${T.cardBorder}`,
            boxShadow: theme === "dark"
              ? "0 18px 36px -12px rgba(0,0,0,.7), 0 4px 12px -6px rgba(0,0,0,.5)"
              : "0 16px 32px -14px rgba(15,17,23,.35), 0 4px 10px -6px rgba(15,17,23,.15)",
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onContextMenu={(e) => e.preventDefault()}
        >
          {PORT_COLORS.map((c) => {
            const current = nodeById[colorMenu.nodeId]?.ports.find((p) => p.id === colorMenu.portId)?.color === c;
            return (
              <button
                key={c}
                className="rounded-full transition-transform hover:scale-125"
                style={{
                  width: 14, height: 14, background: c,
                  border: current ? `2px solid ${T.text}` : `2px solid ${T.card}`,
                  boxShadow: `0 0 6px -1px ${c}`,
                }}
                title={c}
                onClick={() => {
                  updateNode(colorMenu.nodeId, (n) => ({
                    ...n,
                    ports: n.ports.map((p) => p.id === colorMenu.portId ? { ...p, color: c } : p),
                  }));
                  setColorMenu(null);
                }}
              />
            );
          })}
        </div>
      )}

      {/* ---------- Barra de herramientas ---------- */}
      <div
        className="absolute top-4 left-4 flex items-center gap-1 rounded-2xl px-2 py-1.5"
        style={{ background: T.card, border: `1px solid ${T.cardBorder}`, boxShadow: "0 14px 34px -14px rgba(0,0,0,.6)" }}
      >
        <ToolBtn T={T} testId="add-node-card" label="Nuevo nodo" onClick={() => addNode("card")}><Plus size={16} /></ToolBtn>
        <ToolBtn T={T} testId="add-node-timeline" label="Línea temporal" onClick={() => addNode("timeline")}><Clock size={16} /></ToolBtn>
        <Sep T={T} />
        <span
          data-testid="save-status"
          className="px-2 text-[11px]"
          style={{ color: status === "error" ? "#F87171" : T.sub }}
          title={status === "error" ? "No se pudo conectar con la API" : "Estado de persistencia"}
        >
          {status}
        </span>
        <Sep T={T} />
        <ToolBtn T={T} label={defaultCurved ? "Conector: curvo" : "Conector: recto"} onClick={() => setDefaultCurved((c) => !c)}>
          {defaultCurved ? <Spline size={16} /> : <Minus size={16} />}
        </ToolBtn>
        <ToolBtn T={T} label="Tema" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </ToolBtn>
        <Sep T={T} />
        <ToolBtn T={T} label="Alejar" onClick={() => setView((v) => ({ ...v, z: Math.max(0.25, v.z * 0.9) }))}><ZoomOut size={16} /></ToolBtn>
        <span className="text-xs w-10 text-center" style={{ color: T.sub }}>{Math.round(view.z * 100)}%</span>
        <ToolBtn T={T} label="Acercar" onClick={() => setView((v) => ({ ...v, z: Math.min(2.5, v.z * 1.1) }))}><ZoomIn size={16} /></ToolBtn>
        <ToolBtn T={T} label="Restablecer vista" onClick={() => setView({ x: 40, y: 20, z: 1 })}><Maximize2 size={16} /></ToolBtn>
      </div>

      {/* ---------- Barra de acciones de selección ---------- */}
      {selection && (
        <div
          className="absolute bottom-5 left-1/2 -translate-x-1/2 flex items-center gap-1 rounded-2xl px-2 py-1.5"
          style={{ background: T.card, border: `1px solid ${T.cardBorder}`, boxShadow: "0 14px 34px -14px rgba(0,0,0,.6)" }}
        >
          {selectedEdge && (
            <button
              className="flex items-center gap-1.5 text-xs rounded-xl px-3 py-1.5 hover:opacity-80"
              style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.text }}
              onClick={() => setEdges((es) => es.map((e) => e.id === selectedEdge.id ? { ...e, curved: !e.curved } : e))}
            >
              {selectedEdge.curved ? <Minus size={14} /> : <Spline size={14} />}
              {selectedEdge.curved ? "Hacer recto" : "Hacer curvo"}
            </button>
          )}
          <button
            className="flex items-center gap-1.5 text-xs rounded-xl px-3 py-1.5 hover:opacity-80"
            style={{ background: "rgba(248,113,113,.12)", border: "1px solid rgba(248,113,113,.35)", color: "#F87171" }}
            onClick={deleteSelection}
          >
            <Trash2 size={14} /> Eliminar
          </button>
        </div>
      )}

      {/* ---------- Ayuda ---------- */}
      <div className="absolute bottom-4 left-4 text-[11px] leading-relaxed max-w-xs" style={{ color: T.sub }}>
        Doble clic en el lienzo: nuevo nodo · Clic en un punto de color: iniciar/terminar conexión ·
        Botón derecho en un punto: elegir color · Rueda: zoom · Arrastrar fondo: mover lienzo
      </div>
    </div>
  );
}
