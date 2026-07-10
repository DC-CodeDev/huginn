import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement } from "react";
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
    vi.unstubAllGlobals();
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
    registerMock.mockResolvedValue(undefined);

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

describe("PwaProvider update flow", () => {
  const renderUpdateHarness = async () => {
    const { PwaProvider, usePwa } = await import("./pwa");

    function Harness() {
      const pwa = usePwa();
      return createElement(
        "div",
        null,
        createElement("div", { "data-testid": "state" }, pwa.updateState),
        createElement("div", { "data-testid": "error" }, pwa.updateError ?? ""),
        createElement("div", { "data-testid": "dismissed" }, String(pwa.updateDismissed)),
        createElement("button", {
          type: "button",
          onClick: pwa.requestUpdate,
          disabled: !pwa.canApplyUpdate,
        }, "Actualizar"),
        createElement("button", {
          type: "button",
          onClick: pwa.dismissUpdate,
          disabled: pwa.updateState === "updating",
        }, "Más tarde"),
        createElement("button", {
          type: "button",
          onClick: () => pwa.setSaveStatus("guardando"),
        }, "Set saving"),
      );
    }

    return render(createElement(PwaProvider, {
      runtime: {
        isProduction: true,
        navigatorRef: { serviceWorker: serviceWorkerTarget as unknown as Navigator["serviceWorker"] },
        reload,
      },
    }, createElement(Harness)));
  };

  let serviceWorkerTarget: {
    listeners: Map<string, () => void>;
    addEventListener: ReturnType<typeof vi.fn>;
    removeEventListener: ReturnType<typeof vi.fn>;
  };
  let reload: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    registerMock.mockReset();
    addEventListenerMock.mockReset();
    instances.length = 0;
    registerMock.mockResolvedValue(undefined);
    reload = vi.fn();
    serviceWorkerTarget = {
      listeners: new Map(),
      addEventListener: vi.fn((type: string, handler: () => void) => {
        serviceWorkerTarget.listeners.set(type, handler);
      }),
      removeEventListener: vi.fn(),
    };
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("pasa a updating y evita doble actualización", async () => {
    await renderUpdateHarness();
    act(() => instances[0].listeners.get("waiting")?.());

    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));

    expect(screen.getByTestId("state").textContent).toBe("updating");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Actualizar" }).disabled).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Más tarde" }).disabled).toBe(true);
    expect(instances[0].messageSkipWaiting).toHaveBeenCalledTimes(1);
  });

  it("controllerchange recarga una sola vez", async () => {
    await renderUpdateHarness();
    act(() => instances[0].listeners.get("waiting")?.());
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));

    act(() => serviceWorkerTarget.listeners.get("controllerchange")?.());
    act(() => serviceWorkerTarget.listeners.get("controllerchange")?.());

    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("muestra error si messageSkipWaiting falla", async () => {
    await renderUpdateHarness();
    act(() => instances[0].listeners.get("waiting")?.());
    instances[0].messageSkipWaiting.mockImplementationOnce(() => {
      throw new Error("skipWaiting failed");
    });

    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));

    expect(screen.getByTestId("state").textContent).toBe("error");
    expect(screen.getByTestId("error").textContent).toContain("No se pudo activar");
  });

  it("el timeout devuelve control al usuario", async () => {
    const { PWA_UPDATE_TIMEOUT_MS } = await import("./pwa");
    await renderUpdateHarness();
    act(() => instances[0].listeners.get("waiting")?.());
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));

    act(() => vi.advanceTimersByTime(PWA_UPDATE_TIMEOUT_MS));

    expect(screen.getByTestId("state").textContent).toBe("error");
    expect(screen.getByTestId("error").textContent).toContain("cerrá otras pestañas");
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Actualizar" }).disabled).toBe(false);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Más tarde" }).disabled).toBe(false);
  });

  it("limpia listeners y timers al desmontar", async () => {
    const clearTimeoutSpy = vi.spyOn(window, "clearTimeout");
    const { unmount } = await renderUpdateHarness();
    act(() => instances[0].listeners.get("waiting")?.());
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));

    unmount();

    expect(serviceWorkerTarget.removeEventListener).toHaveBeenCalledWith(
      "controllerchange",
      serviceWorkerTarget.listeners.get("controllerchange"),
    );
    expect(clearTimeoutSpy).toHaveBeenCalled();
  });

  it("Más tarde cierra en idle y no actúa durante updating", async () => {
    await renderUpdateHarness();
    act(() => instances[0].listeners.get("waiting")?.());

    fireEvent.click(screen.getByRole("button", { name: "Más tarde" }));
    expect(screen.getByTestId("dismissed").textContent).toBe("true");

    act(() => instances[0].listeners.get("waiting")?.());
    fireEvent.click(screen.getByRole("button", { name: "Actualizar" }));
    fireEvent.click(screen.getByRole("button", { name: "Más tarde" }));
    expect(screen.getByTestId("dismissed").textContent).toBe("false");
  });
});
