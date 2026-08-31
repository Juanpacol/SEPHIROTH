"""Agent Auditor — automated post-hoc analysis of one `ExecutionTrace`.

Answers the questions a human would ask while eyeballing a trace by hand
(as done manually throughout this runtime audit): did routing select a
reasonable set of agents, did any agent call the same tool redundantly, did
tool calls go unused, and why did the run abstain (if it did). Consumes the
trace `build_trace.py` already produces — no new instrumentation needed.

Severity is informational, not a pass/fail gate (that's `intelligence.
evaluation`'s job) — this module surfaces things worth a human's attention.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List

from sephiroth.contracts import ExecutionTrace, VerificationStatus


@dataclass
class Finding:
    severity: str  # "info" | "warning" | "concern"
    category: str
    message: str


@dataclass
class AuditReport:
    trace_id: str
    findings: List[Finding] = field(default_factory=list)
    tool_calls_by_agent: Dict[str, int] = field(default_factory=dict)
    total_tool_calls: int = 0
    redundant_call_count: int = 0
    abstained: bool = False
    supported_claim_ratio: float | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "findings": [
                {"severity": f.severity, "category": f.category, "message": f.message} for f in self.findings
            ],
            "tool_calls_by_agent": self.tool_calls_by_agent,
            "total_tool_calls": self.total_tool_calls,
            "redundant_call_count": self.redundant_call_count,
            "abstained": self.abstained,
            "supported_claim_ratio": self.supported_claim_ratio,
        }


def _detect_redundant_calls(trace: ExecutionTrace) -> List[Finding]:
    """Same agent calling the same tool 2+ times in one run — the exact
    pattern found and fixed in `evidence`'s prompt during this audit
    (search reformulated 3-4x per consultation). Flags it generically so
    it surfaces again for any agent/tool, not just that one case."""
    findings: List[Finding] = []
    by_agent_tool: Dict[tuple, int] = Counter()
    for call in trace.tool_calls:
        by_agent_tool[(call.agent, call.tool)] += 1
    for (agent, tool), count in by_agent_tool.items():
        if count > 1:
            findings.append(
                Finding(
                    severity="warning",
                    category="redundant_tool_call",
                    message=f"{agent} called {tool} {count}x in one run — check for reformulated retries.",
                )
            )
    return findings


def _detect_unused_selected_agents(trace: ExecutionTrace) -> List[Finding]:
    """An agent was selected by routing but produced no content and made no
    tool calls — likely dead weight in this run (or a silent failure not
    surfaced as a `Failure`)."""
    findings: List[Finding] = []
    called_agents = {c.agent for c in trace.tool_calls}
    result_by_agent = {r.agent: r for r in trace.agent_calls}
    for agent in trace.selected_agents:
        result = result_by_agent.get(agent)
        made_tool_call = agent in called_agents
        has_content = bool(result and result.content.strip())
        if not made_tool_call and not has_content:
            findings.append(
                Finding(
                    severity="concern",
                    category="unused_selected_agent",
                    message=f"{agent} was selected by routing but produced no content and no tool calls.",
                )
            )
    return findings


def _detect_low_tool_usage(trace: ExecutionTrace) -> List[Finding]:
    """Flags when a selected agent that HAS declared tools never called
    any — the qwen2.5:14b pattern found in Fase 5's eval run (avg 0.59
    tool calls/case): an agent skipping tool calls it's instructed to
    make, answering from parametric knowledge instead."""
    findings: List[Finding] = []
    called_agents = {c.agent for c in trace.tool_calls}
    for agent in trace.selected_agents:
        if agent == "coordinator":
            continue
        if agent not in called_agents:
            findings.append(
                Finding(
                    severity="concern",
                    category="skipped_tool_call",
                    message=f"{agent} was selected but made zero tool calls — check if it answered "
                    "from unverified parametric knowledge instead of retrieved evidence.",
                )
            )
    return findings


def _detect_unsupported_claims(trace: ExecutionTrace) -> List[Finding]:
    if not trace.verification or not trace.verification.claims:
        return []
    claims = trace.verification.claims
    unsupported = [
        c for c in claims if c.status in (VerificationStatus.UNSUPPORTED, VerificationStatus.CONTRADICTED)
    ]
    if unsupported:
        by_agent = defaultdict(list)
        for c in unsupported:
            by_agent[c.originating_agent or "unknown"].append(c.text[:80])
        findings = []
        for agent, texts in by_agent.items():
            findings.append(
                Finding(
                    severity="concern",
                    category="unsupported_claim",
                    message=f"{agent} produced {len(texts)} unsupported/contradicted claim(s) not "
                    f'traceable to retrieved evidence — first: "{texts[0]}"',
                )
            )
        return findings
    return []


def _detect_abstention(trace: ExecutionTrace) -> List[Finding]:
    if trace.abstention is None or trace.abstention.status.value == "answer":
        return []
    return [
        Finding(
            severity="info",
            category="abstention",
            message=f"Run abstained (status={trace.abstention.status.value}, "
            f"reason={trace.abstention.reason or 'n/a'}) — see unsupported-claim findings above for why.",
        )
    ]


def audit_trace(trace: ExecutionTrace) -> AuditReport:
    """Runs every check against one trace and returns a structured report."""
    findings: List[Finding] = []
    findings.extend(_detect_redundant_calls(trace))
    findings.extend(_detect_unused_selected_agents(trace))
    findings.extend(_detect_low_tool_usage(trace))
    findings.extend(_detect_unsupported_claims(trace))
    findings.extend(_detect_abstention(trace))

    tool_calls_by_agent: Dict[str, int] = Counter(c.agent for c in trace.tool_calls)
    redundant = sum(
        1
        for (agent, tool) in {(c.agent, c.tool) for c in trace.tool_calls}
        if sum(1 for c in trace.tool_calls if c.agent == agent and c.tool == tool) > 1
    )

    supported_claim_ratio = None
    if trace.verification and trace.verification.claims:
        total = len(trace.verification.claims)
        supported = sum(1 for c in trace.verification.claims if c.status == VerificationStatus.SUPPORTED)
        supported_claim_ratio = round(supported / total, 4) if total else None

    return AuditReport(
        trace_id=trace.trace_id,
        findings=findings,
        tool_calls_by_agent=dict(tool_calls_by_agent),
        total_tool_calls=len(trace.tool_calls),
        redundant_call_count=redundant,
        abstained=trace.abstention is not None and trace.abstention.status.value != "answer",
        supported_claim_ratio=supported_claim_ratio,
    )


__all__ = ["AuditReport", "Finding", "audit_trace"]
