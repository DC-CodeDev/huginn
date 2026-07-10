import { useEffect, useState, type ReactNode } from "react";
import { useModalBackdrop, useModalPanel } from "bylgja";

interface AnimatedModalProps {
  /**
   * Controla la visibilidad. Se usa `show` (y no `open`) para ser consistente
   * con el resto de la integración de bylgja en Huginn (useFadeScale en
   * FilterPanel/ProfileMenu) y con la API de los hooks de bylgja.
   */
  show: boolean;
  /** Se dispara al cerrar por click en el backdrop o por tecla Escape. */
  onClose: () => void;
  /** Contenido del panel. En la parte B, cada modal pasa su panel ya estilizado. */
  children: ReactNode;
  /** Clases extra para el wrapper animado del panel. */
  className?: string;
  /** Clases extra para el backdrop (color/opacidad se controlan aparte). */
  backdropClassName?: string;
  /**
   * Clases extra para la capa interactiva que centra el panel. Útil para el
   * padding de safe-area (`app-modal-backdrop`) que varios modales de Huginn
   * aplicaban antes sobre su backdrop para no pegar el panel a los bordes.
   */
  overlayClassName?: string;
  /** Cierra al presionar Escape mientras está visible. Default: true. */
  closeOnEscape?: boolean;
  /**
   * Clase de z-index aplicada al backdrop y a la capa interactiva. Los modales
   * de Huginn usan mayormente z-50; TagsModal usa z-40. Default: "z-50".
   */
  zIndexClassName?: string;
}

/**
 * Envuelve el patrón compartido de "backdrop oscuro + panel centrado" con
 * animación de entrada/salida vía Presence de bylgja (useModalBackdrop +
 * useModalPanel). Pensado para que los siete modales existentes de Huginn lo
 * consuman en la parte B del paso 4.
 *
 * Detalles de diseño relevantes:
 * - El backdrop y el panel se renderizan como HERMANOS, no anidados. El CSS de
 *   `bylgja-modal-backdrop` topea la opacidad del elemento en
 *   `--bylgja-backdrop-opacity` (0.48 por defecto); si el panel fuera hijo del
 *   backdrop heredaría ese tope y se vería lavado. Por eso el backdrop es solo
 *   la capa oscura y el panel vive en su propia capa.
 * - `render()` de los hooks sólo acepta `children` (no `style` ni handlers), así
 *   que el click-afuera y el centrado del panel viven en una capa propia
 *   (`overlay`) que es hermana del backdrop y queda por encima de él.
 * - Esa capa se renderiza SIEMPRE (no se gatea su montaje). Así `panel.render`
 *   se llama desde el primer render, y Presence nace en estado `show=false`
 *   (renderizando `null`) para poder animar la transición real a `show=true`.
 *   Si en cambio retrasáramos el primer montaje del panel hasta que `show` ya
 *   es `true`, Presence nacería directamente en su valor final y la ENTRADA no
 *   animaría (aparecería de golpe); Presence ya sabe mantenerse montado durante
 *   la salida y desmontarse solo cuando el spring de salida asienta.
 * - Separamos dos preocupaciones que antes estaban mezcladas en un `mounted`:
 *   "el panel debe existir en el DOM" (lo decide Presence) vs. "la capa debe
 *   capturar clicks" (sólo mientras está o estuvo visible). Lo segundo se
 *   resuelve con `pointer-events`, apagándolo vía `onSettled` cuando la salida
 *   asienta, sin afectar el ciclo de montaje del panel.
 *
 * NOTA DE TIMING (a tener en cuenta en el futuro, no se resuelve acá):
 * La duración de la animación de salida del panel (SPRING_GENTLE que usa
 * useModalPanel internamente) determina cuánto tiempo real tiene cualquier
 * interacción interna —por ejemplo el spring de un botón pressable que dispara
 * el cierre— para terminar su propia animación antes de que el contenido se
 * desmonte. Si en el futuro se quiere coordinar mejor ese timing (que el botón
 * de confirmar termine su feedback de presión antes de que el modal cierre),
 * este es el punto donde habría que exponer/ajustar el springConfig de salida.
 */
export function AnimatedModal({
  show,
  onClose,
  children,
  className,
  backdropClassName,
  overlayClassName,
  closeOnEscape = true,
  zIndexClassName = "z-50",
}: AnimatedModalProps) {
  const backdrop = useModalBackdrop({
    show,
    className: `fixed inset-0 ${zIndexClassName} bg-black${backdropClassName ? ` ${backdropClassName}` : ""}`,
  });
  const panel = useModalPanel({
    show,
    className,
    // Cuando la salida asienta y ya no estamos visibles, la capa deja de
    // capturar clicks (pointer-events) para no bloquear con la pantalla vacía.
    // No desmonta el panel: de eso se encarga Presence por su cuenta.
    onSettled: () => {
      if (!show) setCapturing(false);
    },
  });

  // La capa captura clicks mientras el modal está o estuvo visible (incluida la
  // animación de salida); se apaga sólo cuando esa salida asienta.
  const [capturing, setCapturing] = useState(show);
  useEffect(() => {
    if (show) setCapturing(true);
  }, [show]);
  const capturesClicks = show || capturing;

  // Escape cierra mientras está visible (patrón que hoy tiene TagsModal).
  useEffect(() => {
    if (!show || !closeOnEscape) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [show, closeOnEscape, onClose]);

  return (
    <>
      {backdrop.render()}
      <div
        data-export-exclude="true"
        className={`fixed inset-0 ${zIndexClassName} flex items-center justify-center${capturesClicks ? "" : " pointer-events-none"}${overlayClassName ? ` ${overlayClassName}` : ""}`}
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        {panel.render(children)}
      </div>
    </>
  );
}
