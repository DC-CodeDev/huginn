import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const swSource = readFileSync(resolve(__dirname, "sw.ts"), "utf-8");

describe("service worker source", () => {
  it("mantiene NetworkOnly para /api y para escrituras", () => {
    expect(swSource).toMatch(/url\.pathname\.startsWith\("\/api\/"\)/);
    expect(swSource).toMatch(/new NetworkOnly\(\)/);
    expect(swSource).toMatch(/WRITE_METHODS = new Set\(\["POST", "PUT", "PATCH", "DELETE"\]\)/);
  });

  it("usa fallback offline sin prometer edición offline", () => {
    expect(swSource).toMatch(/request\.mode === "navigate"/);
    expect(swSource).toMatch(/matchPrecache\(OFFLINE_URL\)/);
    expect(swSource).not.toMatch(/indexeddb/i);
  });

  it("no implementa background sync ni activación automática", () => {
    expect(swSource).not.toMatch(/BackgroundSync/i);
    expect(swSource).not.toMatch(/skipWaiting/i);
    expect(swSource).not.toMatch(/clients\.claim/i);
  });
});
