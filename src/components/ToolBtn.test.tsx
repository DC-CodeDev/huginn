import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { ToolBtn } from "./ToolBtn";
import { THEMES } from "../lib/theme";

afterEach(cleanup);

describe("ToolBtn", () => {
  it("shows the Bylgja tooltip on hover and preserves its accessible name and click action", async () => {
    const onClick = vi.fn();
    const { getByRole, findByRole } = render(
      <ToolBtn T={THEMES.dark} label="Acercar" onClick={onClick}><span aria-hidden="true">+</span></ToolBtn>,
    );

    const trigger = getByRole("button", { name: "Acercar" });
    fireEvent.pointerEnter(trigger, { pointerType: "mouse" });

    expect((await findByRole("tooltip")).textContent).toBe("Acercar");
    fireEvent.click(trigger);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("opens on keyboard focus and closes with Escape", async () => {
    const { getByRole, findByRole } = render(
      <ToolBtn T={THEMES.dark} label="Restablecer vista" onClick={() => undefined}><span aria-hidden="true">↺</span></ToolBtn>,
    );

    const trigger = getByRole("button", { name: "Restablecer vista" });
    fireEvent.focus(trigger);
    const tooltip = await findByRole("tooltip");
    expect(trigger.getAttribute("aria-describedby")).toBe(tooltip.id);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(tooltip.getAttribute("aria-hidden")).toBe("true");
  });
});
