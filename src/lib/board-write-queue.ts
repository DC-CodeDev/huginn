/**
 * Cola de escrituras serializadas para un Board.
 *
 * Garantiza que solo una escritura esté activa a la vez, leyendo la versión
 * más reciente del board en el momento de ejecución (no al encolar).
 *
 * Uso en producción:
 *   const queue = createWriteQueue(() => versionRef.current, () => conflictRef.current, () => boardId)
 *   const result = await queue.enqueue(async (version) => api.saveState(id, { ... }))
 */

import { VersionConflictError } from "./board-conflict";

// ----------------------------------------------------------------------
//  WriteQueue
// ----------------------------------------------------------------------

export interface WriteQueue {
  /**
   * Encola una operación de escritura.
   *
   * @param operation Recibe la versión actual del board al momento de ejecutarse.
   *                  Nunca recibe null — si no hay versión, la cola lanza Error.
   * @returns El resultado de la operación.
   */
  enqueue: <T>(operation: (version: number) => Promise<T>) => Promise<T>;

  /**
   * Reinicia la cola, cancelando el efecto de operaciones previas.
   * No rechaza promesas pendientes (pasan a segundo plano silenciosamente).
   */
  reset: () => void;
}

// ----------------------------------------------------------------------
//  createWriteQueue
// ----------------------------------------------------------------------

/**
 * Crea una cola de escrituras serializadas.
 *
 * @param getVersion  Función que retorna la versión actual del board (o null si no cargada).
 * @param getConflict Función que retorna el conflicto actual (o null si no hay conflicto).
 * @param getBoardId  Función que retorna el ID del board activo.
 */
export function createWriteQueue(
  getVersion: () => number | null,
  getConflict: () => { currentVersion: number } | null,
  getBoardId: () => string,
): WriteQueue {
  let chain: Promise<unknown> = Promise.resolve();
  let generation = 0;

  const enqueue = <T,>(operation: (version: number) => Promise<T>): Promise<T> => {
    const capturedGeneration = generation;
    const queued = chain.then(async () => {
      if (capturedGeneration !== generation) {
        throw new Error("Write queue was reset");
      }
      const version = getVersion();
      if (version == null) {
        throw new Error("Board version is not available");
      }
      const conflict = getConflict();
      if (conflict) {
        throw new VersionConflictError({
          code: "VERSION_CONFLICT",
          message: "El board está en estado de conflicto",
          board_id: getBoardId(),
          expected_version: version,
          current_version: conflict.currentVersion,
        });
      }
      return operation(version);
    });

    // Si falla, la cadena continúa (no bloquea permanentemente)
    chain = queued.catch(() => undefined);
    return queued;
  };

  const reset = (): void => {
    generation++;
    chain = Promise.resolve();
  };

  return { enqueue, reset };
}
