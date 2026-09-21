"""SPEC-029 AC-029-03: `enable_single_agent_mode` and `enable_dynamic_planner`
are removed from `Settings`, not just defaulted off — the single
consultation path (`intent_router` → one specialist → answer) is
unconditional once `laboratory`/`coordinator`/the fan-out are gone, so there
is no longer a second mode to flag between.
"""

from core.config import Settings


def test_enable_single_agent_mode_field_is_removed():
    assert "enable_single_agent_mode" not in Settings.model_fields


def test_enable_dynamic_planner_field_is_removed():
    assert "enable_dynamic_planner" not in Settings.model_fields
