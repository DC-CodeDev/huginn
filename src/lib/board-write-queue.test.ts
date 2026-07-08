import { describe, it, expect, beforeEach } from "vitest";
import { createWriteQueue } from "./board-write-queue";
import { VersionConflictError } from "./board-conflict";

describe("createWriteQueue", () => {
  let version: number | null;
  let conflict: { currentVersion: number } | null;
  let boardId: string;
  let queue: ReturnType<typeof createWriteQueue>;

  beforeEach(() => {
    version = 1;
    conflict = null;
    boardId = "board-1";
    queue = createWriteQueue(
      () => version,
      () => conflict,
      () => boardId,
    );
  });

  // ------------------------------------------------------------------
  // Escrituras secuenciales
  // ------------------------------------------------------------------

  it("1. encola dos escrituras y la segunda no comienza antes de que termine la primera", async () => {
    const order: string[] = [];

    const p1 = queue.enqueue(async (v) => {
      order.push("start-1");
      await new Promise((r) => setTimeout(r, 10));
      order.push("end-1");
      return v;
    });

    const p2 = queue.enqueue(async (v) => {
      order.push("start-2");
      order.push("end-2");
      return v;
    });

    await Promise.all([p1, p2]);
    expect(order).toEqual(["start-1", "end-1", "start-2", "end-2"]);
  });

  it("2. nunca hay más de una escritura activa", async () => {
    let active = 0;
    let maxActive = 0;

    const p1 = queue.enqueue(async () => {
      active++;
      maxActive = Math.max(maxActive, active);
      await new Promise((r) => setTimeout(r, 5));
      active--;
    });

    const p2 = queue.enqueue(async () => {
      active++;
      maxActive = Math.max(maxActive, active);
      await new Promise((r) => setTimeout(r, 5));
      active--;
    });

    await Promise.all([p1, p2]);
    expect(maxActive).toBe(1);
  });

  it("3. el orden de ejecución coincide con el orden de encolado", async () => {
    const values: number[] = [];

    await Promise.all([
      queue.enqueue(async () => { values.push(1); }),
      queue.enqueue(async () => { values.push(2); }),
      queue.enqueue(async () => { values.push(3); }),
    ]);

    expect(values).toEqual([1, 2, 3]);
  });

  // ------------------------------------------------------------------
  // Versión actualizada entre escrituras
  // ------------------------------------------------------------------

  it("4. primera escritura comienza con versión 1, segunda con versión 2", async () => {
    const received: number[] = [];

    const p1 = queue.enqueue(async (v) => {
      received.push(v); // espera 1
      return "ok";
    });

    const p2 = queue.enqueue(async (v) => {
      received.push(v); // espera 2
      return "ok";
    });

    // Simular que el backend avanzó la versión después de la primera
    p1.then(() => { version = 2; });
    await Promise.all([p1, p2]);
    expect(received).toEqual([1, 2]);
  });

  it("5. la segunda escritura no usa la versión capturada al momento de encolarse", async () => {
    const versions: number[] = [];

    queue.enqueue(async (v) => {
      versions.push(v);
      version = 5; // el backend avanzó a 5
      return "ok";
    });

    await queue.enqueue(async (v) => {
      versions.push(v); // debe ser 5, no la versión 1 que estaba al encolar
      return "ok";
    });

    expect(versions).toEqual([1, 5]);
  });

  // ------------------------------------------------------------------
  // Error normal — la cadena no queda bloqueada
  // ------------------------------------------------------------------

  it("6. primera escritura falla con error normal, segunda se ejecuta", async () => {
    const executed: string[] = [];

    const p1 = queue.enqueue(async () => {
      executed.push("first-start");
      throw new Error("normal error");
    });

    const p2 = queue.enqueue(async () => {
      executed.push("second");
      return "ok";
    });

    await expect(p1).rejects.toThrow("normal error");
    await expect(p2).resolves.toBe("ok");
    expect(executed).toEqual(["first-start", "second"]);
  });

  it("7. la cadena no queda permanentemente rechazada tras un error", async () => {
    // Encolar una que falla
    await expect(
      queue.enqueue(async () => { throw new Error("fail"); }),
    ).rejects.toThrow("fail");

    // La siguiente debe poder ejecutarse
    const result = await queue.enqueue(async (v) => v);
    expect(result).toBe(1);
  });

  it("8. no existe retry automático de la primera que falló", async () => {
    let calls = 0;

    await expect(
      queue.enqueue(async () => { calls++; throw new Error("fail"); }),
    ).rejects.toThrow("fail");

    expect(calls).toBe(1); // solo un intento
  });

  // ------------------------------------------------------------------
  // Conflicto — bloquea escrituras
  // ------------------------------------------------------------------

  it("9. una escritura lanza VersionConflictError durante la ejecución", async () => {
    const p = queue.enqueue(async () => {
      throw new VersionConflictError({
        code: "VERSION_CONFLICT",
        message: "El board fue modificado por otro cliente.",
        board_id: "board-1",
        expected_version: 1,
        current_version: 2,
      });
    });

    await expect(p).rejects.toThrow(VersionConflictError);
  });

  it("10. si hay conflicto, las siguientes escrituras no se ejecutan", async () => {
    conflict = { currentVersion: 3 };
    let executed = false;

    await expect(
      queue.enqueue(async () => { executed = true; }),
    ).rejects.toThrow(VersionConflictError);

    expect(executed).toBe(false);
  });

  it("11. la operación conflictiva no actualiza la versión local", async () => {
    // El conflicto se produce sin modificar version
    conflict = { currentVersion: 5 };

    await expect(
      queue.enqueue(async (v) => v),
    ).rejects.toThrow(VersionConflictError);

    expect(version).toBe(1); // sin cambios
  });

  it("12. no se reintenta la operación conflictiva", async () => {
    conflict = { currentVersion: 3 };
    let calls = 0;

    await expect(
      queue.enqueue(async () => { calls++; }),
    ).rejects.toThrow(VersionConflictError);

    expect(calls).toBe(0); // ni siquiera se ejecutó
  });

  // ------------------------------------------------------------------
  // reset
  // ------------------------------------------------------------------

  it("13. reset reinicia la cadena", async () => {
    queue.enqueue(async () => { throw new Error("boom"); });
    queue.reset();

    // Después de reset, la cadena está limpia
    const result = await queue.enqueue(async (v) => v);
    expect(result).toBe(1);
  });

  it("14. reset rechaza operaciones encoladas previas (generación)", async () => {
    let resolved = false;

    const p = queue.enqueue(async () => {
      await new Promise((r) => setTimeout(r, 5));
      resolved = true;
      return "ok";
    });

    queue.reset();

    // La operación ya encolada se rechaza porque la generación cambió
    await expect(p).rejects.toThrow("Write queue was reset");
    expect(resolved).toBe(false);
  });

  // ------------------------------------------------------------------
  // Versión null
  // ------------------------------------------------------------------

  it("15. enqueue lanza error si la versión es null", async () => {
    version = null;
    await expect(
      queue.enqueue(async (v) => v),
    ).rejects.toThrow("Board version is not available");
  });

  // ------------------------------------------------------------------
  // Generación — reset invalida operaciones pendientes
  // ------------------------------------------------------------------

  it("16. reset + incremento de generación evita que operaciones viejas se ejecuten", async () => {
    let executed = false;

    const oldOp = queue.enqueue(async (v) => {
      // Esta operación se encoló antes del reset, pero se ejecuta después
      executed = true;
      return v;
    });

    queue.reset();

    // La operación vieja debe rechazar por generación distinta
    await expect(oldOp).rejects.toThrow("Write queue was reset");
    expect(executed).toBe(false);
  });

  it("17. operación encolada después de reset sí se ejecuta", async () => {
    queue.reset();

    const result = await queue.enqueue(async (v) => v + 10);
    expect(result).toBe(11); // version=1 + 10
  });

  it("18. reset múltiple no deja fugas de operaciones antiguas", async () => {
    const results: string[] = [];

    queue.enqueue(async (v) => { results.push("A"); return v; });
    queue.reset();

    queue.enqueue(async (v) => { results.push("B"); return v; });
    queue.reset();

    await queue.enqueue(async (v) => { results.push("C"); return v; });

    expect(results).toEqual(["C"]);
  });
});
