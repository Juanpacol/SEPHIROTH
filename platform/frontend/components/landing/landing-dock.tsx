"use client";

/** Floating section-jump dock for the landing page, replacing the flat
 * text nav on scroll. Desktop only (Dock.css hides it under 640px) — the
 * sticky `LandingNav` header still carries the same links for mobile. */

import dynamic from "next/dynamic";
import { LayoutDashboard, ShieldCheck, Users, HelpCircle, LogIn } from "lucide-react";
import { useRouter } from "next/navigation";

const Dock = dynamic(() => import("@/components/effects/dock"), { ssr: false });

export default function LandingDock() {
  const router = useRouter();

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const items = [
    { icon: <LayoutDashboard size={20} />, label: "How it works", onClick: () => scrollTo("how-it-works") },
    { icon: <ShieldCheck size={20} />, label: "Safeguards", onClick: () => scrollTo("safeguards") },
    { icon: <Users size={20} />, label: "Agents", onClick: () => scrollTo("agents") },
    { icon: <HelpCircle size={20} />, label: "FAQ", onClick: () => scrollTo("faq") },
    { icon: <LogIn size={20} />, label: "Open the app", onClick: () => router.push("/login") },
  ];

  return <Dock items={items} />;
}
