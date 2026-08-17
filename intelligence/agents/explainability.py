"""Shim — relocated to `src/sephiroth/telemetry/explain.py` (Phase 5).

Per `docs/00-migration-charter.md`'s shim rules: re-exports only, no logic.
Deleted the phase after this one, unless it becomes permanent.
"""

from sephiroth.telemetry.explain import build_explanation

__all__ = ["build_explanation"]
