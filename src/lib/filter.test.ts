import { describe, it, expect } from "vitest";
import { computeNodeOpacity, type FilterMode } from "./filter";

describe("computeNodeOpacity", () => {
  const tags = ["ux", "backend", "frontend"];

  /* ── Filtro cerrado ── */
  it("retorna 1 si el filtro está cerrado (filterOpen=false)", () => {
    expect(computeNodeOpacity(tags, false, ["ux"], "wide")).toBe(1);
    expect(computeNodeOpacity(tags, false, [], "strict")).toBe(1);
    expect(computeNodeOpacity(tags, false, ["nada"], "strict")).toBe(1);
  });

  /* ── Sin tags tildados ── */
  it("retorna 0.5 si el filtro está abierto pero no hay tags tildados", () => {
    expect(computeNodeOpacity(tags, true, [], "wide")).toBe(0.5);
    expect(computeNodeOpacity(tags, true, [], "strict")).toBe(0.5);
  });

  /* ── Modo Amplio ── */
  it("modo Amplio: nodo con al menos un tag tildado → opacidad 1", () => {
    expect(computeNodeOpacity(tags, true, ["ux"], "wide")).toBe(1);
    expect(computeNodeOpacity(tags, true, ["backend", "nada"], "wide")).toBe(1);
    expect(computeNodeOpacity(tags, true, ["UX"], "wide")).toBe(1); // case-insensitive
  });

  it("modo Amplio: nodo sin ningún tag tildado → opacidad 0.5", () => {
    expect(computeNodeOpacity(tags, true, ["nada"], "wide")).toBe(0.5);
    expect(computeNodeOpacity(tags, true, ["foo", "bar"], "wide")).toBe(0.5);
  });

  it("modo Amplio: nodo sin tags → opacidad 0.5 si hay tags tildados", () => {
    expect(computeNodeOpacity([], true, ["ux"], "wide")).toBe(0.5);
  });

  /* ── Modo Estricto ── */
  it("modo Estricto: nodo con todos los tags tildados → opacidad 1", () => {
    expect(computeNodeOpacity(tags, true, ["ux"], "strict")).toBe(1);
    expect(computeNodeOpacity(tags, true, ["ux", "backend"], "strict")).toBe(1);
    expect(computeNodeOpacity(tags, true, ["ux", "backend", "frontend"], "strict")).toBe(1);
    expect(computeNodeOpacity(tags, true, ["UX", "BACKEND"], "strict")).toBe(1); // case-insensitive
  });

  it("modo Estricto: nodo con solo algunos tags tildados → opacidad 0.5", () => {
    expect(computeNodeOpacity(tags, true, ["ux", "nada"], "strict")).toBe(0.5);
    expect(computeNodeOpacity(tags, true, ["ux", "backend", "nada"], "strict")).toBe(0.5);
  });

  it("modo Estricto: nodo sin ningún tag tildado → opacidad 0.5", () => {
    expect(computeNodeOpacity(tags, true, ["nada"], "strict")).toBe(0.5);
  });

  it("modo Estricto: nodo sin tags → opacidad 0.5 si hay tags tildados", () => {
    expect(computeNodeOpacity([], true, ["ux"], "strict")).toBe(0.5);
  });

  /* ── Edge cases ── */
  it("nodo sin tags, sin tags tildados, filtro abierto → opacidad 0.5", () => {
    expect(computeNodeOpacity([], true, [], "wide")).toBe(0.5);
    expect(computeNodeOpacity([], true, [], "strict")).toBe(0.5);
  });

  it("comparación es case-insensitive", () => {
    expect(computeNodeOpacity(["UX"], true, ["ux"], "wide")).toBe(1);
    expect(computeNodeOpacity(["ux"], true, ["UX"], "wide")).toBe(1);
    expect(computeNodeOpacity(["Ux"], true, ["uX"], "strict")).toBe(1);
  });
});
