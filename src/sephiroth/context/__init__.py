"""Context Engine — F-034/F-035 (SPEC-005).

Per-agent context views (`views.py`), lexical MMR reranking (`rerank.py`),
character-budget truncation (`budget.py`), and per-patient consultation
memory (`memory.py`).
"""

from .budget import truncate
from .memory import recent_consultation_summaries
from .rerank import mmr_rerank
from .views import context_for_agent, log_filtered_fields

__all__ = [
    "context_for_agent",
    "log_filtered_fields",
    "mmr_rerank",
    "recent_consultation_summaries",
    "truncate",
]
