/** The navigation tree, and the one place it is declared.
 *
 * Three surfaces render this: the desktop sidebar, the mobile tab bar, and the
 * mobile drawer. They read from here rather than each owning a list, for the
 * same reason `components/ui/data-list.tsx` refuses to split into a table and a
 * card component — a second list is a second place to add a destination, and
 * the one nobody develops against silently falls behind.
 *
 * `id` keys into the `nav.*` / `nav.group*` dictionary entries (see
 * `lib/i18n/dictionaries.{en,es}.ts`); label text lives only there, so adding a
 * language never means touching this file.
 */

import {
  Bell,
  BookOpenCheck,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileText,
  FlaskConical,
  LayoutDashboard,
  ScanEye,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { AuthUser } from "@/lib/auth";

export interface NavItem {
  href: string;
  id: string;
  icon: LucideIcon;
  /** Promoted to the mobile tab bar. Everything else is drawer-only.
   *
   * A tab bar holds five destinations before the labels stop being readable,
   * so this is a hard budget, not a preference — `primaryTabs` enforces it. */
  primary?: boolean;
}

export interface NavGroup {
  groupId: string | null;
  items: NavItem[];
}

export const CLINICIAN_NAV: NavGroup[] = [
  {
    groupId: null,
    items: [{ href: "/dashboard", id: "dashboard", icon: LayoutDashboard, primary: true }],
  },
  {
    groupId: "groupClinical",
    items: [
      { href: "/patients", id: "patients", icon: Users, primary: true },
      { href: "/schedule", id: "schedule", icon: CalendarDays, primary: true },
      { href: "/results", id: "results", icon: FlaskConical, primary: true },
      { href: "/approvals", id: "approvals", icon: ClipboardCheck },
      { href: "/alerts", id: "alerts", icon: Bell, primary: true },
    ],
  },
  {
    groupId: "groupIntelligence",
    items: [
      { href: "/imaging", id: "imaging", icon: ScanEye },
      { href: "/evidence", id: "evidence", icon: BookOpenCheck },
    ],
  },
];

export const PATIENT_NAV: NavGroup[] = [
  {
    groupId: null,
    items: [
      { href: "/portal", id: "portalHome", icon: LayoutDashboard, primary: true },
      { href: "/portal/appointments", id: "portalAppointments", icon: ClipboardList, primary: true },
      { href: "/portal/results", id: "portalResults", icon: FileText, primary: true },
    ],
  },
];

export const MAX_TABS = 5;

export function navFor(role: AuthUser["role"] | undefined): NavGroup[] {
  return role === "patient" ? PATIENT_NAV : CLINICIAN_NAV;
}

/** The tab bar's destinations, flattened and capped. */
export function primaryTabs(role: AuthUser["role"] | undefined): NavItem[] {
  return navFor(role)
    .flatMap((g) => g.items)
    .filter((i) => i.primary)
    .slice(0, MAX_TABS);
}

/** Whether `href` is the current section.
 *
 * The `+ "/"` matters: a bare `startsWith` would light up `/portal` for
 * `/portal/results` *and* light up `/patients` for a hypothetical
 * `/patients-archive`. */
export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + "/");
}
