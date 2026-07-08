// @vitest-environment node
import { describe, it, expect } from "vitest";
import { portPos, edgePath, PORT_Y0, PORT_DY } from "./geometry";
import { PORT_COLORS, type Node, type Port } from "../types";

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */

const port = (id: string, side: Port["side"], color: Port["color"]): Port => ({
  id,
  side,
  color,
  label: id,
});

// Nodo card básico con un puerto en cada lado.
const cardNode: Node = {
  id: "n1",
  x: 100,
  y: 200,
  w: 300,
  title: "Card",
  type: "card",
  tags: [],
  blocks: [],
  ports: [
    port("in", "left", PORT_COLORS[3]),
    port("out", "right", PORT_COLORS[1]),
  ],
};

// Nodo con varios puertos por lado para verificar el índice por lado (samesSide).
const stackedNode: Node = {
  id: "n2",
  x: 0,
  y: 0,
  w: 200,
  title: "Stacked",
  type: "card",
  tags: [],
  blocks: [],
  ports: [
    port("l0", "left", PORT_COLORS[0]),
    port("r0", "right", PORT_COLORS[1]),
    port("l1", "left", PORT_COLORS[2]),
  ],
};

/* ------------------------------------------------------------------ */
/*  portPos                                                            */
/* ------------------------------------------------------------------ */

describe("portPos", () => {
  it("ubica un puerto válido del lado left en x = node.x", () => {
    const pos = portPos(cardNode, "in");
    expect(pos).toEqual({
      x: 100, // node.x
      y: 256, // node.y + PORT_Y0 + 0 * PORT_DY = 200 + 56
      side: "left",
      color: PORT_COLORS[3],
    });
  });

  it("ubica un puerto del lado right en x = node.x + node.w", () => {
    const pos = portPos(cardNode, "out");
    // Misma y que el puerto left (idx 0 dentro de su lado), pero x desplazada por w.
    expect(pos).toEqual({
      x: 400, // node.x + node.w = 100 + 300
      y: 256, // node.y + PORT_Y0
      side: "right",
      color: PORT_COLORS[1],
    });
  });

  it("indexa la y según la posición dentro del mismo lado, no en el array global", () => {
    // "l1" es el 3er puerto del array pero el 2º del lado left → idx 1.
    const pos = portPos(stackedNode, "l1");
    expect(pos?.y).toBe(PORT_Y0 + PORT_DY); // 0 + 56 + 26 = 82
    expect(pos?.side).toBe("left");
  });

  it("devuelve null cuando el portId no existe en el nodo", () => {
    expect(portPos(cardNode, "no-existe")).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/*  edgePath                                                           */
/* ------------------------------------------------------------------ */

describe("edgePath", () => {
  it("genera un path recto (M … L …) cuando curved es false", () => {
    const path = edgePath(
      { x: 0, y: 0, side: "right" },
      { x: 100, y: 50, side: "left" },
      false,
    );
    expect(path).toBe("M 0 0 L 100 50");
    expect(path.startsWith("M")).toBe(true);
    expect(path).toContain("L");
    expect(path).not.toContain("C");
  });

  it("genera una curva Bézier (M … C …) cuando curved es true", () => {
    const path = edgePath(
      { x: 0, y: 0, side: "right" },
      { x: 100, y: 50, side: "left" },
      true,
    );
    // dx = max(60, |100-0|/2 = 50) = 60 → c1x = 0+60, c2x = 100-60.
    expect(path.startsWith("M 0 0")).toBe(true);
    expect(path).toContain("C");
    expect(path).toBe("M 0 0 C 60 0, 40 50, 100 50");
  });

  it("usa la mitad de la distancia como dx cuando supera el mínimo de 60", () => {
    const path = edgePath(
      { x: 0, y: 0, side: "right" },
      { x: 400, y: 0, side: "left" },
      true,
    );
    // dx = max(60, |400|/2 = 200) = 200 → c1x = 0+200, c2x = 400-200.
    expect(path).toContain("C");
    expect(path).toBe("M 0 0 C 200 0, 200 0, 400 0");
  });
});
