import { Sparkles } from "lucide-react";

/** Sephiroth-gradient badge — marks content produced by an AI agent. */
export default function AgentBadge({ name }: { name: string }) {
  return (
    <span className="ai-badge">
      <Sparkles size={11} />
      {name}
    </span>
  );
}
