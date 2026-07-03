import type { PortColor, PortSide } from "../types";

/* ------------------------------------------------------------------ */
/*  Tipos de apoyo del estado de interacción del canvas               */
/* ------------------------------------------------------------------ */

export interface PortPos {
  x: number;
  y: number;
  side: PortSide;
  color: PortColor;
}

export type Pending = { nodeId: string; portId: string; color: PortColor } | null;

export type Selection = { type: "node" | "edge"; id: string } | null;

export type ColorMenu = { nodeId: string; portId: string; x: number; y: number } | null;

export type DragState =
  | { kind: "pan"; sx: number; sy: number; vx: number; vy: number }
  | { kind: "node"; id: string; ox: number; oy: number }
  | null;
