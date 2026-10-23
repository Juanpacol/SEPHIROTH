"use client";

/** The landing page is dark whatever theme the reader chose for the app. The layout's own wrapper already
 * carries the dark colours for everything inside the page; this puts the `dark` class on `<html>` too, for
 * what React renders outside the page (the mobile menu sheet is a portal), and gives the reader's theme back
 * when they leave: the app keeps its light and dark. */

import { useEffect } from "react";

export default function ForceDark() {
  useEffect(() => {
    const root = document.documentElement;
    const hadDark = root.classList.contains("dark");
    root.classList.add("dark");
    return () => {
      if (!hadDark) root.classList.remove("dark");
    };
  }, []);

  return null;
}
