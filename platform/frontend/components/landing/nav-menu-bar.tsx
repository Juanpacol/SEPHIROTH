"use client";

/** The landing header's menus: a row of buttons, each opening a panel of destinations
 * with a line about each. One panel is open at a time.
 *
 * There is one panel for all the menus, in the manner of Stripe's: it is a single floating
 * card that slides under the button you move to and changes height to fit its contents,
 * while the contents fade through, so going from one menu to the next reads as the same
 * object moving rather than one panel closing and another opening. The only hover on the
 * buttons is a fine line that grows under them (`.nav-underline`), and the card is the
 * header's own navy: nothing changes colour when a menu is chosen.
 *
 * Opens on click and, on a device that can hover, on hover too (after a short pause,
 * so crossing the bar does not flash every panel). Closes on Escape (focus goes back
 * to the button), on a click outside, when focus leaves the bar, and when an item is
 * chosen. The panel is a `region` the button controls, as in a disclosure, not an
 * ARIA menu: its content is ordinary links, and a menu role would promise arrow-key
 * behaviour a list of links does not have. */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import { useActiveSection } from "@/lib/hooks/use-active-section";
import { useLanguage } from "@/lib/language";
import { NAV_MENUS, NAV_SECTIONS, type NavItem, type NavMenu } from "./nav-menus";

const HOVER_OPEN_MS = 90;
const HOVER_CLOSE_MS = 160;
/** How much later each item enters than the one before it. */
const STAGGER_MS = 30;

function ItemLink({
  item,
  current,
  onChoose,
  index,
}: {
  item: NavItem;
  current: boolean;
  onChoose: () => void;
  index: number;
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
      style={{ animationDelay: `${index * STAGGER_MS}ms` }}
      className="group/item tap flex animate-fadeIn items-start gap-3 rounded-inner px-3 py-2.5 transition-colors duration-normal [animation-fill-mode:both]"
    >
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-ink transition-colors duration-normal group-hover/item:text-primary-ink">
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

function PanelContent({
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
    <div id={id} role="region" aria-label={t(menu.labelKey)} className="animate-fadeIn p-2">
      <div className="eyebrow px-3 pb-1 pt-2 text-muted">{t(menu.eyebrowKey)}</div>
      <ul className="flex flex-col">
        {menu.items.map((item, i) => (
          <li key={item.href}>
            <ItemLink
              item={item}
              index={i}
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
  const [height, setHeight] = useState<number | null>(null);
  const bar = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});
  const cells = useRef<Record<string, HTMLDivElement | null>>({});
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

  // The card is as tall as what is in it, and follows it when it changes: measured here so
  // the height can be transitioned (an `auto` height cannot).
  useEffect(() => {
    const el = inner.current;
    if (!openId || !el) {
      setHeight(null);
      return;
    }
    setHeight(el.offsetHeight);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setHeight(el.offsetHeight));
    observer.observe(el);
    return () => observer.disconnect();
  }, [openId]);

  // The one panel sits after every button in the DOM, so Tab would skip over its links to the
  // next button. Keyboard focus is handed across by hand: from the open button into the panel's
  // first link, from the panel's last link on to the next button, and back from its first.
  const links = () => Array.from(panel.current?.querySelectorAll<HTMLAnchorElement>("a") ?? []);
  const onButtonKeyDown = (e: ReactKeyboardEvent<HTMLButtonElement>, id: string) => {
    if (e.key !== "Tab" || e.shiftKey || openId !== id) return;
    const first = links()[0];
    if (!first) return;
    e.preventDefault();
    first.focus();
  };
  const onPanelKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Tab" || !openId) return;
    const all = links();
    if (e.shiftKey && document.activeElement === all[0]) {
      e.preventDefault();
      buttons.current[openId]?.focus();
    } else if (!e.shiftKey && document.activeElement === all[all.length - 1]) {
      const next = NAV_MENUS[NAV_MENUS.findIndex((m) => m.id === openId) + 1];
      if (next) {
        e.preventDefault();
        buttons.current[next.id]?.focus();
      }
    }
  };

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

  const open = NAV_MENUS.find((m) => m.id === openId) ?? null;
  const panelCell = openId ? cells.current[openId] : null;

  return (
    <div
      ref={bar}
      className="relative hidden items-center gap-1 md:flex"
      onMouseLeave={scheduleClose}
      onMouseEnter={clear}
      onBlur={(e) => {
        if (!bar.current?.contains(e.relatedTarget as Node | null)) close();
      }}
    >
      {NAV_MENUS.map((menu) => {
        const panelId = `${baseId}-${menu.id}`;
        const isOpen = openId === menu.id;
        const here = menu.id === "product" && active !== null;
        return (
          <div
            key={menu.id}
            ref={(el) => {
              cells.current[menu.id] = el;
            }}
            className="relative"
            onMouseEnter={() => scheduleOpen(menu.id)}
          >
            <button
              type="button"
              ref={(el) => {
                buttons.current[menu.id] = el;
              }}
              aria-expanded={isOpen}
              aria-controls={panelId}
              onKeyDown={(e) => onButtonKeyDown(e, menu.id)}
              onClick={() => {
                clear();
                setOpenId(isOpen ? null : menu.id);
              }}
              className={`tap relative inline-flex items-center gap-1 nav-underline px-3.5 py-2 text-sm font-medium transition-colors duration-normal hover:text-ink ${
                isOpen ? "text-ink" : "text-muted"
              }`}
              data-here={here || undefined}
            >
              {t(menu.labelKey)}
              <ChevronDown
                size={14}
                aria-hidden="true"
                className={`transition-transform duration-normal ease-standard ${isOpen ? "rotate-180" : ""}`}
              />
            </button>
          </div>
        );
      })}

      {open ? (
        <div
          ref={panel}
          data-nav-panel
          onKeyDown={onPanelKeyDown}
          className="absolute top-full z-30 mt-3 w-[min(92vw,24rem)] animate-fadeIn overflow-hidden rounded-card border border-line/60 bg-surface shadow-popover transition-[left,height] duration-slow ease-sheet"
          style={{ left: panelCell?.offsetLeft ?? 0, height: height ?? undefined }}
        >
          <div ref={inner}>
            <PanelContent
              key={open.id}
              menu={open}
              id={`${baseId}-${open.id}`}
              active={active}
              onChoose={() => close()}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
