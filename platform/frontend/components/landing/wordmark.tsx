/** The name in the header, set in the display face in wide-tracked capitals (as the Anthropic and Ruby pages
 * set theirs), each letter its own span so that on hover they lift one after another. The letters are
 * hidden from assistive technology and the whole carries the name once. */
const NAME = "SEPHIROTH";

export default function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span
      aria-label={NAME}
      className={`inline-flex font-display font-semibold uppercase leading-none ${className}`}
    >
      {NAME.split("").map((letter, i) => (
        <span
          key={i}
          aria-hidden="true"
          style={{ transitionDelay: `${i * 22}ms` }}
          className="inline-block transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover/brand:-translate-y-[2px]"
        >
          {letter}
        </span>
      ))}
    </span>
  );
}
