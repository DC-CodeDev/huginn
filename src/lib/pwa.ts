import { Workbox } from "workbox-window";
import { createContext, createElement, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { SaveStatus } from "../api";
import { useOnlineStatus } from "./connectivity";

export const PWA_UPDATE_TIMEOUT_MS = 10_000;

type PwaRegistrationOptions = {
  isProduction?: boolean;
  navigatorRef?: Pick<Navigator, "serviceWorker"> | undefined;
  onWaiting?: (workbox: Workbox, registration: ServiceWorkerRegistration | undefined) => void;
  onRegistered?: (registration: ServiceWorkerRegistration | undefined) => void;
  onError?: (error: unknown) => void;
  logger?: Pick<Console, "error" | "info">;
};

type PwaRegistrationHandle = {
  workbox: Workbox;
  registerPromise: Promise<ServiceWorkerRegistration | undefined>;
};

type ControllerChangeTarget = Pick<ServiceWorkerContainer, "addEventListener" | "removeEventListener"> | undefined;
export type PwaUpdateState = "idle" | "updating" | "error";

type PwaRuntimeOptions = {
  isProduction?: boolean;
  navigatorRef?: Pick<Navigator, "serviceWorker"> | undefined;
  reload?: () => void;
};

type PwaContextValue = {
  isOnline: boolean;
  saveStatus: SaveStatus | null;
  updateAvailable: boolean;
  updateDismissed: boolean;
  updateState: PwaUpdateState;
  updateError: string | null;
  updateRequiresConfirmation: boolean;
  canApplyUpdate: boolean;
  updateWarning: string | null;
  setSaveStatus: (status: SaveStatus | null) => void;
  dismissUpdate: () => void;
  requestUpdate: () => void;
};

const PwaContext = createContext<PwaContextValue | null>(null);

export function registerAppServiceWorker(
  options: PwaRegistrationOptions = {},
): PwaRegistrationHandle | null {
  const isProduction = options.isProduction ?? import.meta.env.PROD;
  const navigatorRef = options.navigatorRef ?? globalThis.navigator;
  const logger = options.logger ?? console;

  if (!isProduction || !navigatorRef?.serviceWorker) {
    return null;
  }

  const workbox = new Workbox("/sw.js", { scope: "/" });
  let latestRegistration: ServiceWorkerRegistration | undefined;

  workbox.addEventListener("waiting", () => {
    logger.info("Nuevo service worker instalado y esperando activación.");
    options.onWaiting?.(workbox, latestRegistration);
  });

  const registerPromise = workbox.register();
  registerPromise
    .then((registration) => {
      latestRegistration = registration;
      options.onRegistered?.(registration);
      return registration;
    })
    .catch((error) => {
      logger.error("No se pudo registrar el service worker.", error);
      options.onError?.(error);
    });

  return { workbox, registerPromise };
}

export function getUpdateWarning(saveStatus: SaveStatus | null): string | null {
  if (saveStatus === "guardando") {
    return "Esperá a que el board termine de guardar antes de actualizar.";
  }
  if (saveStatus === "error") {
    return "Hay un error de guardado. Recargar ahora puede perder cambios recientes.";
  }
  if (saveStatus === "conflicto") {
    return "Hay un conflicto de versión. Resolvelo antes de actualizar.";
  }
  return null;
}

export function canApplyUpdate(saveStatus: SaveStatus | null): boolean {
  return saveStatus !== "guardando" && saveStatus !== "conflicto";
}

export function resolveUpdateIntent(
  saveStatus: SaveStatus | null,
  needsConfirmation: boolean,
): "blocked" | "confirm" | "apply" {
  if (saveStatus === "guardando" || saveStatus === "conflicto") {
    return "blocked";
  }
  if (saveStatus === "error" && !needsConfirmation) {
    return "confirm";
  }
  return "apply";
}

export function subscribeToControllerChange(
  target: ControllerChangeTarget,
  onChange: () => void,
): () => void {
  if (!target) {
    return () => {};
  }
  target.addEventListener("controllerchange", onChange);
  return () => target.removeEventListener("controllerchange", onChange);
}

export function PwaProvider({ children, runtime }: { children: ReactNode; runtime?: PwaRuntimeOptions }) {
  const isOnline = useOnlineStatus();
  const isProduction = runtime?.isProduction ?? import.meta.env.PROD;
  const serviceWorkerTarget = runtime?.navigatorRef?.serviceWorker ?? globalThis.navigator?.serviceWorker;
  const reloadRef = useRef<() => void>(() => window.location.reload());
  reloadRef.current = runtime?.reload ?? (() => window.location.reload());
  const [saveStatus, setSaveStatus] = useState<SaveStatus | null>(null);
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const [updateState, setUpdateState] = useState<PwaUpdateState>("idle");
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [updateRequiresConfirmation, setUpdateRequiresConfirmation] = useState(false);
  const workboxRef = useRef<Workbox | null>(null);
  const shouldReloadOnControllerChange = useRef(false);
  const hasReloadedForUpdate = useRef(false);
  const updateTimeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const clearUpdateTimeout = () => {
    if (updateTimeoutRef.current) {
      window.clearTimeout(updateTimeoutRef.current);
      updateTimeoutRef.current = null;
    }
  };

  const failUpdate = (message: string) => {
    clearUpdateTimeout();
    shouldReloadOnControllerChange.current = false;
    setUpdateState("error");
    setUpdateError(message);
  };

  useEffect(() => {
    if (!serviceWorkerTarget || !isProduction) {
      return;
    }

    const handleControllerChange = () => {
      if (shouldReloadOnControllerChange.current && !hasReloadedForUpdate.current) {
        hasReloadedForUpdate.current = true;
        clearUpdateTimeout();
        reloadRef.current();
      }
    };

    return subscribeToControllerChange(serviceWorkerTarget, handleControllerChange);
  }, [isProduction, serviceWorkerTarget]);

  useEffect(() => {
    const registration = registerAppServiceWorker({
      isProduction,
      navigatorRef: runtime?.navigatorRef,
      onWaiting: (workbox) => {
        workboxRef.current = workbox;
        setUpdateAvailable(true);
        setUpdateDismissed(false);
        setUpdateState("idle");
        setUpdateError(null);
      },
    });

    workboxRef.current = registration?.workbox ?? null;
  }, [isProduction, runtime?.navigatorRef]);

  useEffect(() => () => clearUpdateTimeout(), []);

  const value = useMemo<PwaContextValue>(() => ({
    isOnline,
    saveStatus,
    updateAvailable,
    updateDismissed,
    updateState,
    updateError,
    updateRequiresConfirmation,
    canApplyUpdate: canApplyUpdate(saveStatus) && updateState !== "updating",
    updateWarning: getUpdateWarning(saveStatus),
    setSaveStatus,
    dismissUpdate: () => {
      if (updateState === "updating") {
        return;
      }
      setUpdateDismissed(true);
      setUpdateRequiresConfirmation(false);
    },
    requestUpdate: () => {
      if (updateState === "updating") {
        return;
      }
      if (!workboxRef.current) {
        failUpdate("No se pudo iniciar la actualización. Reintentá en unos segundos.");
        return;
      }

      const intent = resolveUpdateIntent(saveStatus, updateRequiresConfirmation);
      if (intent === "blocked") {
        return;
      }
      if (intent === "confirm") {
        setUpdateRequiresConfirmation(true);
        return;
      }

      shouldReloadOnControllerChange.current = true;
      hasReloadedForUpdate.current = false;
      setUpdateRequiresConfirmation(false);
      setUpdateState("updating");
      setUpdateError(null);

      try {
        workboxRef.current.messageSkipWaiting();
      } catch (error) {
        console.error("No se pudo enviar skipWaiting al service worker.", error);
        failUpdate("No se pudo activar la nueva versión. Reintentá en unos segundos.");
        return;
      }

      clearUpdateTimeout();
      updateTimeoutRef.current = window.setTimeout(() => {
        failUpdate("La actualización no pudo tomar control de esta pestaña. Reintentá o cerrá otras pestañas de Huginn y volvé a probar.");
      }, PWA_UPDATE_TIMEOUT_MS);
    },
  }), [isOnline, saveStatus, updateAvailable, updateDismissed, updateState, updateError, updateRequiresConfirmation]);

  return createElement(PwaContext.Provider, { value }, children);
}

export function usePwa() {
  const context = useContext(PwaContext);
  if (!context) {
    throw new Error("usePwa debe usarse dentro de PwaProvider");
  }
  return context;
}
