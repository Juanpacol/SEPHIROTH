/** Agents are named by what they do. The id (`drug-safety`) is for the wire; this
 * is what a person reads. Both spellings of an id appear on the wire
 * (`drug-safety` / `drug_safety`), and an id saved before a rename, or one this
 * build has never heard of, is shown as it came: a label is never worth an error. */
const LABEL_KEYS: Record<string, string> = {
  radiology: "agents.radiology",
  "drug-safety": "agents.drugSafety",
  evidence: "agents.evidence",
};

export function agentLabel(id: string, t: (key: string) => string): string {
  const key = LABEL_KEYS[id.replace(/_/g, "-")];
  return key ? t(key) : id;
}
