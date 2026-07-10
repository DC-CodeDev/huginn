import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { AnimatedModal } from "./AnimatedModal";

afterEach(cleanup);

describe("AnimatedModal", () => {
  it("no renderiza contenido ni backdrop cuando show=false", () => {
    const { container } = render(
      <AnimatedModal show={false} onClose={() => {}}>
        <div data-testid="panel">contenido</div>
      </AnimatedModal>,
    );
    expect(screen.queryByTestId("panel")).toBeNull();
    expect(container.querySelector(".bylgja-modal-backdrop")).toBeNull();
  });

  it("monta el backdrop y el contenido cuando show=true", () => {
    const { container } = render(
      <AnimatedModal show onClose={() => {}}>
        <div data-testid="panel">contenido</div>
      </AnimatedModal>,
    );
    expect(screen.getByTestId("panel")).toBeTruthy();
    expect(container.querySelector(".bylgja-modal-backdrop")).not.toBeNull();
    expect(container.querySelector(".bylgja-modal-panel")).not.toBeNull();
  });

  it("cierra al hacer click afuera del panel (en la capa interactiva)", () => {
    const onClose = vi.fn();
    render(
      <AnimatedModal show onClose={onClose}>
        <div data-testid="panel">contenido</div>
      </AnimatedModal>,
    );
    // La capa interactiva es el ancestro con inset-0 que centra el panel.
    const overlay = screen.getByTestId("panel").closest(".fixed.inset-0") as HTMLElement;
    // Click sobre la capa misma (target === currentTarget) => cierra.
    fireEvent.mouseDown(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("no cierra al hacer click dentro del panel", () => {
    const onClose = vi.fn();
    render(
      <AnimatedModal show onClose={onClose}>
        <div data-testid="panel">contenido</div>
      </AnimatedModal>,
    );
    fireEvent.mouseDown(screen.getByTestId("panel"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("cierra al presionar Escape cuando está visible", () => {
    const onClose = vi.fn();
    render(
      <AnimatedModal show onClose={onClose}>
        <div data-testid="panel">contenido</div>
      </AnimatedModal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("respeta closeOnEscape=false", () => {
    const onClose = vi.fn();
    render(
      <AnimatedModal show onClose={onClose} closeOnEscape={false}>
        <div data-testid="panel">contenido</div>
      </AnimatedModal>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
