import { toBlob } from "html-to-image";
import type { Node } from "../types";
import type { Theme } from "./theme";

export type ExportRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type ExportBounds = ExportRect;

type ExportableNode = Pick<Node, "id" | "x" | "y" | "w">;

export const BOARD_EXPORT_MARGIN = 96;
export const BOARD_EXPORT_PIXEL_RATIO = 3;
const BOARD_EXPORT_GRID_SIZE = 26;
const PORT_DOT_OVERFLOW = 8;

type ExportBoardOptions = {
  canvasEl: HTMLElement;
  nodes: ExportableNode[];
  boardName: string;
  theme: Theme;
  showGrid: boolean;
};

type ExportBoardResult = {
  bounds: ExportBounds;
  fileName: string;
  pixelRatio: number;
};

export function unionRects(rects: ExportRect[]): ExportRect | null {
  if (rects.length === 0) return null;

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const rect of rects) {
    if (!Number.isFinite(rect.x) || !Number.isFinite(rect.y) || rect.width <= 0 || rect.height <= 0) {
      continue;
    }
    minX = Math.min(minX, rect.x);
    minY = Math.min(minY, rect.y);
    maxX = Math.max(maxX, rect.x + rect.width);
    maxY = Math.max(maxY, rect.y + rect.height);
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null;
  }

  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

export function computeBoardExportBounds(rects: ExportRect[], margin = BOARD_EXPORT_MARGIN): ExportBounds | null {
  const union = unionRects(rects);
  if (!union) return null;

  const x = Math.floor(union.x - margin);
  const y = Math.floor(union.y - margin);
  const width = Math.max(1, Math.ceil(union.width + margin * 2));
  const height = Math.max(1, Math.ceil(union.height + margin * 2));

  return { x, y, width, height };
}

export function measureNodeRects(canvasEl: HTMLElement, nodes: ExportableNode[]): ExportRect[] {
  return nodes.map((node) => {
    const nodeEl = canvasEl.querySelector(`[data-testid="node-${node.id}"]`) as HTMLElement | null;
    const width = nodeEl?.offsetWidth || node.w;
    const height = nodeEl?.offsetHeight || 120;

    return {
      x: node.x - PORT_DOT_OVERFLOW,
      y: node.y,
      width: width + PORT_DOT_OVERFLOW * 2,
      height,
    };
  });
}

export function measureEdgeRects(canvasEl: HTMLElement): ExportRect[] {
  const paths = Array.from(
    canvasEl.querySelectorAll<SVGGraphicsElement>('svg[data-testid="canvas-edges"] path:not([data-export-exclude="true"])'),
  );

  return paths.flatMap((path) => {
    try {
      const bbox = path.getBBox();
      if (bbox.width <= 0 && bbox.height <= 0) return [];
      return [{
        x: bbox.x - PORT_DOT_OVERFLOW,
        y: bbox.y - PORT_DOT_OVERFLOW,
        width: bbox.width + PORT_DOT_OVERFLOW * 2,
        height: bbox.height + PORT_DOT_OVERFLOW * 2,
      }];
    } catch {
      return [];
    }
  });
}

export function buildBoardExportFileName(boardName: string): string {
  const base = boardName
    .trim()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  return `${base || "board"}-export.png`;
}

export async function exportBoardToPng({
  canvasEl,
  nodes,
  boardName,
  theme,
  showGrid,
}: ExportBoardOptions): Promise<ExportBoardResult> {
  const bounds = computeBoardExportBounds([
    ...measureNodeRects(canvasEl, nodes),
    ...measureEdgeRects(canvasEl),
  ]);

  if (!bounds) {
    throw new Error("No hay nodos para exportar.");
  }

  const clone = canvasEl.cloneNode(true) as HTMLElement;
  const worldClone = clone.querySelector('[data-testid="board-world"]') as HTMLElement | null;
  if (!worldClone) {
    throw new Error("No se pudo preparar la capa del board para exportar.");
  }

  prepareExportClone(clone, worldClone, bounds, theme, showGrid);

  const host = document.createElement("div");
  host.style.position = "fixed";
  host.style.left = "-100000px";
  host.style.top = "0";
  host.style.width = `${bounds.width}px`;
  host.style.height = `${bounds.height}px`;
  host.style.overflow = "hidden";
  host.appendChild(clone);
  document.body.appendChild(host);

  try {
    await nextAnimationFrame();
    const blob = await toBlob(clone, {
      width: bounds.width,
      height: bounds.height,
      pixelRatio: BOARD_EXPORT_PIXEL_RATIO,
      backgroundColor: theme.bg,
      cacheBust: true,
      skipFonts: true,
      filter: (domNode) => {
        if (!(domNode instanceof HTMLElement)) return true;
        return domNode.getAttribute("data-export-exclude") !== "true";
      },
    });

    if (!blob) {
      throw new Error("No se pudo generar el PNG.");
    }

    const fileName = buildBoardExportFileName(boardName);
    downloadBlob(blob, fileName);

    return { bounds, fileName, pixelRatio: BOARD_EXPORT_PIXEL_RATIO };
  } finally {
    host.remove();
  }
}

function prepareExportClone(
  clone: HTMLElement,
  worldClone: HTMLElement,
  bounds: ExportBounds,
  theme: Theme,
  showGrid: boolean,
) {
  clone.style.width = `${bounds.width}px`;
  clone.style.height = `${bounds.height}px`;
  clone.style.minHeight = `${bounds.height}px`;
  clone.style.maxWidth = "none";
  clone.style.overflow = "hidden";
  clone.style.background = theme.bg;
  clone.style.backgroundImage = showGrid ? `radial-gradient(${theme.dot} 1.6px, transparent 1.6px)` : "none";
  clone.style.backgroundSize = showGrid ? `${BOARD_EXPORT_GRID_SIZE}px ${BOARD_EXPORT_GRID_SIZE}px` : "";
  clone.style.backgroundPosition = showGrid ? `${-bounds.x}px ${-bounds.y}px` : "";
  clone.style.color = theme.text;
  clone.style.cursor = "default";

  worldClone.style.transform = `translate(${-bounds.x}px, ${-bounds.y}px) scale(1)`;
  worldClone.style.transformOrigin = "0 0";
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function nextAnimationFrame() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}
