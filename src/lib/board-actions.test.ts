import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { renameBoard, deleteBoard } from "./board-actions";
import { VersionConflictError } from "./board-conflict";
import type { BoardSummary } from "../types";

const fetchMock = vi.fn();

function okResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

function conflictResponse(): Response {
  return new Response(JSON.stringify({
    detail: {
      code: "VERSION_CONFLICT",
      message: "Conflicto de versión",
      board_id: "board-1",
      expected_version: 1,
      current_version: 3,
    },
  }), { status: 409, headers: { "Content-Type": "application/json" } });
}

const BOARDS: BoardSummary[] = [
  { id: "b1", name: "Board A", version: 1, created_at: "", updated_at: "", node_count: 0, edge_count: 0 },
  { id: "b2", name: "Board B", version: 5, created_at: "", updated_at: "", node_count: 0, edge_count: 0 },
];

describe("renameBoard", () => {
  beforeEach(() => { vi.stubGlobal("fetch", fetchMock); fetchMock.mockReset(); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("1. no ejecuta rename cuando falta versión", async () => {
    const result = await renameBoard("missing", "New", BOARDS);
    expect(result).toEqual({ ok: false, reason: "no-version" });
  });

  it("2. no ejecuta rename con boards null", async () => {
    const result = await renameBoard("b1", "New", null);
    expect(result).toEqual({ ok: false, reason: "no-version" });
  });

  it("3. rename exitoso actualiza versión", async () => {
    fetchMock.mockResolvedValue(okResponse({ id: "b1", name: "Board A Renamed", version: 2 }));
    const result = await renameBoard("b1", "Board A Renamed", BOARDS);
    expect(result).toEqual({
      ok: true,
      board: expect.objectContaining({ id: "b1", name: "Board A Renamed", version: 2 }),
    });
    // Verificar que se usó la versión del board
    const callBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? "{}"));
    expect(callBody.expected_version).toBe(1);
  });

  it("4. conflicto en rename propaga VersionConflictError", async () => {
    fetchMock.mockResolvedValue(conflictResponse());
    const result = await renameBoard("b2", "Board B Renamed", BOARDS);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("conflict");
      if (result.reason === "conflict") {
        expect(result.error.boardId).toBe("board-1");
        expect(result.error.expectedVersion).toBe(1);
        expect(result.error.currentVersion).toBe(3);
      }
    }
  });

  it("5. error de red en rename retorna error", async () => {
    fetchMock.mockRejectedValue(new Error("Network error"));
    const result = await renameBoard("b1", "New", BOARDS);
    expect(result).toEqual({ ok: false, reason: "error", error: expect.any(Error) });
  });
});

describe("deleteBoard", () => {
  beforeEach(() => { vi.stubGlobal("fetch", fetchMock); fetchMock.mockReset(); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("1. no ejecuta delete cuando falta versión", async () => {
    const result = await deleteBoard("missing", BOARDS);
    expect(result).toEqual({ ok: false, reason: "no-version" });
  });

  it("2. no ejecuta delete con boards null", async () => {
    const result = await deleteBoard("b1", null);
    expect(result).toEqual({ ok: false, reason: "no-version" });
  });

  it("3. delete exitoso retorna ok", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const result = await deleteBoard("b1", BOARDS);
    expect(result).toEqual({ ok: true });
    // Verificar que se pasó expected_version
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("expected_version=1");
  });

  it("4. conflicto en delete propaga VersionConflictError", async () => {
    fetchMock.mockResolvedValue(conflictResponse());
    const result = await deleteBoard("b2", BOARDS);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reason).toBe("conflict");
    }
  });

  it("5. error de red en delete retorna error", async () => {
    fetchMock.mockRejectedValue(new Error("Network error"));
    const result = await deleteBoard("b1", BOARDS);
    expect(result).toEqual({ ok: false, reason: "error", error: expect.any(Error) });
  });
});
