/* ------------------------------------------------------------------ */
/*  Lógica de filtro visual por tags                                  */
/* ------------------------------------------------------------------ */

export type FilterMode = "wide" | "strict";

/**
 * Determina la opacidad de un nodo según el estado del filtro.
 *
 * - Si el filtro está cerrado: 1 (sin efecto).
 * - Si el filtro está abierto pero no hay tags tildados: 0.75.
 * - Modo Amplio ("wide"): opacidad 1 si el nodo tiene AL MENOS UNO de los tags tildados.
 * - Modo Estricto ("strict"): opacidad 1 solo si el nodo tiene TODOS los tags tildados.
 * - En cualquier otro caso: 0.75.
 */
export function computeNodeOpacity(
  nodeTags: string[],
  filterOpen: boolean,
  filterTags: string[],
  filterMode: FilterMode,
): number {
  if (!filterOpen) return 1;
  if (filterTags.length === 0) return 0.5;

  const lowerNodeTags = nodeTags.map((t) => t.toLowerCase());

  if (filterMode === "wide") {
    return filterTags.some((t) => lowerNodeTags.includes(t.toLowerCase())) ? 1 : 0.5;
  }

  // strict
  return filterTags.every((t) => lowerNodeTags.includes(t.toLowerCase())) ? 1 : 0.5;
}
