# ADR-002 — MCP as the standard tool layer

**Status:** Accepted · **Date:** 2026-08-16 · **Phase:** 0 (records an existing decision)

## Context

Agents need tools: image analysis, drug interactions, guideline retrieval,
entity extraction. Each could be a plain Python function called directly.

## Decision

All tool access goes through **MCP** (Model Context Protocol) servers, run
in-process via FastMCP's in-memory transport.

## Rationale

- **One schema, two consumers.** A `@mcp.tool` declaration produces both the
  structured function-calling schema the model invokes *and* the
  natural-language catalog injected into the system prompt. Direct Python calls
  would need those maintained separately, and they would drift.
- **A boundary to enforce at.** Capability checks, permissions, timeouts and
  retries need a chokepoint. MCP gives one; scattered function calls do not.
  [ADR-004](ADR-004-capability-based-routing.md) depends on this.
- **In-process is cheap.** No subprocesses, no sockets — the protocol's
  discipline without its deployment cost.
- **It is the emerging standard**, so tools written here are portable outward
  and third-party servers are reachable inward.

## Consequences

Every tool pays a small indirection cost. In exchange there is exactly one place
where authorization happens — which is what made the Phase 0 hotfix a ten-line
change rather than an audit of every call site.

## Alternatives rejected

**Direct function calls** — no chokepoint, duplicated schemas.
**LangChain tools** — couples the tool layer to the framework
[ADR-001](ADR-001-remove-langgraph.md) removes.
