import { useEffect, useState } from "react";

type NavigatorLike = Pick<Navigator, "onLine"> | undefined;
type EventTargetLike = Pick<Window, "addEventListener" | "removeEventListener"> | undefined;

export function readOnlineStatus(navigatorRef: NavigatorLike = globalThis.navigator): boolean {
  // navigator.onLine solo refleja conectividad percibida por el navegador:
  // no garantiza que la API o el backend de Huginn estén disponibles.
  return navigatorRef?.onLine ?? true;
}

export function subscribeToConnectivity(
  target: EventTargetLike,
  onChange: (isOnline: boolean) => void,
): () => void {
  if (!target) {
    return () => {};
  }

  const handleOnline = () => onChange(true);
  const handleOffline = () => onChange(false);

  target.addEventListener("online", handleOnline);
  target.addEventListener("offline", handleOffline);

  return () => {
    target.removeEventListener("online", handleOnline);
    target.removeEventListener("offline", handleOffline);
  };
}

export function useOnlineStatus(options: {
  navigatorRef?: NavigatorLike;
  target?: EventTargetLike;
} = {}): boolean {
  const navigatorRef = options.navigatorRef ?? globalThis.navigator;
  const target = options.target ?? globalThis.window;
  const [isOnline, setIsOnline] = useState(() => readOnlineStatus(navigatorRef));

  useEffect(() => {
    setIsOnline(readOnlineStatus(navigatorRef));
    return subscribeToConnectivity(target, setIsOnline);
  }, [navigatorRef, target]);

  return isOnline;
}
