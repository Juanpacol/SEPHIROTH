"use client";

/** The landing header's menus: a row of buttons, each opening a panel of destinations
 * with a line about each. One panel is open at a time.
 *
 * Opens on click and, on a device that can hover, on hover too (after a short pause,
 * so crossing the bar does not flash every panel). Closes on Escape (focus goes back
 * to the button), on a click outside, when focus leaves the bar, and when an item is
 * chosen. The panel is a `region` the button controls, as in a disclosure, not an
 * ARIA menu: its content is ordinary links, and a menu role would promise arrow-key
 * behaviour a list of links does not have. */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { useActiveSection } from "@/lib/hooks/use-active-section";
import { useLanguage } from "@/lib/language";
import { NAV_MENUS, NAV_SECTIONS, type NavItem, type NavMenu } from "./nav-menus";

const HOVER_OPEN_MS = 90;
const HOVER_CLOSE_MS = 160;

function ItemLink({
  item,
  current,
  onChoose,
  promo = false,
}: {
  item: NavItem;
  current: boolean;
  onChoose: () => void;
  promo?: boolean;
}) {
  const { t } = useLanguage();
  const external = item.external
    ? { target: "_blank", rel: "noopener noreferrer" }
    : ({} as Record<string, string>);
  return (
    <a
      href={item.href}
      onClick={onChoose}
      aria-current={current ? "location" : undefined}
      {...external}
      className={`group/item tap flex items-start gap-3 rounded-inner px-3 py-2.5 transition-colors duration-normal hover:bg-primary-soft ${
        promo ? "bg-primary-soft/70" : ""
      }`}
    >
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
          {t(item.titleKey)}
          {current ? <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" /> : null}
          {item.external ? (
            <>
              <ArrowUpRight
                size={13}
                aria-hidden="true"
                className="text-muted group-hover/item:text-primary-ink"
              />
              <span className="sr-only">{t("marketing.nav.external")}</span>
            </>
          ) : null}
        </span>
        <span className="mt-0.5 block text-xs leading-relaxed text-muted">{t(item.bodyKey)}</span>
      </span>
    </a>
  );
}

function Panel({
  menu,
  id,
  active,
  onChoose,
}: {
  menu: NavMenu;
  id: string;
  active: string | null;
  onChoose: () => void;
}) {
  const { t } = useLanguage();
  return (
    <div
      id={id}
      role="region"
      aria-label={t(menu.labelKey)}
      className="absolute left-0 top-full z-30 mt-2 w-[min(92vw,24rem)] animate-fadeIn rounded-card bg-card p-2 shadow-popover"
    >
      <div className="eyebrow px-3 pb-1 pt-2 text-muted">{t(menu.eyebrowKey)}</div>
      {menu.promo ? (
        <div className="mb-1">
          <ItemLink item={menu.promo} current={active === menu.promo.section} onChoose={onChoose} promo />
        </div>
      ) : null}
      <ul className="flex flex-col">
        {menu.items.map((item) => (
          <li key={item.href}>
            <ItemLink
              item={item}
              current={Boolean(item.section) && active === item.section}
              onChoose={onChoose}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function NavMenuBar() {
  const { t } = useLanguage();
  const baseId = useId();
  const [openId, setOpenId] = useState<string | null>(null);
  const bar = useRef<HTMLDivElement>(null);
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const active = useActiveSection(NAV_SECTIONS);

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };
  const close = useCallback((restoreFocusTo?: string) => {
    clear();
    setOpenId(null);
    if (restoreFocusTo) buttons.current[restoreFocusTo]?.focus();
  }, []);
  const canHover = () =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia("(hover: hover)").matches
      : false;

  useEffect(() => {
    if (!openId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(openId);
    };
    const onPointer = (e: MouseEvent) => {
      if (bar.current && !bar.current.contains(e.target as Node)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [openId, close]);

  useEffect(() => clear, []);

  const scheduleOpen = (id: string) => {
    if (!canHover()) return;
    clear();
    timer.current = setTimeout(() => setOpenId(id), HOVER_OPEN_MS);
  };
  const scheduleClose = () => {
    if (!canHover()) return;
    clear();
    timer.current = setTimeout(() => setOpenId(null), HOVER_CLOSE_MS);
  };

  return (
    <div
      ref={bar}
      className="hidden items-center gap-1 md:flex"
      onMouseLeave={scheduleClose}
      onMouseEnter={clear}
      onBlur={(e) => {
        if (!bar.current?.contains(e.relatedTarget as Node | null)) close();
      }}
    >
      {NAV_MENUS.map((menu) => {
        const panelId = `${baseId}-${menu.id}`;
        const open = openId === menu.id;
        const here = menu.id === "product" && active !== null;
        return (
          <div key={menu.id} className="relative" onMouseEnter={() => scheduleOpen(menu.id)}>
            <button
              type="button"
              ref={(el) => {
                buttons.current[menu.id] = el;
              }}
              aria-expanded={open}
              aria-controls={panelId}
              onClick={() => {
                clear();
                setOpenId(open ? null : menu.id);
              }}
              className={`tap inline-flex items-center gap-1 rounded-full px-3.5 py-2 text-sm font-medium transition-colors duration-normal hover:bg-primary-soft hover:text-primary-ink ${
                open ? "bg-primary-soft text-primary-ink" : "text-muted"
              }`}
              data-here={here || undefined}
            >
              {t(menu.labelKey)}
              <ChevronDown
                size={14}
                aria-hidden="true"
                className={`transition-transform duration-normal ease-standard ${open ? "rotate-180" : ""}`}
              />
            </button>
            {open ? <Panel menu={menu} id={panelId} active={active} onChoose={() => close()} /> : null}
          </div>
        );
      })}
    </div>
  );
}
