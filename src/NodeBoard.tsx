// @ts-nocheck
import { useState, useRef, useEffect, useCallback } from "react";
import {
  Plus, Trash2, Type, Hash, Table2, Image as ImageIcon, Moon, Sun,
  Spline, Minus, ZoomIn, ZoomOut, Maximize2, Clock, CircleDot, X,
} from "lucide-react";
import { useBoardPersistence } from "./api";

/* ------------------------------------------------------------------ */
/*  Constantes de geometría y tema                                     */
/* ------------------------------------------------------------------ */

const CARD_W = 280;
const TIMELINE_W = 360;
const PORT_Y0 = 56;   // y del primer puerto (relativo al nodo)
const PORT_DY = 26;   // separación vertical entre puertos

const PORT_COLORS = ["#C4847A", "#4ADE80", "#F87171", "#60A5FA", "#C084FC", "#E8EBF0"];

const THEMES = {
  dark: {
    bg: "#0F1117",
    dot: "#0A0C10",          // dots levemente más oscuros que el fondo
    card: "#161923",
    cardBorder: "#242938",
    field: "#0C0E14",
    fieldBorder: "#1E2230",
    text: "#E8EBF0",
    sub: "#8A90A3",
  },
  light: {
    bg: "#E8EBF0",
    dot: "#DCE0E9",
    card: "#FFFFFF",
    cardBorder: "#D6DBE6",
    field: "#EEF0F6",
    fieldBorder: "#DCE0EA",
    text: "#0F1117",
    sub: "#5B6172",
  },
};

let _id = 100;
const uid = () => `id_${_id++}_${Math.random().toString(36).slice(2, 6)}`;

/* ------------------------------------------------------------------ */
/*  Datos iniciales (demo estilo referencia)                           */
/* ------------------------------------------------------------------ */

const initialNodes = [
  {
    id: "n1", type: "card", x: 120, y: 260, w: CARD_W, title: "Model",
    ports: [
      { id: "p1", side: "right", color: "#C4847A", label: "model" },
      { id: "p2", side: "right", color: "#4ADE80", label: "positive" },
      { id: "p3", side: "right", color: "#F87171", label: "negative" },
    ],
    blocks: [{ id: uid(), type: "text", value: "DreamShaper 6 (SD1.5)" }],
  },
  {
    id: "n2", type: "card", x: 560, y: 120, w: CARD_W, title: "Positive",
    ports: [
      { id: "p4", side: "left", color: "#4ADE80", label: "in" },
      { id: "p5", side: "right", color: "#4ADE80", label: "out" },
    ],
    blocks: [{ id: uid(), type: "text", value: "A black bear with a pink snout, minimalist style, soft gradients, clear blue sky" }],
  },
  {
    id: "n3", type: "card", x: 560, y: 420, w: CARD_W, title: "Negative",
    ports: [
      { id: "p6", side: "left", color: "#F87171", label: "in" },
      { id: "p7", side: "right", color: "#F87171", label: "out" },
    ],
    blocks: [{ id: uid(), type: "text", value: "No text, unnecessary details, background objects, other animals or people." }],
  },
  {
    id: "n4", type: "card", x: 990, y: 220, w: CARD_W, title: "Image Generator",
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
    ports: [],
    stages: [
      { id: uid(), title: "Define", tags: ["Goals", "Roadmap", "Frameworks"] },
      { id: uid(), title: "Research", tags: ["Survey", "Interview", "CJM"] },
      { id: uid(), title: "Design", tags: ["Sketches", "Wireframes", "UI Kit"] },
      { id: uid(), title: "Testing", tags: ["Usability", "Split testing"] },
    ],
  },
];

const initialEdges = [
  { id: "e1", from: { nodeId: "n1", portId: "p2" }, to: { nodeId: "n2", portId: "p4" }, curved: true },
  { id: "e2", from: { nodeId: "n1", portId: "p3" }, to: { nodeId: "n3", portId: "p6" }, curved: true },
  { id: "e3", from: { nodeId: "n1", portId: "p1" }, to: { nodeId: "n4", portId: "p8" }, curved: true },
  { id: "e4", from: { nodeId: "n2", portId: "p5" }, to: { nodeId: "n4", portId: "p9" }, curved: true },
  { id: "e5", from: { nodeId: "n3", portId: "p7" }, to: { nodeId: "n4", portId: "p10" }, curved: true },
];

/* ------------------------------------------------------------------ */
/*  Utilidades de geometría                                            */
/* ------------------------------------------------------------------ */

function portPos(node, portId) {
  const port = node.ports.find((p) => p.id === portId);
  if (!port) return null;
  const samesSide = node.ports.filter((p) => p.side === port.side);
  const idx = samesSide.findIndex((p) => p.id === portId);
  return {
    x: port.side === "left" ? node.x : node.x + node.w,
    y: node.y + PORT_Y0 + idx * PORT_DY,
    side: port.side,
    color: port.color,
  };
}

function edgePath(a, b, curved) {
  if (!curved) return `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
  const dx = Math.max(60, Math.abs(b.x - a.x) / 2);
  const c1x = a.side === "left" ? a.x - dx : a.x + dx;
  const c2x = b.side === "right" ? b.x + dx : b.x - dx;
  return `M ${a.x} ${a.y} C ${c1x} ${a.y}, ${c2x} ${b.y}, ${b.x} ${b.y}`;
}

/* ------------------------------------------------------------------ */
/*  Componente principal                                               */
/* ------------------------------------------------------------------ */

export default function NodeBoard() {
  const [theme, setTheme] = useState("dark");
  const T = THEMES[theme] || THEMES.dark;

  const [nodes, setNodes] = useState(initialNodes);
  const [edges, setEdges] = useState(initialEdges);
  const { status } = useBoardPersistence({ nodes, edges, setNodes, setEdges });
  const [selection, setSelection] = useState(null); // {type:'node'|'edge', id}
  const [pending, setPending] = useState(null);     // conexión en curso
  const [mouseWorld, setMouseWorld] = useState({ x: 0, y: 0 });
  const [menuNode, setMenuNode] = useState(null);
  const [colorMenu, setColorMenu] = useState(null); // {nodeId, portId, x, y} en coords de pantalla
  const [defaultCurved, setDefaultCurved] = useState(true);

  const [view, setView] = useState({ x: 40, y: 20, z: 1 });
  const viewRef = useRef(view);
  viewRef.current = view;

  const canvasRef = useRef(null);
  const dragRef = useRef(null);

  const toWorld = useCallback((sx, sy) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const v = viewRef.current;
    return { x: (sx - rect.left - v.x) / v.z, y: (sy - rect.top - v.y) / v.z };
  }, []);

  /* ---------------- Zoom con rueda (listener nativo, no pasivo) ---- */
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const onWheel = (e) => {
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
    const move = (e) => {
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
    const onKey = (e) => {
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
  const updateNode = (id, fn) => setNodes((ns) => ns.map((n) => (n.id === id ? fn(n) : n)));

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

  const addNode = (type, at) => {
    const pos = at || toWorld(
      canvasRef.current.getBoundingClientRect().left + 320,
      canvasRef.current.getBoundingClientRect().top + 200
    );
    const base = { id: uid(), x: pos.x, y: pos.y, title: type === "timeline" ? "Línea temporal" : "Nuevo nodo" };
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

  const onPortClick = (node, port) => {
    if (pending) {
      if (pending.nodeId === node.id && pending.portId === port.id) { setPending(null); return; }
      setEdges((es) => [...es, {
        id: uid(),
        from: { nodeId: pending.nodeId, portId: pending.portId },
        to: { nodeId: node.id, portId: port.id },
        curved: defaultCurved,
      }]);
      setPending(null);
    } else {
      setPending({ nodeId: node.id, portId: port.id, color: port.color });
    }
  };

  const cyclePortColor = (nodeId, portId) => {
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
  }).filter(Boolean);

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
              const rect = canvasRef.current.getBoundingClientRect();
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
        <ToolBtn T={T} label="Nuevo nodo" onClick={() => addNode("card")}><Plus size={16} /></ToolBtn>
        <ToolBtn T={T} label="Línea temporal" onClick={() => addNode("timeline")}><Clock size={16} /></ToolBtn>
        <Sep T={T} />
        <span
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

/* ------------------------------------------------------------------ */
/*  Nodo (tarjeta o línea temporal)                                    */
/* ------------------------------------------------------------------ */

function NodeCard({ node, T, theme, selected, onSelect, onStartDrag, onDelete, update, onPortClick, onPortCycle, onPortContext, pending, menuOpen, onOpenMenu }) {
  const leftPorts = node.ports.filter((p) => p.side === "left");
  const rightPorts = node.ports.filter((p) => p.side === "right");
  const maxPorts = Math.max(leftPorts.length, rightPorts.length);
  const portsZone = maxPorts > 0 ? 12 + maxPorts * PORT_DY : 4;

  const stopIfField = (e) => {
    if (e.target.closest("input,textarea,button,select,label")) return true;
    return false;
  };

  return (
    <div
      className="absolute rounded-2xl"
      style={{
        left: node.x, top: node.y, width: node.w,
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
        if (stopIfField(e)) { onSelect(); return; }
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
        <button className="p-1 rounded-lg hover:opacity-70" style={{ color: T.sub }} onClick={(e) => { e.stopPropagation(); onOpenMenu(); }}>
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
          {node.type === "card" && (
            <>
              <MenuItem T={T} icon={<Type size={13} />} label="Bloque de texto"
                onClick={() => update((n) => ({ ...n, blocks: [...n.blocks, { id: uid(), type: "text", value: "" }] }))} />
              <MenuItem T={T} icon={<Hash size={13} />} label="Dato numérico"
                onClick={() => update((n) => ({ ...n, blocks: [...n.blocks, { id: uid(), type: "number", value: "0", label: "Etiqueta" }] }))} />
              <MenuItem T={T} icon={<Table2 size={13} />} label="Cuadro / tabla"
                onClick={() => update((n) => ({ ...n, blocks: [...n.blocks, { id: uid(), type: "table", data: [["", ""], ["", ""]] }] }))} />
              <MenuItem T={T} icon={<ImageIcon size={13} />} label="Imagen"
                onClick={() => update((n) => ({ ...n, blocks: [...n.blocks, { id: uid(), type: "image", src: null }] }))} />
              <div style={{ height: 1, background: T.fieldBorder }} />
            </>
          )}
          {node.type === "timeline" && (
            <MenuItem T={T} icon={<Clock size={13} />} label="Añadir etapa"
              onClick={() => update((n) => ({ ...n, stages: [...n.stages, { id: uid(), title: `Etapa ${n.stages.length + 1}`, tags: [] }] }))} />
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
            update={(fn) => update((n) => ({ ...n, blocks: n.blocks.map((x) => x.id === b.id ? fn(x) : x) }))}
            remove={() => update((n) => ({ ...n, blocks: n.blocks.filter((x) => x.id !== b.id) }))}
          />
        ))}
        {node.type === "timeline" && (
          <Timeline node={node} T={T} update={update} />
        )}
      </div>
    </div>
  );
}

function MenuItem({ T, icon, label, onClick }) {
  return (
    <button
      className="flex items-center gap-2 w-full px-3 py-2 text-left hover:opacity-75"
      style={{ color: T.text }}
      onClick={onClick}
    >
      <span style={{ color: T.sub }}>{icon}</span>{label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Bloques de contenido                                               */
/* ------------------------------------------------------------------ */

function Block({ block, T, update, remove }) {
  const fileRef = useRef(null);

  const wrap = (children) => (
    <div className="relative group rounded-xl" style={{ background: T.field, border: `1px solid ${T.fieldBorder}` }}>
      <button
        className="absolute -top-2 -right-2 z-10 rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ background: T.card, border: `1px solid ${T.fieldBorder}`, color: T.sub }}
        onClick={remove} title="Quitar bloque"
      >
        <X size={11} />
      </button>
      {children}
    </div>
  );

  if (block.type === "text") {
    return wrap(
      <textarea
        value={block.value}
        placeholder="Escribí acá…"
        onChange={(e) => {
          update((b) => ({ ...b, value: e.target.value }));
          e.target.style.height = "auto";
          e.target.style.height = e.target.scrollHeight + "px";
        }}
        ref={(el) => { if (el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; } }}
        className="w-full bg-transparent outline-none resize-none text-xs leading-relaxed px-3 py-2.5"
        style={{ color: T.text, minHeight: 38 }}
      />
    );
  }

  if (block.type === "number") {
    return wrap(
      <div className="px-3 py-2.5">
        <input
          value={block.value}
          onChange={(e) => update((b) => ({ ...b, value: e.target.value }))}
          className="w-full bg-transparent outline-none text-xl font-semibold tracking-tight"
          style={{ color: T.text }}
        />
        <input
          value={block.label}
          onChange={(e) => update((b) => ({ ...b, label: e.target.value }))}
          className="w-full bg-transparent outline-none text-[11px] mt-0.5"
          style={{ color: T.sub }}
        />
      </div>
    );
  }

  if (block.type === "table") {
    const data = block.data;
    const setCell = (r, c, v) => update((b) => {
      const d = b.data.map((row) => [...row]); d[r][c] = v; return { ...b, data: d };
    });
    return wrap(
      <div className="p-2">
        <div className="grid gap-px rounded-lg overflow-hidden" style={{ gridTemplateColumns: `repeat(${data[0].length}, 1fr)`, background: T.fieldBorder }}>
          {data.map((row, r) => row.map((cell, c) => (
            <input
              key={`${r}-${c}`}
              value={cell}
              onChange={(e) => setCell(r, c, e.target.value)}
              className="bg-transparent outline-none text-[11px] px-2 py-1.5 min-w-0"
              style={{ background: T.field, color: r === 0 ? T.text : T.sub, fontWeight: r === 0 ? 600 : 400 }}
            />
          )))}
        </div>
        <div className="flex gap-1 mt-1.5">
          <MiniBtn T={T} onClick={() => update((b) => ({ ...b, data: [...b.data, Array(b.data[0].length).fill("")] }))}>+ fila</MiniBtn>
          <MiniBtn T={T} onClick={() => update((b) => ({ ...b, data: b.data.map((r) => [...r, ""]) }))}>+ col</MiniBtn>
          {data.length > 1 && <MiniBtn T={T} onClick={() => update((b) => ({ ...b, data: b.data.slice(0, -1) }))}>− fila</MiniBtn>}
          {data[0].length > 1 && <MiniBtn T={T} onClick={() => update((b) => ({ ...b, data: b.data.map((r) => r.slice(0, -1)) }))}>− col</MiniBtn>}
        </div>
      </div>
    );
  }

  if (block.type === "image") {
    return wrap(
      <div className="p-2">
        {block.src ? (
          <img src={block.src} alt="" className="w-full rounded-lg object-cover cursor-pointer" style={{ maxHeight: 180 }}
            onClick={() => fileRef.current?.click()} title="Clic para reemplazar" />
        ) : (
          <button
            className="w-full flex flex-col items-center gap-1.5 py-6 rounded-lg text-[11px]"
            style={{ color: T.sub, border: `1px dashed ${T.fieldBorder}` }}
            onClick={() => fileRef.current?.click()}
          >
            <ImageIcon size={18} /> Subir imagen
          </button>
        )}
        <input
          ref={fileRef} type="file" accept="image/*" className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const r = new FileReader();
            r.onload = () => update((b) => ({ ...b, src: r.result }));
            r.readAsDataURL(f);
          }}
        />
      </div>
    );
  }
  return null;
}

function MiniBtn({ T, children, onClick }) {
  return (
    <button className="text-[10px] rounded-md px-1.5 py-0.5 hover:opacity-75"
      style={{ background: T.card, border: `1px solid ${T.fieldBorder}`, color: T.sub }} onClick={onClick}>
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Línea temporal                                                     */
/* ------------------------------------------------------------------ */

function Timeline({ node, T, update }) {
  const [tagDrafts, setTagDrafts] = useState({});
  const stageColor = (i) => PORT_COLORS[i % (PORT_COLORS.length - 1)];

  const setStage = (id, fn) => update((n) => ({ ...n, stages: n.stages.map((s) => s.id === id ? fn(s) : s) }));

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
                  onClick={() => update((n) => ({ ...n, stages: n.stages.filter((x) => x.id !== s.id) }))}
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
        onClick={() => update((n) => ({ ...n, stages: [...n.stages, { id: uid(), title: `Etapa ${n.stages.length + 1}`, tags: [] }] }))}
      >
        + Añadir etapa
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Botones de la barra                                                */
/* ------------------------------------------------------------------ */

function ToolBtn({ T, label, onClick, children }) {
  return (
    <button
      title={label}
      className="p-2 rounded-xl hover:opacity-75 transition-opacity"
      style={{ color: T.text }}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function Sep({ T }) {
  return <span className="w-px h-5 mx-1" style={{ background: T.cardBorder }} />;
}
