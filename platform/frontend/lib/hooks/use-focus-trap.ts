"use client";

/** Keeps keyboard focus inside an open overlay, and gives it back when the
 * overlay closes.
 *
 * Without this, a drawer is only visually modal: Tab walks straight out of it
 * into the page behind, and a screen reader reads that page as if nothing had
 * opened. That is tolerable for a small right-side sheet on a desktop and not
 * tolerable for a mobile navigation drawer, which is why it lands before the
 * mobile shell rather than after it.
 *
 * Four jobs, in order of how often they are forgotten:
 *   1. move focus into the overlay when it opens,
 *   2. cycle Tab / Shift+Tab within it,
 *   3. restore focus to whatever opened it,
 *   4. stop the page behind from scrolling.
 *
 * Scope: this hook does not render a scrim, does not handle Escape, and does
 * not set `aria-modal` — those belong to the component, which knows what it is.
 *
 * It takes the element itself, not a `RefObject`. That is deliberate: these
 * overlays render through `Portal`, which returns `null` on its first pass and
 * only mounts its children on the following one. A ref's `.current` is invisible
 * to the dependency array, so the effect would run once against `null` and never
 * again — the trap would silently do nothing, which is exactly the bug it exists
 * to prevent. Callers hold the node in state via a callback ref instead.
 */

import { useEffect } from "react";

/** Tab order, minus the things that look focusable and are not. `[hidden]`,
 * `disabled`, and `tabindex="-1"` are excluded by the selector; elements
 * hidden by CSS are filtered at runtime below, since a selector cannot see
 * `display: none` applied by a class. */
const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
]
  .map((selector) => `${selector}:not([hidden])`)
  .join(",");

/** Deliberately not `offsetParent`/`getClientRects`, the usual way to ask this:
 * jsdom performs no layout, so both report every element as invisible and the
 * trap would find nothing to focus in any test — a filter that only works in a
 * real browser is a filter nothing can prove. Computed style is implemented in
 * both, and the `[hidden]` walk covers the ancestor case cheaply. */
function isVisible(el: HTMLElement): boolean {
  if (el.closest("[hidden]")) return false;
  const style = typeof getComputedStyle === "function" ? getComputedStyle(el) : null;
  return !style || (style.display !== "none" && style.visibility !== "hidden");
}

function focusableWithin(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(isVisible);
}

export function useFocusTrap(container: HTMLElement | null, active: boolean) {
  useEffect(() => {
    if (!active || !container) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    // Prefer the first real control; fall back to the container itself so
    // focus is never left behind on the page when an overlay opens empty.
    const initial = focusableWithin(container)[0] ?? container;
    if (initial === container && !container.hasAttribute("tabindex")) {
      container.setAttribute("tabindex", "-1");
    }
    initial.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = focusableWithin(container);
      if (items.length === 0) {
        // Nothing to move to; keep focus where it is rather than letting the
        // browser hand it to the page behind.
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const current = document.activeElement;

      if (event.shiftKey && (current === first || !container.contains(current))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && current === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      // The opener can be gone by now (a row that the action removed, say),
      // so check it is still connected before handing focus back to it.
      if (previouslyFocused && previouslyFocused.isConnected) previouslyFocused.focus();
    };
  }, [container, active]);
}

export default useFocusTrap;
