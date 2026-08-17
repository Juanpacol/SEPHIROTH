import Link from "next/link";
import WingMark from "@/components/brand/wing-mark";
import { DISCLAIMER } from "@/lib/legal";

export default function LandingFooter() {
  return (
    <footer className="border-t border-line/60">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid gap-8 md:grid-cols-3">
          <div>
            <div className="flex items-center gap-2">
              <WingMark size={20} className="text-primary" />
              <span className="font-bold tracking-tight">SEPHIROTH</span>
            </div>
            <p className="mt-2 max-w-xs text-sm text-muted">
              Multi-agent AI decision support for clinicians, with the reasoning shown.
            </p>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">Product</div>
            <ul className="mt-2 space-y-1.5 text-sm">
              <li>
                <a href="#how-it-works" className="hover:text-primary">
                  How it works
                </a>
              </li>
              <li>
                <a href="#safeguards" className="hover:text-primary">
                  Safeguards
                </a>
              </li>
              <li>
                <a href="#agents" className="hover:text-primary">
                  Agents
                </a>
              </li>
            </ul>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">Get started</div>
            <ul className="mt-2 space-y-1.5 text-sm">
              <li>
                <Link href="/login" className="hover:text-primary">
                  Clinician sign in
                </Link>
              </li>
              <li>
                <Link href="/portal/claim" className="hover:text-primary">
                  Patient portal setup
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <p className="mt-10 text-xs text-muted">{DISCLAIMER}</p>
      </div>
    </footer>
  );
}
