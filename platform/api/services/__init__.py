"""Business logic that more than one caller needs.

Until this package existed, logic lived inline in routers -- `dashboard.py` is
749 lines and `scheduling.py` is 1004 -- which is fine while exactly one route
needs a rule and becomes a correctness problem the moment a second one does.
Resolving an alert is the concrete case: it has to happen identically whether a
clinician clicks resolve on the alert or completes the task that represents it,
and the version that lived in the router could only be reached one way.

Conventions here, both inherited rather than invented:

- **A service never commits.** It stages work in the caller's transaction, the
  same discipline as `platform/api/workflows/memory.py::set_memory` and
  `src/sephiroth/workflows/events.py::emit`. Routers commit; the tick commits
  once at the end. A service that commits half of a request's work is a service
  that can leave the database in a state no code path intended.
- **Errors are domain errors, not HTTP ones.** A service raises
  `TaskTransitionError`; the router decides that means 409. Services do not
  import from FastAPI.
"""
