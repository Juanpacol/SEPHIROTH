"""Abstention and input-facing safety — F-040/F-041 (SPEC-004)."""

from .abstention import ABSTAIN_THRESHOLD, PARTIAL_BANNER, PARTIAL_THRESHOLD, decide
from .output_safety import check_input
from .scope import check_scope

__all__ = [
    "ABSTAIN_THRESHOLD",
    "PARTIAL_BANNER",
    "PARTIAL_THRESHOLD",
    "check_input",
    "check_scope",
    "decide",
]
