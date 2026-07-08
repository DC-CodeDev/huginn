/**
 * Tipos y excepciones relacionados con conflictos de versión de Boards.
 *
 * Separados de api.ts para poder importarlos sin depender de React,
 * y para facilitar tests unitarios.
 */

// ----------------------------------------------------------------------
//  VersionConflictError
// ----------------------------------------------------------------------

export type VersionConflictPayload = {
  code: "VERSION_CONFLICT";
  message: string;
  board_id: string;
  expected_version: number;
  current_version: number;
};

export class VersionConflictError extends Error {
  boardId: string;
  expectedVersion: number;
  currentVersion: number;

  constructor(payload: VersionConflictPayload) {
    super(payload.message);
    this.name = "VersionConflictError";
    this.boardId = payload.board_id;
    this.expectedVersion = payload.expected_version;
    this.currentVersion = payload.current_version;
  }
}

// ----------------------------------------------------------------------
//  BoardConflict (estado de conflicto)
// ----------------------------------------------------------------------

export type BoardConflict = {
  boardId: string;
  expectedVersion: number;
  currentVersion: number;
  message: string;
};
