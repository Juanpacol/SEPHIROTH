import LandingNav from "@/components/landing/landing-nav";
import LandingFooter from "@/components/landing/landing-footer";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <LandingNav />
      <main className="flex-1">{children}</main>
      <LandingFooter />
    </div>
  );
}
