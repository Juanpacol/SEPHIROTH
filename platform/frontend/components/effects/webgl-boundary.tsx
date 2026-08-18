"use client";

/** Catches a WebGL/three.js failure (missing GPU, disabled WebGL, driver
 * issue) so a purely decorative effect can never take the whole page down
 * with it — renders nothing instead of an "Unhandled Runtime Error"
 * overlay. Class component because React only supports error boundaries
 * via `componentDidCatch`/`getDerivedStateFromError`, no hook equivalent. */

import { Component, type ReactNode } from "react";

export default class WebglBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.warn("Decorative WebGL effect failed to render; hiding it.", error);
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}
