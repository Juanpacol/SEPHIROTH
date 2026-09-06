/** The navigation config, shared by the desktop sidebar and the mobile bottom
 * bar so the two cannot disagree about what exists.
 *
 * It lived inside `sidebar.tsx` while the sidebar was the only consumer. The
 * moment a phone has its own bar, a nav item defined in one place and forgotten
 * in the other is a destination that exists on a laptop and not on a phone —
 * the failure this app already has, in its most literal form.
 *
 * `id` keys into the `nav.*` dictionary entries; label text lives only in
 * `lib/i18n/`, so adding a language never means touching this file.
 */

import {
  Bell,
  CalendarDays,
  CheckSquare,
  ClipboardCheck,
  ClipboardList,
  FileText,
  FlaskConical,
  LayoutDashboard,
  Repeat,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  id: string;
  icon: LucideIcon;
  /** Promoted to the phone's bottom bar. Everything else lives behind "More".
   * Four at most: the fifth slot is the drawer trigger, and a bar of six
   * targets on a 375px screen is under the 44px comfortable minimum. */
  mobile?: boolean;
  /** Which counter from `useBadgeCounts` this destination shows, if any. */
  badge?: "tasks_open" | "alerts_active";
}

export interface NavGroup {
  groupId: string | null;
  items: NavItem[];
}

/** Flat, in the order a day runs: what is happening, what is waiting, who it
 * concerns, what came back, when it happens.
 *
 * The groups are gone. "Clinical" and "Intelligence" described how the system
 * is built rather than what a clinician is doing, and the second group was the
 * tell — `/imaging`, `/evidence` and `/agents` were top-level destinations
 * because they were interesting features, not because anyone starts their day
 * by opening them. They now live where they are used: imaging inside a
 * patient, evidence from an alert or a medication, agent activity under
 * `/admin`. Nothing was deleted; the URLs still work.
 */
export const CLINICIAN_NAV: NavGroup[] = [
  {
    groupId: null,
    items: [
      { href: "/work", id: "work", icon: LayoutDashboard, mobile: true },
      // Tasks displaces /alerts on the phone bar: an alert is one source of
      // work and this is all of them, so a clinician who can only reach four
      // destinations should reach the superset.
      { href: "/tasks", id: "tasks", icon: CheckSquare, mobile: true, badge: "tasks_open" },
      { href: "/patients", id: "patients", icon: Users, mobile: true },
      { href: "/agenda", id: "agenda", icon: CalendarDays, mobile: true },
      { href: "/alerts", id: "alerts", icon: Bell, badge: "alerts_active" },
      { href: "/approvals", id: "approvals", icon: ClipboardCheck },
      { href: "/results", id: "results", icon: FlaskConical },
      { href: "/followups", id: "followups", icon: Repeat },
      { href: "/settings", id: "settings", icon: Settings },
    ],
  },
];

export const PATIENT_NAV: NavGroup[] = [
  {
    groupId: null,
    items: [
      { href: "/portal", id: "portalHome", icon: LayoutDashboard, mobile: true },
      { href: "/portal/appointments", id: "portalAppointments", icon: ClipboardList, mobile: true },
      { href: "/portal/results", id: "portalResults", icon: FileText, mobile: true },
    ],
  },
];

export function navFor(role: string | undefined): NavGroup[] {
  return role === "patient" ? PATIENT_NAV : CLINICIAN_NAV;
}

export function flatNav(groups: NavGroup[]): NavItem[] {
  return groups.flatMap((group) => group.items);
}

/** Longest-prefix match, so `/patients/P001` highlights `/patients` and an
 * item whose href is a prefix of another (`/portal` vs `/portal/results`)
 * does not light up alongside it. */
export function isActive(pathname: string, href: string, allHrefs: string[]): boolean {
  const matches = allHrefs.filter((h) => pathname === h || pathname.startsWith(h + "/"));
  if (matches.length === 0) return false;
  return matches.reduce((a, b) => (b.length > a.length ? b : a)) === href;
}
