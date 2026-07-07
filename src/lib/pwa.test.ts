import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const registerMock = vi.fn();
const addEventListenerMock = vi.fn();
const instances: Array<{
  listeners: Map<string, () => void>;
  messageSkipWaiting: ReturnType<typeof vi.fn>;
  scriptUrl: string;
  options: { scope: string };
}> = [];

vi.mock("workbox-window", () => ({
  Workbox: class MockWorkbox {
    listeners = new Map<string, () => void>();
    messageSkipWaiting = vi.fn();

    constructor(public scriptUrl: string, public options: { scope: string }) {
      instances.push(this);
    }

    addEventListener(type: string, handler: () => void) {
      this.listeners.set(type, handler);
      addEventListenerMock(type, handler);
    }

    register() {
      return registerMock();
    }
  },
}));

describe("registerAppServiceWorker", () => {
  beforeEach(() => {
    registerMock.mockReset();
    addEventListenerMock.mockReset();
    instances.length = 0;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("se registra en producción con scope raíz", async () => {
    const { registerAppServiceWorker } = await import("./pwa");
    const onRegistered = vi.fn();
    const registration = { scope: "/" } as ServiceWorkerRegistration;
    registerMock.mockResolvedValue(registration);

    const handle = registerAppServiceWorker({
      isProduction: true,
      navigatorRef: { serviceWorker: {} as Navigator["serviceWorker"] },
      onRegistered,
    });

    expect(handle).not.toBeNull();
    expect(instances).toHaveLength(1);
    expect(instances[0].scriptUrl).toBe("/sw.js");
    expect(instances[0].options).toEqual({ scope: "/" });
    await handle?.registerPromise;
    expect(onRegistered).toHaveBeenCalledWith(registration);
  });

  it("no se registra en desarrollo", async () => {
    const { registerAppServiceWorker } = await import("./pwa");

    const handle = registerAppServiceWorker({
      isProduction: false,
      navigatorRef: { serviceWorker: {} as Navigator["serviceWorker"] },
    });

    expect(handle).toBeNull();
    expect(instances).toHaveLength(0);
    expect(registerMock).not.toHaveBeenCalled();
  });

  it("detecta un worker waiting sin activarlo automáticamente", async () => {
    const { registerAppServiceWorker } = await import("./pwa");
    const logger = { error: vi.fn(), info: vi.fn() };
    const onWaiting = vi.fn();
    const reload = vi.fn();
    registerMock.mockResolvedValue(undefined);
    vi.stubGlobal("window", { location: { reload } });

    const handle = registerAppServiceWorker({
      isProduction: true,
      navigatorRef: { serviceWorker: {} as Navigator["serviceWorker"] },
      logger,
      onWaiting,
    });

    instances[0].listeners.get("waiting")?.();

    expect(handle).not.toBeNull();
    expect(onWaiting).toHaveBeenCalledWith(instances[0], undefined);
    expect(logger.info).toHaveBeenCalled();
    expect(instances[0].messageSkipWaiting).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it("reporta errores de registro", async () => {
    const { registerAppServiceWorker } = await import("./pwa");
    const logger = { error: vi.fn(), info: vi.fn() };
    const onError = vi.fn();
    const error = new Error("sw failed");
    registerMock.mockRejectedValue(error);

    const handle = registerAppServiceWorker({
      isProduction: true,
      navigatorRef: { serviceWorker: {} as Navigator["serviceWorker"] },
      logger,
      onError,
    });

    await expect(handle?.registerPromise).rejects.toThrow("sw failed");
    expect(onError).toHaveBeenCalledWith(error);
    expect(logger.error).toHaveBeenCalled();
  });
});

describe("pwa update helpers", () => {
  it("bloquea actualización mientras guarda", async () => {
    const { canApplyUpdate, getUpdateWarning, resolveUpdateIntent } = await import("./pwa");

    expect(canApplyUpdate("guardando")).toBe(false);
    expect(getUpdateWarning("guardando")).toContain("termine de guardar");
    expect(resolveUpdateIntent("guardando", false)).toBe("blocked");
  });

  it("advierte antes de actualizar si hay error de guardado", async () => {
    const { canApplyUpdate, getUpdateWarning, resolveUpdateIntent } = await import("./pwa");

    expect(canApplyUpdate("error")).toBe(true);
    expect(getUpdateWarning("error")).toContain("puede perder cambios");
    expect(resolveUpdateIntent("error", false)).toBe("confirm");
    expect(resolveUpdateIntent("error", true)).toBe("apply");
  });

  it("permite actualizar normalmente cuando está guardado", async () => {
    const { canApplyUpdate, getUpdateWarning, resolveUpdateIntent } = await import("./pwa");

    expect(canApplyUpdate("guardado")).toBe(true);
    expect(getUpdateWarning("guardado")).toBeNull();
    expect(resolveUpdateIntent("guardado", false)).toBe("apply");
  });

  it("suscribe y limpia controllerchange", async () => {
    const { subscribeToControllerChange } = await import("./pwa");
    const add = vi.fn();
    const remove = vi.fn();
    const target = { addEventListener: add, removeEventListener: remove } as unknown as ServiceWorkerContainer;
    const onChange = vi.fn();

    const unsubscribe = subscribeToControllerChange(target, onChange);
    expect(add).toHaveBeenCalledWith("controllerchange", onChange);

    unsubscribe();
    expect(remove).toHaveBeenCalledWith("controllerchange", onChange);
  });
});
