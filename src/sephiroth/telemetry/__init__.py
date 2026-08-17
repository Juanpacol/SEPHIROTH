"""Trace-based observability — SPEC-006, executing `ADR-009`.

`build_trace` projects a populated `RunState` into the persisted,
replayable `ExecutionTrace` contract (`sephiroth.contracts.trace`, defined
since Phase 0). `traced_span` records real spans for the `Executor.step`
and `Verifier.check` seams — see its docstring for the two seams
deliberately not instrumented this phase.
"""

from .build_trace import build_trace
from .span import traced_span

__all__ = ["build_trace", "traced_span"]
