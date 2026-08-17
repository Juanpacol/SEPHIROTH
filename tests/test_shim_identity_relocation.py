"""Identity tests for the three Phase-5 relocation shims (`risk_engine`,
`citation_guard`, `explainability`) — `docs/00-migration-charter.md` rule 2:
a shim must re-export the *same* object, not a copy, so patching either
path reaches the same code."""

import intelligence.agents.citation_guard as citation_guard_shim
import intelligence.agents.explainability as explainability_shim
import intelligence.agents.risk_engine as risk_engine_shim
import sephiroth.safety.risk as risk_engine_new
import sephiroth.telemetry.explain as explainability_new
import sephiroth.verification.citation_guard as citation_guard_new


def test_risk_engine_shim_is_identity():
    assert risk_engine_shim.assess_patient_risk is risk_engine_new.assess_patient_risk
    assert risk_engine_shim.assess_risk_level is risk_engine_new.assess_risk_level
    assert risk_engine_shim.LAB_RULES is risk_engine_new.LAB_RULES


def test_citation_guard_shim_is_identity():
    assert citation_guard_shim.audit is citation_guard_new.audit
    assert citation_guard_shim.sanitize is citation_guard_new.sanitize
    assert citation_guard_shim.CitationReport is citation_guard_new.CitationReport


def test_explainability_shim_is_identity():
    assert explainability_shim.build_explanation is explainability_new.build_explanation
