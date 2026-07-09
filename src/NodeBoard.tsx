import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import {
  Plus, Trash2, Moon, Sun, Spline, Minus, ZoomIn, ZoomOut, Maximize2, Clock,
  ArrowLeft, Filter, Settings, CircleUser, Magnet, Download, LoaderCircle,
} from "lucide-react";
import { api, useBoardPersistence } from "./api";
import { PORT_COLORS } from "./types";
import type { Node, Edge, Port, PortColor } from "./types";
import type { Pending, DragState, ColorMenu, DeletePortConfirm } from "./lib/canvas-types";
import { portPos, edgePath } from "./lib/geometry";
import { THEMES } from "./lib/theme";
import { uid } from "./lib/id";
import { NodeCard } from "./components/NodeCard";
import { ToolBtn } from "./components/ToolBtn";
import { Sep } from "./components/Sep";
import { TagsModal } from "./components/TagsModal";
import { FilterPanel } from "./components/FilterPanel";
import { SettingsModal } from "./components/SettingsModal";
import { ProfileMenu } from "./components/ProfileMenu";
import { useAuth } from "./lib/auth-context";
import { computeNodeOpacity, type FilterMode } from "./lib/filter";
import { usePwa } from "./lib/pwa";
import { exportBoardToPng } from "./lib/board-export";

/* ------------------------------------------------------------------ */
/*  Constantes de geometría y tema                                     */
/* ------------------------------------------------------------------ */

const CARD_W = 280;
const TIMELINE_W = 360;

/* ---------- Snap magnético ---------- */
const SNAP_ENTRY_THRESHOLD = 30;   // px mundo — umbral para enganchar
const SNAP_EXIT_THRESHOLD = 45;    // px mundo — umbral para soltar (histéresis)
const SNAP_DISTANCE = 32;          // px (2 rem) — separación estándar entre nodos

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface NodeBoardProps {
  boardId: string;
  onBack: () => void;
  theme: string;
  onToggleTheme: () => void;
}

/* ------------------------------------------------------------------ */
/*  Componente principal                                               */
/* ------------------------------------------------------------------ */

export default function NodeBoard({ boardId, onBack, theme, onToggleTheme }: NodeBoardProps) {
  const { user, logout } = useAuth();
  const { setSaveStatus } = usePwa();
  const T = THEMES[theme] || THEMES.dark;

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [boardName, setBoardName] = useState("");
  const { status, boardVersion, conflict, reloadBoardFromServer } = useBoardPersistence({ boardId, nodes, edges, setNodes, setEdges, boardName });
  const [reloadConfirm, setReloadConfirm] = useState(false);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);     // conexión en curso
  const [mouseWorld, setMouseWorld] = useState({ x: 0, y: 0 });
  const [menuNode, setMenuNode] = useState<string | null>(null);
  const [tagsNode, setTagsNode] = useState<string | null>(null); // nodo con el modal de tags abierto
  const [colorMenu, setColorMenu] = useState<ColorMenu>(null); // {nodeId, portId, x, y} en coords de pantalla
  const [deletePortConfirm, setDeletePortConfirm] = useState<DeletePortConfirm>(null);
  const [defaultCurved, setDefaultCurved] = useState(true);

  const [filterOpen, setFilterOpen] = useState(false);
  const [filterTags, setFilterTags] = useState<string[]>([]);
  const [filterMode, setFilterMode] = useState<FilterMode>("wide");

  const [showGrid, setShowGrid] = useState(true);
  const [showHelp, setShowHelp] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [exportingPng, setExportingPng] = useState(false);

  const [clipboard, setClipboard] = useState<Node[] | null>(null);
  const lastPasteOffset = useRef<{ dx: number; dy: number } | null>(null);

  // Limpiar clipboard al cambiar de board para evitar pegar contenido entre tableros
  useEffect(() => {
    setClipboard(null);
    lastPasteOffset.current = null;
  }, [boardId]);

  // Cargar nombre del board al montar
  useEffect(() => {
    if (!boardId) return;
    api.getBoard(boardId).then((board) => setBoardName(board.name)).catch(() => {});
  }, [boardId]);

  const [view, setView] = useState({ x: 40, y: 20, z: 1 });

  useEffect(() => {
    setSaveStatus(status);
    return () => setSaveStatus(null);
  }, [setSaveStatus, status]);

  const viewRef = useRef(view);
  viewRef.current = view;

  const canvasRef = useRef<HTMLDivElement>(null);
  const worldRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState>(null);
  const groupDragMovedRef = useRef(false);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const marqueeRef = useRef<{ sx: number; sy: number; mx: number; my: number } | null>(null);
  const [marqueeRect, setMarqueeRect] = useState<{ sx: number; sy: number; mx: number; my: number } | null>(null);
  const [snapEnabled, setSnapEnabled] = useState(true);
  const snapEnabledRef = useRef(snapEnabled);
  snapEnabledRef.current = snapEnabled;
  const snapTargetRef = useRef<{ axis: "x" | "y"; value: number } | null>(null);

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
      if (marqueeRef.current) {
        const rect = canvasRef.current!.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        marqueeRef.current.mx = mx;
        marqueeRef.current.my = my;
        setMarqueeRect({ sx: marqueeRef.current.sx, sy: marqueeRef.current.sy, mx, my });
        return;
      }
      const d = dragRef.current;
      if (!d) return;
      if (d.kind === "pan") {
        setView((v) => ({ ...v, x: d.vx + (e.clientX - d.sx), y: d.vy + (e.clientY - d.sy) }));
      } else if (d.kind === "node") {
        const w = toWorld(e.clientX, e.clientY);
        let nx = w.x - d.ox, ny = w.y - d.oy;
        if (snapEnabledRef.current) {
          const snapped = applySnap(d.id, nx, ny);
          if (snapped) { nx = snapped.x; ny = snapped.y; }
        } else {
          snapTargetRef.current = null;
        }
        setNodes((ns) => ns.map((n) => (n.id === d.id ? { ...n, x: nx, y: ny } : n)));
      } else if (d.kind === "group") {
        const w = toWorld(e.clientX, e.clientY);
        const dx = w.x - d.wx;
        const dy = w.y - d.wy;
        groupDragMovedRef.current = true;
        setNodes((ns) => ns.map((n) => {
          const orig = d.origins[n.id];
          return orig ? { ...n, x: orig.x + dx, y: orig.y + dy } : n;
        }));
      }
    };
    const up = () => {
      if (marqueeRef.current) {
        const m = marqueeRef.current;
        marqueeRef.current = null;
        setMarqueeRect(null);
        const dx = m.mx - m.sx, dy = m.my - m.sy;
        if (dx < -3 || dx > 3 || dy < -3 || dy > 3) {
          const rect = canvasRef.current!.getBoundingClientRect();
          const v = viewRef.current;
          const wsx = Math.min(m.sx, m.mx) + rect.left, wsy = Math.min(m.sy, m.my) + rect.top;
          const wmx = Math.max(m.sx, m.mx) + rect.left, wmy = Math.max(m.sy, m.my) + rect.top;
          const worldMin = toWorld(wsx, wsy);
          const worldMax = toWorld(wmx, wmy);
          const currentNodes = nodesRef.current;
          const selected = currentNodes.filter((n) =>
            n.x >= worldMin.x && n.x <= worldMax.x && n.y >= worldMin.y && n.y <= worldMax.y
          );
          setSelectedNodeIds(selected.map((n) => n.id));
        }
        return;
      }
      const d = dragRef.current;
      if (d?.kind === "node") snapTargetRef.current = null;
      if (d?.kind === "group" && !groupDragMovedRef.current) {
        // El usuario hizo click (sin arrastrar) sobre un nodo del grupo → reemplazar selección
        setSelectedNodeIds([d.clickedId]);
        setSelectedEdgeId(null);
      }
      dragRef.current = null;
      groupDragMovedRef.current = false;
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [toWorld]);

  /* ---------------- Teclado: suprimir + copy/paste ----------------- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if ((e.key === "Delete" || e.key === "Backspace") && (selectedNodeIds.length > 0 || selectedEdgeId)) {
        e.preventDefault();
        deleteSelection();
      }
      if (e.key === "Escape") { setPending(null); setSelectedNodeIds([]); setSelectedEdgeId(null); setMenuNode(null); setColorMenu(null); setTagsNode(null); setFilterOpen(false); }

      if (e.key === "c" && (e.ctrlKey || e.metaKey) && selectedNodeIds.length > 0) {
        const toCopy = nodes.filter((n) => selectedNodeIds.includes(n.id));
        if (toCopy.length > 0) {
          e.preventDefault();
          setClipboard(toCopy);
          lastPasteOffset.current = null;
        }
      }

      if (e.key === "v" && (e.ctrlKey || e.metaKey) && clipboard) {
        e.preventDefault();
        const PASTE_OFFSET = 20;
        const prev = lastPasteOffset.current ?? { dx: 0, dy: 0 };
        const dx = prev.dx + PASTE_OFFSET;
        const dy = prev.dy + PASTE_OFFSET;
        lastPasteOffset.current = { dx, dy };
        const newNodes: Node[] = clipboard.map((src) => {
          const newPorts = src.ports.map((p) => ({ ...p, id: uid() }));
          const common = { id: uid(), x: src.x + dx, y: src.y + dy, w: src.w, title: src.title, tags: [...src.tags], ports: newPorts };
          return src.type === "card"
            ? { ...common, type: "card" as const, blocks: src.blocks.map((b) => ({ ...b, id: uid() })) }
            : { ...common, type: "timeline" as const, stages: src.stages.map((s) => ({ ...s, id: uid(), tags: [...s.tags] })) };
        });
        setNodes((ns) => [...ns, ...newNodes]);
        setSelectedNodeIds(newNodes.map((n) => n.id));
        setSelectedEdgeId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  /* ---------------- Selección de nodos ------------------------------ */
  const handleNodeClick = useCallback((id: string, e: { shiftKey: boolean; ctrlKey: boolean }) => {
    setSelectedEdgeId(null);
    if (e.shiftKey || e.ctrlKey) {
      setSelectedNodeIds((prev) =>
        prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
      );
    } else {
      setSelectedNodeIds([id]);
    }
  }, []);

  /* ---------------- Mutadores --------------------------------------- */
  const updateNode = (id: string, fn: (n: Node) => Node) => setNodes((ns) => ns.map((n) => (n.id === id ? fn(n) : n)));

  const deleteSelection = () => {
    if (selectedNodeIds.length > 0) {
      const ids = new Set(selectedNodeIds);
      setNodes((ns) => ns.filter((n) => !ids.has(n.id)));
      setEdges((es) => es.filter((e) => !ids.has(e.from.nodeId) && !ids.has(e.to.nodeId)));
      setSelectedNodeIds([]);
    } else if (selectedEdgeId) {
      setEdges((es) => es.filter((e) => e.id !== selectedEdgeId));
      setSelectedEdgeId(null);
    }
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
      const pendingColor = port.side === "left" && inputPortColors[node.id]?.[port.id]
        ? inputPortColors[node.id][port.id]
        : port.color;
      setPending({ nodeId: node.id, portId: port.id, color: pendingColor });
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

  /* ---------- Snap helpers ---------- */
  const getNodeWorldHeight = (nodeId: string): number => {
    const el = canvasRef.current?.querySelector(`[data-testid="node-${nodeId}"]`) as HTMLElement | null;
    return el?.offsetHeight ?? 120;
  };

  const applySnap = (draggedId: string, px: number, py: number): { x: number; y: number } | null => {
    // La histéresis fija únicamente el eje enganchado; el eje perpendicular
    // conserva la posición libre que viene del mouse.
    const cur = snapTargetRef.current;
    if (cur) {
      if (cur.axis === "x") {
        const d = Math.abs(px - cur.value);
        if (d < SNAP_EXIT_THRESHOLD) return { x: cur.value, y: py };
      } else {
        const d = Math.abs(py - cur.value);
        if (d < SNAP_EXIT_THRESHOLD) return { x: px, y: cur.value };
      }
    }
    snapTargetRef.current = null;

    const dragged = nodesRef.current.find((n) => n.id === draggedId);
    if (!dragged) return null;
    const dragH = getNodeWorldHeight(draggedId);
    const others = nodesRef.current.filter((n) => n.id !== draggedId);
    let best: { axis: "x" | "y"; value: number; dist: number } | null = null;

    for (const other of others) {
      const otherH = getNodeWorldHeight(other.id);
      // Derecha — solo si el nodo arrastrado está a la izquierda del destino
      const txr = other.x + other.w + SNAP_DISTANCE;
      const dxr = Math.abs(px - txr);
      if (px < txr + 2 && dxr < SNAP_ENTRY_THRESHOLD && (!best || dxr < best.dist))
        best = { axis: "x", value: txr, dist: dxr };
      // Izquierda — solo si el nodo arrastrado está a la derecha del destino
      const txl = other.x - dragged.w - SNAP_DISTANCE;
      const dxl = Math.abs(px - txl);
      if (px > txl - 2 && dxl < SNAP_ENTRY_THRESHOLD && (!best || dxl < best.dist))
        best = { axis: "x", value: txl, dist: dxl };
      // Abajo — solo si el nodo arrastrado está arriba del destino
      const tyd = other.y + otherH + SNAP_DISTANCE;
      const dyd = Math.abs(py - tyd);
      if (py < tyd + 2 && dyd < SNAP_ENTRY_THRESHOLD && (!best || dyd < best.dist))
        best = { axis: "y", value: tyd, dist: dyd };
      // Arriba — solo si el nodo arrastrado está abajo del destino
      const tyu = other.y - dragH - SNAP_DISTANCE;
      const dyu = Math.abs(py - tyu);
      if (py > tyu - 2 && dyu < SNAP_ENTRY_THRESHOLD && (!best || dyu < best.dist))
        best = { axis: "y", value: tyu, dist: dyu };
    }

    if (best) {
      snapTargetRef.current = { axis: best.axis, value: best.value };
      return best.axis === "x" ? { x: best.value, y: py } : { x: px, y: best.value };
    }
    return null;
  };

  /* ---------------- Render de aristas ------------------------------- */
  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));

  // Tags únicos del tablero derivados del estado local: se unen con los del servidor en el
  // modal para que un tag recién creado esté disponible antes de que el autosave persista.
  const localBoardTags = useMemo(() => {
    const seen = new Map<string, string>();
    for (const n of nodes) for (const t of n.tags) if (!seen.has(t.toLowerCase())) seen.set(t.toLowerCase(), t);
    return [...seen.values()];
  }, [nodes]);
  // Mapa de colores calculados para puertos de entrada (left): con 1 conexión
  // entrante adopta el color del puerto out de origen; con 0 o múltiples conexiones
  // usa su propio color almacenado (por defecto blanco #E8EBF0).
  const inputPortColors = useMemo(() => {
    const map: Record<string, Record<string, PortColor>> = {};
    for (const node of nodes) {
      for (const port of node.ports) {
        if (port.side !== "left") continue;
        const incoming = edges.filter((e) => e.to.nodeId === node.id && e.to.portId === port.id);
        if (incoming.length === 1) {
          const edge = incoming[0];
          const srcNode = nodeById[edge.from.nodeId];
          if (srcNode) {
            const srcPort = srcNode.ports.find((p) => p.id === edge.from.portId);
            if (srcPort) {
              if (!map[node.id]) map[node.id] = {};
              map[node.id][port.id] = srcPort.color;
            }
          }
        }
      }
    }
    return map;
  }, [nodes, edges, nodeById]);

  const tagsNodeObj = tagsNode ? nodeById[tagsNode] : null;
  const renderedEdges = edges.map((e) => {
    const a = nodeById[e.from.nodeId] && portPos(nodeById[e.from.nodeId], e.from.portId);
    const b = nodeById[e.to.nodeId] && portPos(nodeById[e.to.nodeId], e.to.portId);
    if (!a || !b) return null;
    return { ...e, a, b, color: a.color };
  }).filter((e): e is NonNullable<typeof e> => e !== null);

  const pendingPos = pending && nodeById[pending.nodeId] ? portPos(nodeById[pending.nodeId], pending.portId) : null;

  const selectedEdge = selectedEdgeId ? edges.find((e) => e.id === selectedEdgeId) : null;

  const handleExportPng = useCallback(async () => {
    if (exportingPng || nodes.length === 0 || !canvasRef.current || !worldRef.current) return;
    setExportingPng(true);
    try {
      await exportBoardToPng({
        canvasEl: canvasRef.current,
        nodes,
        boardName,
        theme: T,
        showGrid,
      });
    } catch (error) {
      console.error("No se pudo exportar el board como PNG", error);
      window.alert("No se pudo exportar el board como PNG.");
    } finally {
      setExportingPng(false);
    }
  }, [T, boardName, exportingPng, nodes, showGrid]);

  // Opacidad por nodo según el filtro de tags
  const nodeOpacities = useMemo(() => {
    const map: Record<string, number> = {};
    for (const n of nodes) {
      map[n.id] = computeNodeOpacity(n.tags, filterOpen, filterTags, filterMode);
    }
    return map;
  }, [nodes, filterOpen, filterTags, filterMode]);

  /* ================================================================== */
  return (
    <div
      ref={canvasRef}
      data-testid="board-canvas"
      className="relative w-full app-dvh overflow-hidden select-none"
      style={{
        background: T.bg,
        backgroundImage: showGrid ? `radial-gradient(${T.dot} 1.6px, transparent 1.6px)` : undefined,
        backgroundSize: showGrid ? `${26 * view.z}px ${26 * view.z}px` : undefined,
        backgroundPosition: showGrid ? `${view.x}px ${view.y}px` : undefined,
        color: T.text,
        fontFamily: "'Inter','Segoe UI',system-ui,sans-serif",
        cursor: dragRef.current?.kind === "pan" ? "grabbing" : marqueeRect ? "crosshair" : "default",
      }}
      onMouseDown={(e) => {
        if (e.target !== canvasRef.current) return;
        setSelectedNodeIds([]); setSelectedEdgeId(null); setMenuNode(null); setPending(null); setColorMenu(null);
        if (e.button === 0) {
          if (e.ctrlKey || e.metaKey) {
            const rect = canvasRef.current!.getBoundingClientRect();
            const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
            marqueeRef.current = { sx, sy, mx: sx, my: sy };
            setMarqueeRect({ sx, sy, mx: sx, my: sy });
          } else {
            e.preventDefault();
            dragRef.current = { kind: "pan", sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
          }
        }
      }}
      onDoubleClick={(e) => {
        if (e.target === canvasRef.current) addNode("card", toWorld(e.clientX, e.clientY));
      }}
    >
      {/* ---------- Capa transformada (mundo) ---------- */}
      <div
        ref={worldRef}
        data-testid="board-world"
        className="absolute top-0 left-0"
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.z})`, transformOrigin: "0 0" }}
      >
        {/* Aristas */}
        <svg data-testid="canvas-edges" className="absolute top-0 left-0 overflow-visible pointer-events-none" width="1" height="1">
          {renderedEdges.map((e) => (
            <g key={e.id}>
              <path
                d={edgePath(e.a, e.b, e.curved)}
                stroke="transparent" strokeWidth={14} fill="none"
                className="pointer-events-auto cursor-pointer"
                onClick={(ev) => { ev.stopPropagation(); setSelectedEdgeId(e.id); setSelectedNodeIds([]); }}
              />
              <path
                d={edgePath(e.a, e.b, e.curved)}
                stroke={e.color} fill="none"
                strokeWidth={selectedEdgeId === e.id ? 2.6 : 1.6}
                opacity={selectedEdgeId === e.id ? 1 : 0.75}
                style={selectedEdgeId === e.id
                  ? { filter: `drop-shadow(0 0 6px ${e.color})` } : undefined}
              />
            </g>
          ))}
          {pendingPos && (
            <path
              data-export-exclude="true"
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
            selected={selectedNodeIds.includes(node.id)}
            opacity={nodeOpacities[node.id]}
            menuOpen={menuNode === node.id}
            onOpenMenu={() => setMenuNode(menuNode === node.id ? null : node.id)}
            onOpenTags={() => { setTagsNode(node.id); setMenuNode(null); }}
            onSelect={(e) => { handleNodeClick(node.id, e); setMenuNode(null); }}
            onStartDrag={(e) => {
              const w = toWorld(e.clientX, e.clientY);
              const isGroupDragIntent = !e.shiftKey && !e.ctrlKey && !e.metaKey
                && selectedNodeIds.length > 1 && selectedNodeIds.includes(node.id);
              if (isGroupDragIntent) {
                const origins: Record<string, { x: number; y: number }> = {};
                for (const selId of selectedNodeIds) {
                  const selNode = nodes.find((n) => n.id === selId);
                  if (selNode) origins[selId] = { x: selNode.x, y: selNode.y };
                }
                groupDragMovedRef.current = false;
                dragRef.current = { kind: "group", ids: [...selectedNodeIds], origins, wx: w.x, wy: w.y, clickedId: node.id };
              } else {
                snapTargetRef.current = null;
                dragRef.current = { kind: "node", id: node.id, ox: w.x - node.x, oy: w.y - node.y };
                handleNodeClick(node.id, e);
              }
            }}
            onDelete={() => { setNodes((ns) => ns.filter((n) => n.id !== node.id)); setEdges((es) => es.filter((e2) => e2.from.nodeId !== node.id && e2.to.nodeId !== node.id)); setSelectedNodeIds((prev) => prev.filter((id) => id !== node.id)); }}
            update={(fn) => updateNode(node.id, fn)}
            onPortClick={(port) => onPortClick(node, port)}
            onPortCycle={(portId) => cyclePortColor(node.id, portId)}
            inputPortColors={inputPortColors}
            onPortContext={(portId, e) => {
              e.preventDefault(); e.stopPropagation();
              const rect = canvasRef.current!.getBoundingClientRect();
              setColorMenu({ nodeId: node.id, portId, x: e.clientX - rect.left, y: e.clientY - rect.top });
            }}
            pending={pending}
          />
        ))}
      </div>

      {/* ---------- Marquee de selección ---------- */}
      {marqueeRect && (() => {
        const l = Math.min(marqueeRect.sx, marqueeRect.mx);
        const t = Math.min(marqueeRect.sy, marqueeRect.my);
        const w = Math.abs(marqueeRect.mx - marqueeRect.sx);
        const h = Math.abs(marqueeRect.my - marqueeRect.sy);
        if (w < 3 && h < 3) return null;
        return (
          <div
            data-export-exclude="true"
            className="absolute z-20 pointer-events-none"
            style={{
              left: l, top: t, width: w, height: h,
              background: "rgba(99,102,241,0.08)",
              border: "1.5px solid rgba(99,102,241,0.5)",
              borderRadius: 4,
            }}
          />
        );
      })()}

      {/* ---------- Modal de tags ---------- */}
      {tagsNodeObj && (
        <div data-export-exclude="true" className="contents">
          <TagsModal
            T={T}
            theme={theme}
            boardId={boardId}
            nodeTitle={tagsNodeObj.title}
            tags={tagsNodeObj.tags}
            localBoardTags={localBoardTags}
            setTags={(tags) => updateNode(tagsNodeObj.id, (n) => ({ ...n, tags }))}
            onClose={() => setTagsNode(null)}
          />
        </div>
      )}

      {/* ---------- Panel de filtro por tags ---------- */}
      {filterOpen && (
        <div data-export-exclude="true" className="contents">
          <FilterPanel
            T={T}
            allBoardTags={localBoardTags}
            filterTags={filterTags}
            filterMode={filterMode}
            onChangeFilterTags={setFilterTags}
            onChangeFilterMode={setFilterMode}
            onClose={() => setFilterOpen(false)}
          />
        </div>
      )}

      {/* ---------- Menú contextual de colores ---------- */}
      {colorMenu && (
        <div
          data-export-exclude="true"
          className="absolute z-30 flex flex-col gap-1.5 rounded-2xl px-3 py-2"
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
          <div className="flex items-center gap-2">
            {PORT_COLORS.map((c) => {
              const port = nodeById[colorMenu.nodeId]?.ports.find((p) => p.id === colorMenu.portId);
              const displayColor = port && port.side === "left" && inputPortColors[colorMenu.nodeId]?.[colorMenu.portId]
                ? inputPortColors[colorMenu.nodeId][colorMenu.portId]
                : port?.color;
              const current = displayColor === c;
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
          <div className="h-px" style={{ background: T.cardBorder }} />
          <button
            className="flex items-center gap-1.5 text-xs rounded-xl px-2.5 py-1.5 transition-colors hover:opacity-80"
            style={{ color: "#F87171" }}
            onClick={() => {
              const node = nodeById[colorMenu.nodeId];
              if (!node) return;
              const edgeCount = edges.filter(
                (e) => (e.from.nodeId === colorMenu.nodeId && e.from.portId === colorMenu.portId)
                    || (e.to.nodeId === colorMenu.nodeId && e.to.portId === colorMenu.portId)
              ).length;
              setColorMenu(null);
              setDeletePortConfirm({ nodeId: colorMenu.nodeId, portId: colorMenu.portId, step: "confirm", edgeCount });
            }}
          >
            <Trash2 size={12} /> Eliminar puerto
          </button>
        </div>
      )}

      {/* ---------- Confirmación de eliminación de puerto ---------- */}
      {deletePortConfirm && deletePortConfirm.step === "confirm" && (
        <div
          data-export-exclude="true"
          className="absolute inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,.5)" }}
          onClick={() => setDeletePortConfirm(null)}
        >
          <div
            className="rounded-2xl px-6 py-5 shadow-xl max-w-sm w-full mx-4"
            style={{ background: T.card, border: `1px solid ${T.cardBorder}` }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="font-semibold mb-2" style={{ color: T.text }}>¿Eliminar puerto?</div>
            <div className="text-sm mb-4" style={{ color: T.sub }}>
              {deletePortConfirm.edgeCount === 0
                ? "Este puerto no tiene conexiones. Se eliminará sin afectar edges."
                : `Este puerto tiene ${deletePortConfirm.edgeCount} conexión${deletePortConfirm.edgeCount !== 1 ? "es" : ""}. Eliminarlo también eliminará esa${deletePortConfirm.edgeCount !== 1 ? "s" : ""} ${deletePortConfirm.edgeCount} conexión${deletePortConfirm.edgeCount !== 1 ? "es" : ""}.`}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                className="px-4 py-2 rounded-xl text-sm font-medium"
                style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.text }}
                onClick={() => setDeletePortConfirm(null)}
              >
                Cancelar
              </button>
              <button
                className="px-4 py-2 rounded-xl text-sm font-medium"
                style={{ background: "#F87171", color: "#fff" }}
                onClick={() => setDeletePortConfirm((prev) => prev ? { ...prev, step: "final" } : null)}
              >
                Continuar
              </button>
            </div>
          </div>
        </div>
      )}

      {deletePortConfirm && deletePortConfirm.step === "final" && (
        <div
          data-export-exclude="true"
          className="absolute inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,.5)" }}
          onClick={() => setDeletePortConfirm(null)}
        >
          <div
            className="rounded-2xl px-6 py-5 shadow-xl max-w-sm w-full mx-4"
            style={{ background: T.card, border: `1px solid ${T.cardBorder}` }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="font-semibold mb-2" style={{ color: T.text }}>Confirmación final</div>
            <div className="text-sm mb-4" style={{ color: T.sub }}>
              Esta acción no se puede deshacer. ¿Estás seguro de que deseas eliminar este puerto{deletePortConfirm.edgeCount > 0 ? ` y sus ${deletePortConfirm.edgeCount} conexión${deletePortConfirm.edgeCount !== 1 ? "es" : ""}` : ""}?
            </div>
            <div className="flex gap-2 justify-end">
              <button
                className="px-4 py-2 rounded-xl text-sm font-medium"
                style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.text }}
                onClick={() => setDeletePortConfirm(null)}
              >
                Cancelar
              </button>
              <button
                className="px-4 py-2 rounded-xl text-sm font-medium"
                style={{ background: "#F87171", color: "#fff" }}
                onClick={() => {
                  const conf = deletePortConfirm;
                  if (!conf) return;
                  // 1) Eliminar edges asociadas al puerto
                  setEdges((es) => es.filter(
                    (e) => !(e.from.nodeId === conf.nodeId && e.from.portId === conf.portId)
                        && !(e.to.nodeId === conf.nodeId && e.to.portId === conf.portId)
                  ));
                  // 2) Eliminar el puerto del nodo
                  updateNode(conf.nodeId, (n) => ({
                    ...n,
                    ports: n.ports.filter((p) => p.id !== conf.portId),
                  }));
                  setDeletePortConfirm(null);
                }}
              >
                Eliminar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ---------- Barra de herramientas ---------- */}
      <div
        data-export-exclude="true"
        className="absolute app-safe-top-left flex items-center gap-1 rounded-2xl px-2 py-1.5 max-w-[calc(100%-32px-var(--safe-left)-var(--safe-right))]"
        style={{ background: T.card, border: `1px solid ${T.cardBorder}`, boxShadow: "0 14px 34px -14px rgba(0,0,0,.6)" }}
      >
        <ToolBtn T={T} testId="back-btn" label="Volver" onClick={onBack}><ArrowLeft size={16} /></ToolBtn>
        <input
          data-testid="board-title"
          value={boardName}
          onChange={(e) => setBoardName(e.target.value)}
          className="bg-transparent text-sm font-medium outline-none"
          style={{ color: T.text, width: `${Math.max(boardName.length + 2, 10)}ch` }}
          placeholder="Nombre del board"
          onMouseDown={(e) => e.stopPropagation()}
        />
        <Sep T={T} />
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
        <ToolBtn T={T} testId="filter-toggle" label={filterOpen ? "Cerrar filtro" : "Filtrar por tags"} onClick={() => setFilterOpen((v) => !v)}>
          <Filter size={16} />
        </ToolBtn>
        <Sep T={T} />
        <ToolBtn T={T} label={defaultCurved ? "Conector: curvo" : "Conector: recto"} onClick={() => setDefaultCurved((c) => !c)}>
          {defaultCurved ? <Spline size={16} /> : <Minus size={16} />}
        </ToolBtn>
        <ToolBtn T={T} label="Tema" onClick={onToggleTheme}>
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </ToolBtn>
        <ToolBtn T={T} testId="snap-toggle" label={snapEnabled ? "Snap: activado" : "Snap: desactivado"} onClick={() => { const next = !snapEnabled; if (!next) snapTargetRef.current = null; snapEnabledRef.current = next; setSnapEnabled(next); }}>
          <span style={{ opacity: snapEnabled ? 1 : 0.35 }}><Magnet size={16} /></span>
        </ToolBtn>
        <ToolBtn
          T={T}
          testId="export-png"
          label={exportingPng ? "Exportando PNG" : "Exportar PNG"}
          onClick={handleExportPng}
          disabled={exportingPng || nodes.length === 0}
        >
          {exportingPng ? <LoaderCircle size={16} className="animate-spin" /> : <Download size={16} />}
        </ToolBtn>
        <Sep T={T} />
        <ToolBtn T={T} label="Alejar" onClick={() => setView((v) => ({ ...v, z: Math.max(0.25, v.z * 0.9) }))}><ZoomOut size={16} /></ToolBtn>
        <span className="text-xs w-10 text-center" style={{ color: T.sub }}>{Math.round(view.z * 100)}%</span>
        <ToolBtn T={T} label="Acercar" onClick={() => setView((v) => ({ ...v, z: Math.min(2.5, v.z * 1.1) }))}><ZoomIn size={16} /></ToolBtn>
        <ToolBtn T={T} label="Restablecer vista" onClick={() => setView({ x: 40, y: 20, z: 1 })}><Maximize2 size={16} /></ToolBtn>
        <Sep T={T} />
        <ToolBtn T={T} label="Ajustes" onClick={() => { setSettingsOpen(true); setProfileOpen(false); }}><Settings size={16} /></ToolBtn>
        <ToolBtn T={T} label="Perfil" onClick={() => { setProfileOpen((v) => !v); setSettingsOpen(false); }}><CircleUser size={16} /></ToolBtn>
      </div>

      {/* ---------- Barra de acciones de selección ---------- */}
      {(selectedNodeIds.length > 0 || selectedEdgeId) && (
        <div
          data-export-exclude="true"
          className="absolute app-safe-bottom-center flex items-center gap-1 rounded-2xl px-2 py-1.5"
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

      {/* ---------- Modal de ajustes ---------- */}
      {settingsOpen && (
        <div data-export-exclude="true" className="contents">
          <SettingsModal
            T={T} theme={theme} mode="board"
            showGrid={showGrid}
            defaultCurved={defaultCurved}
            showHelp={showHelp}
            onChangeShowGrid={setShowGrid}
            onChangeDefaultCurved={setDefaultCurved}
            onChangeShowHelp={setShowHelp}
            onToggleTheme={onToggleTheme}
            onReset={() => { setShowGrid(true); setDefaultCurved(true); setShowHelp(true); setView({ x: 40, y: 20, z: 1 }); }}
            onClose={() => setSettingsOpen(false)}
          />
        </div>
      )}

      {/* ---------- Menú de perfil ---------- */}
      {profileOpen && user && (
        <div data-export-exclude="true" className="contents">
          <ProfileMenu
            T={T} theme={theme}
            user={user}
            onLogout={logout}
            onCloseProfile={onBack}
            onClose={() => setProfileOpen(false)}
          />
        </div>
      )}

      {/* ---------- Conflicto de versión ---------- */}
      {conflict && !reloadConfirm && (
        <div
          data-export-exclude="true"
          className="absolute app-safe-top-right flex flex-col items-end gap-2 z-40 max-w-xs"
          style={{ top: "calc(var(--safe-top, 0px) + 8px)" }}
        >
          <div
            className="rounded-2xl px-4 py-3 text-sm shadow-lg"
            style={{ background: "rgba(248,113,113,.12)", border: "1px solid rgba(248,113,113,.35)", color: "#F87171" }}
          >
            <div className="font-semibold mb-1">Cambios externos detectados</div>
            <div className="text-[13px]" style={{ opacity: 0.85 }}>
              Este board fue modificado desde otro cliente.
            </div>
            {conflict && (
              <div className="text-[11px] mt-1.5" style={{ opacity: 0.6 }}>
                Versión local esperada: {conflict.expectedVersion} · Versión actual del servidor: {conflict.currentVersion}
              </div>
            )}
            <button
              className="mt-2 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors"
              style={{ background: "#F87171", color: "#fff" }}
              onClick={() => setReloadConfirm(true)}
            >
              Recargar board
            </button>
          </div>
        </div>
      )}

      {/* ---------- Confirmación de recarga ---------- */}
      {reloadConfirm && (
        <div
          data-export-exclude="true"
          className="absolute inset-0 z-50 flex items-center justify-center"
          style={{ background: "rgba(0,0,0,.5)" }}
          onClick={() => setReloadConfirm(false)}
        >
          <div
            className="rounded-2xl px-6 py-5 shadow-xl max-w-sm w-full mx-4"
            style={{ background: T.card, border: `1px solid ${T.cardBorder}` }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="font-semibold mb-2" style={{ color: T.text }}>¿Recargar board?</div>
            <div className="text-sm mb-4" style={{ color: T.sub }}>
              Al recargar se descartarán los cambios locales no guardados.
            </div>
            <div className="flex gap-2 justify-end">
              <button
                className="px-4 py-2 rounded-xl text-sm font-medium"
                style={{ background: T.field, border: `1px solid ${T.fieldBorder}`, color: T.text }}
                onClick={() => setReloadConfirm(false)}
              >
                Cancelar
              </button>
              <button
                className="px-4 py-2 rounded-xl text-sm font-medium"
                style={{ background: "#F87171", color: "#fff" }}
                onClick={async () => {
                  const ok = await reloadBoardFromServer();
                  if (ok) setReloadConfirm(false);
                }}
              >
                Recargar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ---------- Ayuda ---------- */}
      {showHelp && (
        <div data-export-exclude="true" className="absolute app-safe-bottom-left text-[11px] leading-relaxed max-w-xs" style={{ color: T.sub }}>
          Doble clic en el lienzo: nuevo nodo · Clic en un punto de color: iniciar/terminar conexión ·
          Botón derecho en un punto: elegir color · Rueda: zoom · Arrastrar fondo: mover lienzo ·
          Ctrl+arrastrar fondo: selección múltiple · Snap magnético al arrastrar nodos
        </div>
      )}
    </div>
  );
}
