import type { Metadata } from "next";
import { Manrope } from "next/font/google";
import "./globals.css";
import AppShell from "@/components/app-shell";
import Providers from "@/components/providers";

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-manrope",
});

export const metadata: Metadata = {
  title: "SEPHIROTH — Clinical AI",
  description:
    "Local-first AI decision support for healthcare professionals. Research and education use only.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={manrope.variable}>
      <body className="font-sans">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
