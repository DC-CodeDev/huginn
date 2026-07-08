/**
 * Operaciones con manejo de versiones y conflictos para Folders/Studios.
 *
 * Extraídas de FolderView.tsx y StudioView.tsx para hacerlas testeables.
 */

import { api } from "../api";
import { VersionConflictError } from "./board-conflict";
import type { BoardSummary } from "../types";

// ----------------------------------------------------------------------
//  Rename
// ----------------------------------------------------------------------

export type RenameResult =
  | { ok: true; board: BoardSummary }
  | { ok: false; reason: "no-version" }
  | { ok: false; reason: "conflict"; error: VersionConflictError }
  | { ok: false; reason: "error"; error: Error };

export async function renameBoard(
  boardId: string,
  newName: string,
  boards: BoardSummary[] | null | undefined,
): Promise<RenameResult> {
  const board = boards?.find((b) => b.id === boardId);
  if (!board || board.version == null) {
    return { ok: false, reason: "no-version" };
  }
  try {
    const result = await api.renameBoard(boardId, newName.trim(), board.version);
    return {
      ok: true,
      board: { ...board, name: result.name, version: result.version },
    };
  } catch (e) {
    if (e instanceof VersionConflictError) {
      return { ok: false, reason: "conflict", error: e };
    }
    return { ok: false, reason: "error", error: e instanceof Error ? e : new Error(String(e)) };
  }
}

// ----------------------------------------------------------------------
//  Delete
// ----------------------------------------------------------------------

export type DeleteResult =
  | { ok: true }
  | { ok: false; reason: "no-version" }
  | { ok: false; reason: "conflict"; error: VersionConflictError }
  | { ok: false; reason: "error"; error: Error };

export async function deleteBoard(
  boardId: string,
  boards: BoardSummary[] | null | undefined,
): Promise<DeleteResult> {
  const board = boards?.find((b) => b.id === boardId);
  if (!board || board.version == null) {
    return { ok: false, reason: "no-version" };
  }
  try {
    await api.deleteBoard(boardId, board.version);
    return { ok: true };
  } catch (e) {
    if (e instanceof VersionConflictError) {
      return { ok: false, reason: "conflict", error: e };
    }
    return { ok: false, reason: "error", error: e instanceof Error ? e : new Error(String(e)) };
  }
}
