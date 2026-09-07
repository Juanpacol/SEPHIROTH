"""How abnormal a result is, decided by arithmetic.

The order of the three checks is the rule, so the tests are ordered the same
way. The one that matters most is that a *critical* value is critical even when
it sits inside a laboratory's own reference interval: a range says what is
usual for that assay, and `LAB_RULES` says what is dangerous, and those are
different questions.

Verifies AC-024-02 (docs/specs/SPEC-024-results-loop.md).
"""

import pytest

from sephiroth.clinical.results import (
    REFERENCE_RANGES,
    TASK_SEVERITY_BY_RESULT,
    classify_imaging,
    classify_lab,
    deserves_a_task,
)
from sephiroth.safety.risk import LAB_RULES


class TestTheOrderOfTheChecks:
    def test_a_dangerous_value_is_critical(self):
        result = classify_lab("potassium", 6.2)

        assert result.severity == "critical"
        # `rule_key` (SPEC-021's stable dedup identity) isn't in this branch's
        # `LabRule` yet -- restoring that is a separate phase, so it's None
        # here rather than the eventual "lab.potassium.high".
        assert result.rule_key is None
        # Traceable to the threshold that fired: a severity nobody can check is
        # one they have to take on faith.
        assert "5.5" in result.reason

    def test_criticality_beats_a_generous_supplied_range(self):
        """A lab's reference interval says what is usual for that assay.
        `LAB_RULES` says what is dangerous. A wide interval must not make a
        dangerous value look normal."""
        result = classify_lab("potassium", 6.2, reference_low=3.0, reference_high=7.0)

        assert result.severity == "critical"

    def test_a_value_outside_the_supplied_range_is_abnormal(self):
        result = classify_lab("creatinine", 2.4, reference_low=0.6, reference_high=1.3)

        assert result.severity == "abnormal"
        assert result.reference_high == 1.3

    def test_the_supplied_range_wins_over_the_built_in_one(self):
        """The laboratory that ran the assay knows its own interval, and
        overriding it with a table in this repository would be this product
        second-guessing the lab."""
        built_in_low, _ = REFERENCE_RANGES["creatinine"]
        assert built_in_low == 0.6

        result = classify_lab("creatinine", 0.5, reference_low=0.4, reference_high=1.1)

        assert result.severity == "normal"

    def test_the_built_in_range_applies_when_none_is_supplied(self):
        assert classify_lab("sodium", 150.0).severity == "abnormal"
        assert classify_lab("sodium", 140.0).severity == "normal"

    def test_a_value_inside_the_range_is_normal(self):
        result = classify_lab("potassium", 4.1)

        assert result.severity == "normal"
        assert "3.5" in result.reason and "5.0" in result.reason


class TestAnUnknownTest:
    def test_it_is_recorded_rather_than_refused(self):
        """A clinic that runs a test this product has no range for still has
        the result. Losing it to protect a taxonomy is the wrong trade."""
        result = classify_lab("ferritina", 300.0)

        assert result.severity == "unclassified"
        assert "ferritina" in result.reason

    def test_it_still_becomes_work(self):
        """Somebody has to look at a number nothing can judge."""
        assert deserves_a_task(classify_lab("ferritina", 300.0))

    def test_a_supplied_range_rescues_it(self):
        result = classify_lab("ferritina", 300.0, reference_low=30.0, reference_high=400.0)

        assert result.severity == "normal"


class TestNameNormalisation:
    @pytest.mark.parametrize("name", ["Potassium", "potasio", "K+", "  POTASSIUM  ", "k"])
    def test_the_spellings_a_clinic_types_reach_one_rule(self, name):
        assert classify_lab(name, 6.2).severity == "critical"

    def test_an_alias_reaches_the_built_in_range_too(self):
        assert classify_lab("glicemia", 250.0).severity == "abnormal"


class TestReproducibility:
    def test_the_same_input_always_classifies_the_same_way(self):
        """B-3: no model is involved, so there is nothing to vary."""
        first = classify_lab("potassium", 6.2)
        second = classify_lab("potassium", 6.2)

        assert (first.severity, first.reason, first.rule_key) == (
            second.severity,
            second.reason,
            second.rule_key,
        )

    def test_boundaries_are_inclusive_of_normal(self):
        low, high = REFERENCE_RANGES["potassium"]

        assert classify_lab("potassium", low).severity == "normal"
        assert classify_lab("potassium", high).severity == "normal"


class TestImaging:
    @pytest.mark.parametrize(
        ("severity", "expected"),
        [("critical", "critical"), ("review", "abnormal"), ("none", "normal")],
    )
    def test_the_read_is_translated_not_re_derived(self, severity, expected):
        """There is no number to compare, and inventing a second opinion from a
        free-text finding is exactly the model-driven classification NG-3 rules
        out."""
        assert classify_imaging(severity).severity == expected

    def test_the_finding_becomes_the_reason(self):
        result = classify_imaging("review", "Nódulo de 8mm en lóbulo superior derecho")

        assert "Nódulo de 8mm" in result.reason

    def test_an_unknown_severity_is_unclassified_rather_than_guessed(self):
        assert classify_imaging("weird").severity == "unclassified"


class TestWhatBecomesWork:
    def test_a_normal_result_is_not_work(self):
        """Filing one anyway is how an inbox teaches people to skim, and the
        results that get missed are missed in an inbox nobody reads carefully."""
        assert not deserves_a_task(classify_lab("potassium", 4.1))

    @pytest.mark.parametrize("severity", ["critical", "abnormal", "unclassified"])
    def test_everything_else_is(self, severity):
        assert severity in TASK_SEVERITY_BY_RESULT

    def test_severity_maps_to_a_proportionate_sla(self):
        """An abnormal result is easy to miss, not an emergency."""
        assert TASK_SEVERITY_BY_RESULT["critical"] == "critical"
        assert TASK_SEVERITY_BY_RESULT["abnormal"] == "medium"


class TestTheTablesThemselves:
    def test_every_range_is_ordered(self):
        for test_name, (low, high) in REFERENCE_RANGES.items():
            assert low < high, test_name

    def test_every_test_with_a_critical_rule_also_has_a_range(self):
        """Otherwise a value that is merely abnormal falls through to
        `unclassified` on a test the product demonstrably knows about."""
        missing = sorted(set(LAB_RULES) - set(REFERENCE_RANGES))

        assert not missing, f"critical rules with no reference range: {missing}"
