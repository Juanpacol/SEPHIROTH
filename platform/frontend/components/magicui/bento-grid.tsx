import { type ComponentPropsWithoutRef, type ReactNode } from "react";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

/** Vendored from magicui.design and restyled onto our own design tokens
 * instead of shadcn's neutral/background scale (`bg-background`,
 * `text-neutral-700`, ...) — swaps in `card`/`ink`/`muted`/`primary` so a
 * bento tile reads as a SEPHIROTH card, not a pasted-in template. Also
 * drops the `@radix-ui/react-icons` + shadcn `<Button>` dependencies the
 * original pulls in, in favor of lucide (already a dependency) and a plain
 * link styled to match. */

interface BentoGridProps extends ComponentPropsWithoutRef<"div"> {
  children: ReactNode;
  className?: string;
}

interface BentoCardProps extends ComponentPropsWithoutRef<"div"> {
  name: string;
  className?: string;
  background?: ReactNode;
  Icon: React.ElementType;
  description: string;
  href?: string;
  cta?: string;
}

const BentoGrid = ({ children, className, ...props }: BentoGridProps) => {
  return (
    <div className={cn("grid w-full auto-rows-[20rem] grid-cols-3 gap-4", className)} {...props}>
      {children}
    </div>
  );
};

const BentoCard = ({ name, className, background, Icon, description, href, cta, ...props }: BentoCardProps) => (
  <div
    className={cn(
      "group relative col-span-3 flex flex-col justify-end overflow-hidden rounded-squircle border border-line/60 bg-card shadow-card transition-all duration-300 ease-ios hover:-translate-y-0.5 hover:shadow-card-lg",
      className
    )}
    {...props}
  >
    {background && <div className="absolute inset-0">{background}</div>}

    <div className="relative z-10 flex flex-col gap-1.5 p-6">
      <div className="mb-1 inline-flex w-fit rounded-2xl bg-primary-soft p-2.5 text-primary transition-transform duration-300 ease-ios group-hover:scale-110">
        <Icon size={20} />
      </div>
      <h3 className="font-bold text-ink">{name}</h3>
      <p className="max-w-md text-sm text-muted">{description}</p>

      {href && cta && (
        <a
          href={href}
          className="mt-2 inline-flex w-fit items-center gap-1.5 text-sm font-semibold text-primary opacity-0 transition-opacity duration-200 group-hover:opacity-100"
        >
          {cta}
          <ArrowRight size={14} />
        </a>
      )}
    </div>
  </div>
);

export { BentoCard, BentoGrid };
