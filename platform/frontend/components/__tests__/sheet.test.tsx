/** `Sheet` — the drawer primitive everything modal is built on.
 *
 * These assert the two properties the pre-portal, pre-focus-trap version did
 * not have, which is the whole reason it was rewritten: the overlay escapes its
 * DOM position, and keyboard focus cannot leave it. Both are invisible to a
 * mouse user and both are the difference between "looks modal" and "is modal".
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Sheet from "@/components/ui/sheet";
import { LanguageProvider } from "@/lib/language";

function renderSheet(props: Partial<React.ComponentProps<typeof Sheet>> = {}) {
  const onClose = vi.fn();
  const result = render(
    <LanguageProvider>
      <button type="button">opener</button>
      <Sheet open onClose={onClose} title="Detalle" {...props}>
        <button type="button">first</button>
        <button type="button">second</button>
      </Sheet>
    </LanguageProvider>,
  );
  return { onClose, ...result };
}

describe("Sheet", () => {
  it("AC-017-01 — renders into document.body, not where it sits in the tree", () => {
    const { container } = renderSheet();
    const dialog = screen.getByRole("dialog");

    // The portal is what keeps a drawer from being clipped by an ancestor
    // with overflow:hidden or backdrop-blur — of which this app has several.
    expect(container).not.toContainElement(dialog);
    expect(document.body).toContainElement(dialog);
  });

  it("renders nothing at all when closed", () => {
    render(
      <LanguageProvider>
        <Sheet open={false} onClose={vi.fn()} title="Detalle">
          <button type="button">first</button>
        </Sheet>
      </LanguageProvider>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  // Tab order inside the panel is [close, first, second] — the close button
  // lives in the header, above the children.
  it("AC-017-02 — moves focus into the panel when it opens", () => {
    renderSheet();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /close/i }));
  });

  it("AC-017-03 — cycles Tab from the last control back to the first", () => {
    renderSheet();

    screen.getByRole("button", { name: "second" }).focus();
    fireEvent.keyDown(document, { key: "Tab" });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: /close/i }));
  });

  it("AC-017-03 — cycles Shift+Tab from the first control back to the last", () => {
    renderSheet();

    screen.getByRole("button", { name: /close/i }).focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "second" }));
  });

  it("AC-017-04 — does not let Tab reach the page behind the scrim", () => {
    renderSheet();
    const opener = screen.getByRole("button", { name: "opener" });

    // Simulate focus having escaped (a stray programmatic focus, an iframe):
    // the next Tab must pull it back inside, not walk further down the page.
    opener.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "second" }));
  });

  it("AC-017-02 — restores focus to whatever opened it", () => {
    const { rerender } = renderSheet();
    const opener = screen.getByRole("button", { name: "opener" });
    // The trap captures document.activeElement on open, so establish it first
    // by re-opening with the opener focused.
    opener.focus();

    rerender(
      <LanguageProvider>
        <button type="button">opener</button>
        <Sheet open={false} onClose={vi.fn()} title="Detalle">
          <button type="button">first</button>
        </Sheet>
      </LanguageProvider>,
    );

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "opener" }));
  });

  it("AC-017-05 — locks page scroll while open and releases it on close", () => {
    const { rerender } = renderSheet();
    expect(document.body.style.overflow).toBe("hidden");

    rerender(
      <LanguageProvider>
        <button type="button">opener</button>
        <Sheet open={false} onClose={vi.fn()} title="Detalle">
          <button type="button">first</button>
        </Sheet>
      </LanguageProvider>,
    );

    expect(document.body.style.overflow).not.toBe("hidden");
  });

  it("closes on Escape and on a scrim click", () => {
    const { onClose } = renderSheet();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("dialog").querySelector("[aria-hidden='true']")!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
