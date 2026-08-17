# Methodology

How the [hypotheses](hypotheses.md) get tested. Written now, before results
exist, so the design cannot be retrofitted to whatever the numbers turn out to
be.

## Design

Four systems, one benchmark, identical evaluation harness.

| System | Architecture | Isolates |
|---|---|---|
| **A** | Question → LLM → answer | The model alone |
| **B** | Question → RAG → LLM → answer | The value of retrieval |
| **C** | Question → coordinator → fixed agents → synthesis | The value of multi-agent, statically orchestrated |
| **D** | SEPHIROTH: analyze → plan → route → execute → verify → safety | The value of the runtime |

C is not hypothetical — it is the system as it exists today, which is why the
pre-migration behaviour is preserved by characterization tests rather than
discarded. **The baseline is a real artifact, not a reconstruction.**

## Ablations

D minus one mechanism at a time. Each answers "what did this component actually
buy?"

`D − dynamic routing` · `D − claim verification` · `D − recovery` ·
`D − abstention` · `D − hybrid retrieval` · `D − safety layer`

Ablation is the part that distinguishes a contribution from added complexity. A
component whose removal changes no metric has not earned its place, and
[vision.md](../00-project/vision.md)'s guiding rule says so explicitly.

## Benchmark

Target 200–500 cases, versioned, across eight categories:

`normal` · `multi-hop` · `paraphrased` · `adversarial` · `unsupported` ·
`safety-critical` · `tool-failure` · `conflicting-evidence`

The last three exist because they are the only way to test H3, H4 and abstention.
A benchmark of answerable questions cannot measure whether a system knows when
**not** to answer.

Today's 27-case set (15 golden, 8 paraphrase, 4 adversarial-negative) is the
seed. Every release documents source, construction method, expected outputs,
evidence, evaluation criteria, and limitations.

## Metrics

| Family | Metrics |
|---|---|
| Retrieval | Recall@1/3/5, MRR, NDCG |
| Generation | Answer correctness, faithfulness, groundedness |
| Evidence | Citation precision, citation recall, evidence coverage |
| Verification | Claim support rate, unsupported claim rate, contradiction detection rate |
| Agentic | Agent selection accuracy, tool selection accuracy, tool success rate, recovery success rate, unnecessary invocation rate |
| Safety | Unsafe answer rate, unsupported high-risk claim rate, abstention rate, **abstention precision**, policy violation rate |
| Performance | p50/p95/p99 latency, tokens, LLM calls, tool calls, cost per query |

**Abstention precision matters more than abstention rate.** A system that
abstains on everything scores a perfect unsafe-answer rate and is useless. The
pair must always be reported together.

## Instrument

The **execution trace** is the measurement instrument. Every metric above is
computed from persisted traces rather than from instrumented one-off runs, which
is why Phase 5 is a prerequisite for the research effort rather than a nicety.

A trace records model versions, so a run against a different provider is never
mistaken for a repeat of the same experiment.

## Failure analysis

Every failure is classified into the closed taxonomy (`PLANNING`, `ROUTING`,
`AGENT`, `TOOL`, `RETRIEVAL`, `EVIDENCE`, `VERIFICATION`, `SAFETY`, `MODEL`,
`RECOVERY`) and, for each, we record: what happened, why, which component
failed, whether the runtime recovered, what recovery cost, and whether it
improved final quality.

The taxonomy is closed and enforced at the type level, so failures aggregate by
component instead of becoming anecdotes.

## Reproducibility

- Deterministic offline mode for everything not requiring a live model.
- Dataset and transcript hashes committed; a changed input with unchanged
  recorded results fails the build as **stale** rather than silently reporting
  outdated numbers. This gate already exists.
- Provider, model id and configuration recorded per run.
- Seeds fixed where the pipeline permits.

LLM non-determinism is real and is not hidden: any live-model metric is reported
with its variance across repeated runs, not as a single number.

## Threats to validity

| Threat | Mitigation |
|---|---|
| Benchmark authored by the same person who built the system | Adversarial and negative categories authored first, before the mechanism that handles them |
| Small corpus (22 documents) inflates retrieval scores | Report corpus size with every retrieval metric; treat H2 as corpus-bounded |
| Single clinical domain | Framed as a case study; generality is argued from the capability mechanism, not claimed from results |
| LLM-as-judge is itself unreliable | Report judge agreement against a deterministic proxy; never use the judge as sole evidence |
| Provider quota shapes what gets run | Record it as an experimental constraint rather than silently sampling |
