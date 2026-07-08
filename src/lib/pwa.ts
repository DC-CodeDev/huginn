import { Workbox } from "workbox-window";
import { createContext, createElement, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { SaveStatus } from "../api";
import { useOnlineStatus } from "./connectivity";

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

type PwaContextValue = {
  isOnline: boolean;
  saveStatus: SaveStatus | null;
  updateAvailable: boolean;
  updateDismissed: boolean;
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

export function PwaProvider({ children }: { children: ReactNode }) {
  const isOnline = useOnlineStatus();
  const [saveStatus, setSaveStatus] = useState<SaveStatus | null>(null);
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const [updateRequiresConfirmation, setUpdateRequiresConfirmation] = useState(false);
  const workboxRef = useRef<Workbox | null>(null);
  const shouldReloadOnControllerChange = useRef(false);

  useEffect(() => {
    if (!("serviceWorker" in navigator) || !import.meta.env.PROD) {
      return;
    }

    const handleControllerChange = () => {
      if (shouldReloadOnControllerChange.current) {
        window.location.reload();
      }
    };

    return subscribeToControllerChange(navigator.serviceWorker, handleControllerChange);
  }, []);

  useEffect(() => {
    const registration = registerAppServiceWorker({
      onWaiting: (workbox) => {
        workboxRef.current = workbox;
        setUpdateAvailable(true);
        setUpdateDismissed(false);
      },
    });

    workboxRef.current = registration?.workbox ?? null;
  }, []);

  const value = useMemo<PwaContextValue>(() => ({
    isOnline,
    saveStatus,
    updateAvailable,
    updateDismissed,
    updateRequiresConfirmation,
    canApplyUpdate: canApplyUpdate(saveStatus),
    updateWarning: getUpdateWarning(saveStatus),
    setSaveStatus,
    dismissUpdate: () => {
      setUpdateDismissed(true);
      setUpdateRequiresConfirmation(false);
    },
    requestUpdate: () => {
      if (!workboxRef.current) {
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
      setUpdateRequiresConfirmation(false);
      workboxRef.current.messageSkipWaiting();
    },
  }), [isOnline, saveStatus, updateAvailable, updateDismissed, updateRequiresConfirmation]);

  return createElement(PwaContext.Provider, { value }, children);
}

export function usePwa() {
  const context = useContext(PwaContext);
  if (!context) {
    throw new Error("usePwa debe usarse dentro de PwaProvider");
  }
  return context;
}
