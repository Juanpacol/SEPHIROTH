# Hypotheses

Each hypothesis names the mechanism, the metric that tests it, and the
architecture phase that must exist first. Nothing here is measurable before its
phase lands, which is why evaluation is a separate effort.

| ID | Hypothesis | Primary metric | Needs phase | RQ |
|---|---|---|---|---|
| **H1** | Dynamic routing reduces unnecessary agent and tool invocations versus static orchestration | Unnecessary agent invocation rate; tool calls per query | 3 | RQ1 |
| **H2** | Hybrid retrieval outperforms single-strategy retrieval | Recall@k, MRR, NDCG | 4 | RQ2 |
| **H3** | Claim-level verification reduces unsupported claims and increases grounding | Unsupported claim rate; claim support rate; citation precision | 4 | RQ3 |
| **H4** | Recovery mechanisms increase task completion under induced failure | Recovery success rate; completion rate under fault injection | 3 | RQ4 |
| **H5** | Reliability improvements persist across LLM providers | All of the above, per provider | 1 | RQ5 |
| **H6** | Reliability mechanisms improve grounding and safety while introducing measurable latency and compute overhead | p50/p95 latency; tokens; LLM calls; cost per query | 5 | RQ6 |

## Reading H6

H6 is stated as a **conjunction, not a hope**: it predicts both an improvement
*and* a cost. It is confirmed by finding overhead, not by finding none. A result
showing large reliability gains at negligible cost would be a reason to suspect
the measurement, not to celebrate.

## Null results worth reporting

| If | Then the honest finding is |
|---|---|
| H1 null | Static routing was already near-optimal for this domain's task distribution; dynamic routing's value lies in generality, not efficiency — and generality is not what was measured |
| H2 null | The seed corpus is too small or too lexically distinctive for retrieval strategy to matter; the result is about the corpus, not the method |
| H3 null | Citation-provenance checking already captured most of the benefit, and claim-level verification is not worth its latency |
| H4 null | The induced failure modes were unrepresentative of real ones |
| H5 null | The benefits are prompt-specific rather than architectural — the most damaging result for the thesis, and the one most worth stating plainly |
| H6 null | Either the overhead is genuinely negligible, or the instrumentation is not capturing it |

H5 is the hypothesis whose failure would most undermine the contribution. That
is precisely why the provider abstraction is Phase 1: the experiment is designed
to be runnable early, not deferred until it is too late to change course.

## Confidence is a measurement, not a claim

The confidence value in an `AbstentionDecision` must be **derived from
observable signals** — evidence coverage, citation validity, agent agreement,
retrieval relevance, contradiction count, verification status — never taken from
an LLM's self-report.

The exact formulation is itself an experiment. It is documented and varied, not
assumed correct. An unmeasured confidence score is one of the things
[scope.md](../00-project/scope.md) rules out.
