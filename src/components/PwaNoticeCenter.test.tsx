import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { PwaNoticeCenter } from "./PwaNoticeCenter";

const usePwaMock = vi.fn();

vi.mock("../lib/pwa", () => ({
  usePwa: () => usePwaMock(),
}));

describe("PwaNoticeCenter", () => {
  it("muestra aviso offline", () => {
    usePwaMock.mockReturnValue({
      isOnline: false,
      saveStatus: null,
      updateAvailable: false,
      updateDismissed: false,
      updateState: "idle",
      updateError: null,
      updateRequiresConfirmation: false,
      canApplyUpdate: true,
      updateWarning: null,
      setSaveStatus: vi.fn(),
      dismissUpdate: vi.fn(),
      requestUpdate: vi.fn(),
    });

    const html = renderToStaticMarkup(<PwaNoticeCenter />);
    expect(html).toContain("Sin conexión");
    expect(html).toContain("Huginn necesita red para cargar y guardar tus boards.");
  });

  it("muestra aviso de actualización y respeta guardando", () => {
    usePwaMock.mockReturnValue({
      isOnline: true,
      saveStatus: "guardando",
      updateAvailable: true,
      updateDismissed: false,
      updateState: "idle",
      updateError: null,
      updateRequiresConfirmation: false,
      canApplyUpdate: false,
      updateWarning: "Esperá a que el board termine de guardar antes de actualizar.",
      setSaveStatus: vi.fn(),
      dismissUpdate: vi.fn(),
      requestUpdate: vi.fn(),
    });

    const html = renderToStaticMarkup(<PwaNoticeCenter />);
    expect(html).toContain("Hay una nueva versión de Huginn disponible.");
    expect(html).toContain("Esperá a que el board termine de guardar");
    expect(html).toContain("disabled");
  });

  it("muestra advertencia extra si el guardado falló", () => {
    usePwaMock.mockReturnValue({
      isOnline: true,
      saveStatus: "error",
      updateAvailable: true,
      updateDismissed: false,
      updateState: "idle",
      updateError: null,
      updateRequiresConfirmation: true,
      canApplyUpdate: true,
      updateWarning: "Hay un error de guardado. Recargar ahora puede perder cambios recientes.",
      setSaveStatus: vi.fn(),
      dismissUpdate: vi.fn(),
      requestUpdate: vi.fn(),
    });

    const html = renderToStaticMarkup(<PwaNoticeCenter />);
    expect(html).toContain("Actualizar de todos modos");
    expect(html).toContain("puede perder cambios recientes");
  });

  it("muestra progreso y deshabilita acciones durante actualización", () => {
    usePwaMock.mockReturnValue({
      isOnline: true,
      saveStatus: "guardado",
      updateAvailable: true,
      updateDismissed: false,
      updateState: "updating",
      updateError: null,
      updateRequiresConfirmation: false,
      canApplyUpdate: false,
      updateWarning: null,
      setSaveStatus: vi.fn(),
      dismissUpdate: vi.fn(),
      requestUpdate: vi.fn(),
    });

    const html = renderToStaticMarkup(<PwaNoticeCenter />);
    expect(html).toContain("Actualizando...");
    expect(html).toContain("Activando la nueva versión");
    expect(html.match(/disabled/g)).toHaveLength(2);
  });

  it("muestra error y permite reintentar", () => {
    usePwaMock.mockReturnValue({
      isOnline: true,
      saveStatus: "guardado",
      updateAvailable: true,
      updateDismissed: false,
      updateState: "error",
      updateError: "La actualización no pudo tomar control de esta pestaña.",
      updateRequiresConfirmation: false,
      canApplyUpdate: true,
      updateWarning: null,
      setSaveStatus: vi.fn(),
      dismissUpdate: vi.fn(),
      requestUpdate: vi.fn(),
    });

    const html = renderToStaticMarkup(<PwaNoticeCenter />);
    expect(html).toContain("Reintentar");
    expect(html).toContain("La actualización no pudo tomar control");
  });
});
