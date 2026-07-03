import type { Node, PortSide } from "../types";
import type { PortPos } from "./canvas-types";

/* ------------------------------------------------------------------ */
/*  Constantes de geometría de puertos                                 */
/* ------------------------------------------------------------------ */

export const PORT_Y0 = 56;   // y del primer puerto (relativo al nodo)
export const PORT_DY = 26;   // separación vertical entre puertos

/* ------------------------------------------------------------------ */
/*  Utilidades de geometría (funciones puras)                          */
/* ------------------------------------------------------------------ */

export function portPos(node: Node, portId: string): PortPos | null {
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

export function edgePath(a: { x: number; y: number; side: PortSide }, b: { x: number; y: number; side: PortSide }, curved: boolean) {
  if (!curved) return `M ${a.x} ${a.y} L ${b.x} ${b.y}`;
  const dx = Math.max(60, Math.abs(b.x - a.x) / 2);
  const c1x = a.side === "left" ? a.x - dx : a.x + dx;
  const c2x = b.side === "right" ? b.x + dx : b.x - dx;
  return `M ${a.x} ${a.y} C ${c1x} ${a.y}, ${c2x} ${b.y}, ${b.x} ${b.y}`;
}
