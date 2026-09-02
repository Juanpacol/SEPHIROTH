/** Renders a consultation answer as readable prose.
 *
 * Deliberately NOT a markdown parser. The answering agents are prompted for a
 * narrow shape (`CLINICIAN_VOICE` in `src/sephiroth/runtime/registry.py`):
 * prose, an occasional short bulleted list, and the odd bold run. Rendering
 * that with `whitespace-pre-wrap` left `**like this**` on screen as literal
 * asterisks, which is exactly the "reads like raw model output" problem the
 * prompt work is meant to fix. Pulling in a full markdown stack to cover a
 * handful of constructs would be a dependency and an XSS surface for no gain
 * — anything outside this subset is shown verbatim, never interpreted.
 */

interface Block {
  type: "paragraph" | "list";
  lines: string[];
}

const BULLET = /^\s*[-*•]\s+/;

/** Split into paragraph and list blocks, blank lines separating paragraphs. */
export function toBlocks(answer: string): Block[] {
  const blocks: Block[] = [];

  for (const rawLine of answer.split("\n")) {
    const line = rawLine.trim();
    const previous = blocks[blocks.length - 1];

    if (!line) {
      // A blank line closes whatever block was open.
      if (previous) blocks.push({ type: "paragraph", lines: [] });
      continue;
    }

    if (BULLET.test(line)) {
      const item = line.replace(BULLET, "");
      if (previous?.type === "list") previous.lines.push(item);
      else blocks.push({ type: "list", lines: [item] });
      continue;
    }

    if (previous?.type === "paragraph" && previous.lines.length > 0) previous.lines.push(line);
    else blocks.push({ type: "paragraph", lines: [line] });
  }

  return blocks.filter((block) => block.lines.length > 0);
}

/** `**bold**` runs; every other character is rendered as written. */
export function renderInline(text: string): React.ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      // Weight only, never a color of its own — emphasis inside a sentence
      // that also recolors makes the answer read as two different voices.
      <strong key={i} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    )
  );
}

export default function AnswerText({ answer }: { answer: string }) {
  return (
    <div className="space-y-2.5 leading-relaxed">
      {toBlocks(answer).map((block, i) =>
        block.type === "list" ? (
          <ul key={i} className="space-y-1.5">
            {block.lines.map((item, j) => (
              <li key={j} className="flex gap-2">
                <span aria-hidden className="mt-[0.45rem] h-1 w-1 shrink-0 rounded-full bg-muted" />
                <span>{renderInline(item)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>{renderInline(block.lines.join(" "))}</p>
        )
      )}
    </div>
  );
}
