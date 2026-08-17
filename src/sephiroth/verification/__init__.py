"""Claim-level verification — F-036 through F-039 (SPEC-004).

`citation_guard` audits citation *labels*; this package audits claim
*content* against retrieved evidence, feeding a confidence score that gates
`sephiroth.safety.abstention`.
"""

from .claims import extract_claims
from .confidence import compute_confidence
from .evidence import harvest_evidence
from .verify import verify_claims

__all__ = ["compute_confidence", "extract_claims", "harvest_evidence", "verify_claims"]
