"use client";

/** Renders children into `document.body` instead of wherever the component
 * happens to sit in the tree.
 *
 * Why this exists: an overlay rendered in normal DOM order is trapped by any
 * ancestor that establishes a stacking or containing block — `overflow:hidden`,
 * `transform`, `filter`, `backdrop-filter`, `position: sticky`. This app has all
 * of those (`.glass-surface` uses `backdrop-blur`, the sidebar is sticky, cards
 * clip their content), so a drawer opened from inside one of them can be
 * clipped or painted under the page no matter how high its `z-index` goes.
 *
 * The mounted guard is not optional: `document` does not exist during the
 * server render, and calling `createPortal` there throws. Returning `null` on
 * the first client pass also keeps the server and client markup identical,
 * which is what prevents a hydration mismatch. */

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

export default function Portal({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;
  return createPortal(children, document.body);
}
