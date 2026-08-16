# Threat model

Scope: the runtime and its clinical application, running on synthetic or public
data. **Not** a deployment threat model for real patient data — see
[privacy.md](privacy.md) for why that deployment is out of scope.

## Assets

| Asset | Why it matters |
|---|---|
| Clinical text and images in flight | Would be PHI in a real deployment |
| Consultation history | Per-user, reveals clinical reasoning about patients |
| API keys (`GEMINI_API_KEY`, `GROQ_API_KEY`, `JWT_SECRET`) | Account compromise, quota theft |
| Tool surface (imaging, drug data, retrieval) | Arbitrary invocation is arbitrary compute and file access |
| Execution traces | Aggregate clinical content if redaction fails |

## Threats and controls

| # | Threat | Control | State |
|---|---|---|---|
| T-1 | **Prompt injection in clinical text** drives an agent to invoke tools outside its scope | Whitelist enforced at dispatch, not just at schema advertisement | ✅ closed in phase 0 |
| T-2 | Injection extracts data via an unrelated tool | Same control; capability metadata narrows it further | ✅ / 📋 phase 2 |
| T-3 | **Fabricated citations** make an unsupported claim look sourced | Citation guard audits labels against real tool output | ✅ |
| T-4 | **Misattributed content** — real citation, wrong claim | Claim-level verification | 📋 phase 4 |
| T-5 | Unauthenticated tool access via `/api/medical/*` | Route through the tool runtime's permission layer | 📋 phase 2 (DEBT-004) |
| T-6 | Arbitrary local file read through the image preview endpoint | Hard-restricted to browser-renderable extensions | ✅ |
| T-7 | Secrets committed | `.env` gitignored; gitleaks blocking in CI | ✅ |
| T-8 | Weak `JWT_SECRET` in a deployed environment | `Settings` refuses to start in staging/production with a default or short secret | ✅ |
| T-9 | PHI leaking into logs or traces | Span attributes are an allow-list, enforced at construction | 🚧 contract done, emitters in phase 5 |
| T-10 | Dependency CVEs | `pip-audit` + `npm audit`, advisory | ✅ |
| T-11 | Quota exhaustion as denial of service | Rate limiter, bounded tool rounds, provider fallback | ✅ |
| T-12 | Model outputs an unsafe recommendation | Output safety engine and abstention | 📋 phase 4 — **the largest open gap** |

## Trust boundaries

1. **Browser → API.** JWT on every agent route. Not all of `/api/medical/*` yet (T-5).
2. **API → model provider.** Clinical content leaves the machine here. The
   irreducible boundary; see [privacy.md](privacy.md).
3. **Agent → tool.** The one that matters most for injection, because a model's
   output becomes a tool invocation. Closed at dispatch as of phase 0.
4. **Runtime → trace store.** Where redaction must hold.

## Assumed, not defended

- A trusted operator. No defence against a malicious administrator.
- Trusted MCP servers — all five are in-repo and in-process.
- No multi-tenancy: one clinician role, patients shared, consultations per-user.

## Why T-1 was fixed out of phase order

An agent's `allowed_tools` only filtered which schemas the model was *shown*.
`registry.execute` checked that a tool existed and nothing else. A model naming
another agent's tool — through hallucination or injected instructions in a
clinical note — had it executed.

Clinical text is untrusted input that reaches a model whose output selects tool
calls. That is a live path, so it was closed in Phase 0 rather than waiting for
Phase 2. Verified in the running container, not only in tests.
