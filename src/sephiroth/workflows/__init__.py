"""Pure, DB-free helpers for the workflow-automation substrate (SPEC-009).

Everything here is a plain function operating on primitive/dataclass
values -- no `data.*`/`core.*` import, no session, no I/O -- so it is
unit-testable the same way `platform/api/scheduling.py::expand_slots` is.
The DB-touching half (the tick engine, step handlers, routers) lives in
`platform/api/workflows/`, per ADR-010's runtime/clinical-app split.
"""
