import type { Metadata } from "next";
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
