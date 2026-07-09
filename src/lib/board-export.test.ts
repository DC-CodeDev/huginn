// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  buildBoardExportFileName,
  computeBoardExportBounds,
  measureEdgeRects,
  measureNodeRects,
  unionRects,
} from "./board-export";

describe("board export geometry", () => {
  it("unions scattered rects and applies margin", () => {
    const bounds = computeBoardExportBounds([
      { x: 100, y: 200, width: 280, height: 120 },
      { x: 1100, y: -300, width: 360, height: 240 },
    ], 50);

    expect(bounds).toEqual({
      x: 50,
      y: -350,
      width: 1460,
      height: 720,
    });
  });

  it("returns null when there is no measurable content", () => {
    expect(unionRects([])).toBeNull();
    expect(computeBoardExportBounds([{ x: 0, y: 0, width: 0, height: 0 }])).toBeNull();
  });

  it("includes edge rects that extend outside node rects", () => {
    const bounds = computeBoardExportBounds([
      { x: 100, y: 100, width: 100, height: 100 },
      { x: -400, y: 150, width: 50, height: 20 },
    ], 10);

    expect(bounds).toEqual({
      x: -410,
      y: 90,
      width: 620,
      height: 120,
    });
  });

  it("measures node DOM size while preserving world coordinates", () => {
    const canvas = document.createElement("div");
    const node = document.createElement("div");
    node.setAttribute("data-testid", "node-n1");
    Object.defineProperty(node, "offsetWidth", { configurable: true, value: 300 });
    Object.defineProperty(node, "offsetHeight", { configurable: true, value: 150 });
    canvas.appendChild(node);

    expect(measureNodeRects(canvas, [{ id: "n1", x: 12, y: 34, w: 280 }])).toEqual([
      { x: 4, y: 34, width: 316, height: 150 },
    ]);
  });

  it("measures SVG edge bboxes and skips export-excluded paths", () => {
    const canvas = document.createElement("div");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("data-testid", "canvas-edges");

    const visible = document.createElementNS("http://www.w3.org/2000/svg", "path") as SVGGraphicsElement;
    visible.getBBox = () => ({ x: -20, y: 5, width: 100, height: 40 }) as DOMRect;

    const excluded = document.createElementNS("http://www.w3.org/2000/svg", "path") as SVGGraphicsElement;
    excluded.setAttribute("data-export-exclude", "true");
    excluded.getBBox = () => ({ x: -1000, y: -1000, width: 2000, height: 2000 }) as DOMRect;

    svg.append(visible, excluded);
    canvas.appendChild(svg);

    expect(measureEdgeRects(canvas)).toEqual([
      { x: -28, y: -3, width: 116, height: 56 },
    ]);
  });
});

describe("board export filenames", () => {
  it("sanitizes board names for png downloads", () => {
    expect(buildBoardExportFileName("  My Board: Alpha/Beta  ")).toBe("my-board-alpha-beta-export.png");
    expect(buildBoardExportFileName("Diseño estratégico")).toBe("diseno-estrategico-export.png");
    expect(buildBoardExportFileName("")).toBe("board-export.png");
  });
});
