import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/app-shell";
import Providers from "@/components/providers";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import { AUTH_GATE_SCRIPT } from "@/lib/auth-gate";

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-manrope",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: "SEPHIROTH — Clinical AI",
  description:
    "Local-first AI decision support for healthcare professionals. Research and education use only.",
  openGraph: {
    title: "SEPHIROTH — Clinical AI",
    description: "Clinical decisions, with the reasoning shown.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "SEPHIROTH — Clinical AI",
    description: "Clinical decisions, with the reasoning shown.",
  },
};

/**
 * Next injects a default viewport when none is declared, so this exists for one
 * reason: `viewportFit: "cover"`. Without it every `env(safe-area-inset-*)` in
 * the stylesheet resolves to 0 and the bottom tab bar sits under the iOS home
 * indicator.
 *
 * Deliberately no `maximumScale`/`userScalable` — blocking pinch-zoom is an
 * accessibility failure, and in a clinical app it's not negotiable.
 *
 * Deliberately no `themeColor` either: Next can only condition it on
 * `prefers-color-scheme`, but the theme here is class-based (lib/theme.ts +
 * `.dark`), so a user with a light OS and a dark app would get the wrong
 * browser chrome. The correct fix is a `<meta name="theme-color">` updated from
 * wherever the class is toggled, not this export.
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={manrope.variable}>
      <head>
        {/* Applies the saved theme before first paint — avoids a flash of the wrong theme. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        {/* Logged-in visitors to "/" bounce to their dashboard/portal before
            the landing page ever paints — see lib/auth-gate.ts. */}
        <script dangerouslySetInnerHTML={{ __html: AUTH_GATE_SCRIPT }} />
      </head>
      <body className="font-sans">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
