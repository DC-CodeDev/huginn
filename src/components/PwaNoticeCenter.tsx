import { usePwa } from "../lib/pwa";

export function PwaNoticeCenter() {
  const {
    isOnline,
    saveStatus,
    updateAvailable,
    updateDismissed,
    updateRequiresConfirmation,
    canApplyUpdate,
    updateWarning,
    requestUpdate,
    dismissUpdate,
  } = usePwa();

  const showUpdate = updateAvailable && !updateDismissed;

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
          {!updateWarning && saveStatus === "guardado" && (
            <p className="app-notice-copy">El board ya está guardado. Podés actualizar cuando quieras.</p>
          )}
          <div className="app-notice-actions">
            <button
              type="button"
              data-testid="update-action"
              className="app-notice-btn app-notice-btn-primary"
              onClick={requestUpdate}
              disabled={!canApplyUpdate}
              title={!canApplyUpdate ? "Esperá a que termine el guardado." : undefined}
            >
              {updateRequiresConfirmation ? "Actualizar de todos modos" : "Actualizar"}
            </button>
            <button
              type="button"
              data-testid="update-later"
              className="app-notice-btn"
              onClick={dismissUpdate}
            >
              Más tarde
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
