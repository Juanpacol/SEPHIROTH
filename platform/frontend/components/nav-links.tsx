"use client";

/** The grouped list of nav links, rendered identically by the desktop sidebar
 * and the mobile drawer. Pairs with `lib/nav.ts`: that file owns *which*
 * destinations exist, this one owns how a link looks. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import { isActive, navFor } from "@/lib/nav";

export default function NavLinks({
  className,
  /** The drawer closes on navigation; the sidebar has nothing to close. */
  onNavigate,
}: {
  className?: string;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const user = useUser();
  const { t } = useLanguage();

  return (
    <nav className={className}>
      {navFor(user?.role).map((group) => (
        <div key={group.groupId ?? "root"}>
          {group.groupId && <div className="nav-group-label">{t(`nav.${group.groupId}`)}</div>}
          {group.items.map(({ href, id, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              aria-current={isActive(pathname, href) ? "page" : undefined}
              className={`nav-item ${isActive(pathname, href) ? "nav-item-active" : ""}`}
            >
              <Icon size={17} />
              {t(`nav.${id}`)}
            </Link>
          ))}
        </div>
      ))}
    </nav>
  );
}
