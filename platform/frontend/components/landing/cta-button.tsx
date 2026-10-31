/** The landing page's calls to action, made for the hero's blue panels: `solid` is frosted glass, a
 * translucent white with a hairline edge and a highlight along its top, so it takes the colour of whatever
 * is behind it instead of fighting it, and brightens on hover (the look of Raycast's and Framer's buttons,
 * which sit on dark pictures the same way). `line` is plain text with a fine line that grows under it
 * (`.nav-underline`). Both are links, since both go somewhere. */
import Link from "next/link";
import { ArrowRight } from "lucide-react";

const BASE = "tap group inline-flex items-center justify-center gap-2.5 whitespace-nowrap font-semibold";

export default function CtaButton({
  href,
  variant = "solid",
  size = "lg",
  children,
  className = "",
}: {
  href: string;
  variant?: "solid" | "line";
  size?: "lg" | "sm";
  children: React.ReactNode;
  className?: string;
}) {
  const inPage = href.startsWith("#");
  const Tag = inPage ? "a" : Link;
  if (variant === "line") {
    return (
      <Tag
        href={href}
        className={`${BASE} nav-underline px-3.5 py-2 text-sm text-white/90 transition-colors duration-normal ease-standard hover:text-white ${className}`}
      >
        {children}
      </Tag>
    );
  }
  const sizing =
    size === "sm"
      ? "rounded-xl px-2.5 py-1.5 text-xs sm:px-3 sm:py-2 sm:text-sm lg:px-4"
      : "rounded-2xl px-6 py-3.5 text-base";
  return (
    <Tag
      href={href}
      className={`${BASE} ${sizing} border border-white/35 bg-white/15 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.35)] backdrop-blur-md transition-[background-color,border-color] duration-normal ease-standard hover:border-white/60 hover:bg-white/25 ${className}`}
    >
      {children}
      <ArrowRight
        size={size === "sm" ? 13 : 15}
        aria-hidden="true"
        className={`transition-transform duration-normal ease-standard group-hover:translate-x-1 ${
          // The icon only earns its keep once the button has room to spare: skip it through the
          // tablet-width squeeze (the header's logo, menus and this button all compete there) and
          // bring it back once `lg` gives everything space again.
          size === "sm" ? "hidden lg:inline" : ""
        }`}
      />
    </Tag>
  );
}
