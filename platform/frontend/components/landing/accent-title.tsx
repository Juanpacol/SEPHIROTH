/** A section heading in the hero's manner: the display face, in capitals, with the last words set in a lighter
 * blue. Words are separate spans only so the last ones can be coloured; a space between them keeps the text read
 * and copied as a sentence. Static: only the hero's own headline comes in word by word. */
import { Fragment } from "react";

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
  return (
    <Tag className={`font-display font-light uppercase leading-[0.95] ${className}`}>
      {words.map((word, i) => {
        const accent = i >= words.length - accentWords;
        return (
          <Fragment key={i}>
            <span data-accent={accent || undefined} className={accent ? ACCENT_BLUE : ""}>
              {word}
            </span>{" "}
          </Fragment>
        );
      })}
    </Tag>
  );
}
