import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readOnlineStatus, subscribeToConnectivity } from "./connectivity";

describe("connectivity helpers", () => {
  const listeners = new Map<string, () => void>();
  const target = {
    addEventListener: vi.fn((type: string, handler: () => void) => {
      listeners.set(type, handler);
    }),
    removeEventListener: vi.fn((type: string) => {
      listeners.delete(type);
    }),
  };

  beforeEach(() => {
    listeners.clear();
    target.addEventListener.mockClear();
    target.removeEventListener.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("usa navigator.onLine como estado inicial", () => {
    expect(readOnlineStatus({ onLine: false })).toBe(false);
    expect(readOnlineStatus({ onLine: true })).toBe(true);
  });

  it("responde a eventos online y offline", () => {
    const onChange = vi.fn();
    subscribeToConnectivity(target as unknown as Window, onChange);

    listeners.get("offline")?.();
    listeners.get("online")?.();

    expect(onChange).toHaveBeenNthCalledWith(1, false);
    expect(onChange).toHaveBeenNthCalledWith(2, true);
  });

  it("limpia listeners al desuscribirse", () => {
    const onChange = vi.fn();
    const unsubscribe = subscribeToConnectivity(target as unknown as Window, onChange);

    unsubscribe();

    expect(target.removeEventListener).toHaveBeenCalledTimes(2);
    expect(listeners.size).toBe(0);
  });

  it("no crea colas ni reintenta escrituras", () => {
    const fetchSpy = vi.fn();
    const onChange = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    subscribeToConnectivity(target as unknown as Window, onChange);
    listeners.get("offline")?.();
    listeners.get("online")?.();

    expect(onChange).toHaveBeenCalledTimes(2);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
