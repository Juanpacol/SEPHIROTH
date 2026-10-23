"use client";

/** A section heading in the hero's manner: the display face, in capitals, with the last words set in a lighter
 * blue. Words are separate spans so the last ones can be coloured and so they can come in one after another as
 * the heading is first scrolled to (the hero's own headline does the same on load). A space between the words
 * keeps the text read and copied as a sentence. */
import { Fragment } from "react";
import { useReveal } from "./reveal";

export const ACCENT_BLUE = "text-[#b6cfff]";

export default function AccentTitle({
  text,
  accentWords = 2,
  as: Tag = "h2",
  className = "",
}: {
  text: string;
  accentWords?: number;
  as?: "h1" | "h2" | "h3";
  className?: string;
}) {
  const words = text.split(" ");
  const { ref, state } = useReveal<HTMLHeadingElement>();
  return (
    <Tag
      ref={ref}
      data-reveal={state}
      className={`font-display font-light uppercase leading-[0.95] ${className}`}
    >
      {words.map((word, i) => {
        const accent = i >= words.length - accentWords;
        return (
          <Fragment key={i}>
            <span
              data-accent={accent || undefined}
              style={{ transitionDelay: state === "shown" ? `${i * 70}ms` : "0ms" }}
              className={`inline-block transition-[opacity,transform] duration-[800ms] ease-[cubic-bezier(0.22,1,0.36,1)] ${
                state === "hidden" ? "translate-y-[0.35em] opacity-0" : ""
              } ${accent ? ACCENT_BLUE : ""}`}
            >
              {word}
            </span>{" "}
          </Fragment>
        );
      })}
    </Tag>
  );
}
