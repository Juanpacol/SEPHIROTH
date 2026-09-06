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
  Activity,
  Bell,
  BookOpenCheck,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  FileText,
  LayoutDashboard,
  ScanEye,
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
}

export interface NavGroup {
  groupId: string | null;
  items: NavItem[];
}

export const CLINICIAN_NAV: NavGroup[] = [
  {
    groupId: null,
    items: [{ href: "/dashboard", id: "dashboard", icon: LayoutDashboard, mobile: true }],
  },
  {
    groupId: "groupClinical",
    items: [
      { href: "/patients", id: "patients", icon: Users, mobile: true },
      { href: "/schedule", id: "schedule", icon: CalendarDays, mobile: true },
      { href: "/approvals", id: "approvals", icon: ClipboardCheck },
      { href: "/alerts", id: "alerts", icon: Bell, mobile: true },
    ],
  },
  {
    groupId: "groupIntelligence",
    items: [
      { href: "/imaging", id: "imaging", icon: ScanEye },
      { href: "/evidence", id: "evidence", icon: BookOpenCheck },
      { href: "/agents", id: "agents", icon: Activity },
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
