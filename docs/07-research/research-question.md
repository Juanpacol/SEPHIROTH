# Research question

## Topic

> Design and evaluation of an **agentic runtime** based on dynamic planning,
> capability-based multi-agent orchestration, evidence retrieval and result
> verification, to improve the reliability and efficiency of LLM-based
> multi-agent systems.

## Main question

> **To what extent does an agentic runtime with dynamic planning,
> capability-based routing, evidence retrieval and result verification improve
> the reliability and efficiency of LLM-based multi-agent systems, compared with
> static orchestration architectures?**

Two words carry the weight:

- **Reliability** — grounded, verifiable, safe answers, and graceful behaviour
  under failure.
- **Efficiency** — the cost of that reliability, in latency, tokens, and calls.

The question is deliberately a trade-off question. "Does it help?" invites a yes;
"at what cost?" is answerable and falsifiable.

## Sub-questions

| ID | Question | Isolates |
|---|---|---|
| **RQ1** | Does dynamic routing reduce unnecessary agent and tool invocations versus static orchestration? | The router |
| **RQ2** | Does hybrid retrieval improve the quality and relevance of retrieved evidence? | The context engine |
| **RQ3** | Does claim-level verification reduce unsupported claims and improve grounding? | The verifier |
| **RQ4** | Do recovery mechanisms improve task completion when agents or tools fail? | The recovery engine |
| **RQ5** | Do these benefits persist across LLM providers? | The provider abstraction |
| **RQ6** | What latency, token, call and cost overhead do the reliability mechanisms introduce? | The whole system's price |

RQ6 exists to keep the others honest. RQ1–RQ5 could all come back positive while
the system is too slow or costly to use; without RQ6 that result would look like
a success.

## Why this question is worth asking

Multi-agent LLM systems are typically evaluated on answer quality alone, with
the orchestration treated as plumbing. The claim under test is that the
orchestration layer is not plumbing — that explicit control over planning,
grounding, verification and recovery produces measurably different behaviour
from the same underlying model.

If that claim is false, the honest finding is that a well-prompted single model
plus RAG is enough, and the added complexity is not justified. The ablation
design ([methodology.md](methodology.md)) is what makes that outcome reportable
rather than embarrassing.

## Falsifiability

The architecture would be judged **not** to have delivered if:

- dynamic routing selects the same agents as static routing on the benchmark
  (RQ1 null), **and**
- claim verification does not reduce unsupported claims (RQ3 null), **and**
- ablations show no component contributes measurably (all null).

That combination is a real possible outcome and is stated here in advance so it
cannot be quietly redefined later.
