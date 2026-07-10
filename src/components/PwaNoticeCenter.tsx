import { LoaderCircle } from "lucide-react";
import { usePwa } from "../lib/pwa";
import { PressableButton } from "./PressableButton";

export function PwaNoticeCenter() {
  const {
    isOnline,
    saveStatus,
    updateAvailable,
    updateDismissed,
    updateState,
    updateError,
    updateRequiresConfirmation,
    canApplyUpdate,
    updateWarning,
    requestUpdate,
    dismissUpdate,
  } = usePwa();

  const showUpdate = updateAvailable && !updateDismissed;
  const isUpdating = updateState === "updating";
  const hasUpdateError = updateState === "error" && updateError;

  return (
    <div className="app-notice-stack">
      {!isOnline && (
        <div
          data-testid="offline-notice"
          className="app-notice"
          style={{
            background: "var(--card)",
            border: "1px solid var(--card-border)",
            color: "var(--text)",
          }}
        >
          <p className="app-notice-title">Sin conexión</p>
          <p className="app-notice-copy">
            Huginn necesita red para cargar y guardar tus boards.
          </p>
          <p className="app-notice-copy app-notice-copy-subtle">
            <code>navigator.onLine</code> no garantiza que el backend esté disponible.
          </p>
        </div>
      )}

      {showUpdate && (
        <div
          data-testid="update-notice"
          className="app-notice"
          style={{
            background: "var(--card)",
            border: "1px solid var(--card-border)",
            color: "var(--text)",
          }}
        >
          <p className="app-notice-title">Hay una nueva versión de Huginn disponible.</p>
          {updateWarning && (
            <p className="app-notice-copy">
              {updateWarning}
            </p>
          )}
          {isUpdating && (
            <p className="app-notice-copy">
              Activando la nueva versión. La página se recargará cuando esté lista.
            </p>
          )}
          {hasUpdateError && (
            <p className="app-notice-copy" role="alert">
              {updateError}
            </p>
          )}
          {!updateWarning && updateState === "idle" && saveStatus === "guardado" && (
            <p className="app-notice-copy">El board ya está guardado. Podés actualizar cuando quieras.</p>
          )}
          <div className="app-notice-actions">
            <PressableButton
              type="button"
              data-testid="update-action"
              className="app-notice-btn app-notice-btn-primary"
              onClick={requestUpdate}
              disabled={!canApplyUpdate}
              title={!canApplyUpdate && !isUpdating ? "Esperá a que termine el guardado." : undefined}
            >
              {isUpdating && <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />}
              {isUpdating
                ? "Actualizando..."
                : hasUpdateError
                  ? "Reintentar"
                  : updateRequiresConfirmation
                    ? "Actualizar de todos modos"
                    : "Actualizar"}
            </PressableButton>
            <PressableButton
              type="button"
              data-testid="update-later"
              className="app-notice-btn"
              onClick={dismissUpdate}
              disabled={isUpdating}
            >
              Más tarde
            </PressableButton>
          </div>
        </div>
      )}
    </div>
  );
}
