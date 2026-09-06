"""Vitals: what may be stored, and what is worth saying about it.

The two bounds are the whole design, and the test that matters most is the one
asserting they are different. A systolic of 900 is a broken cuff and must never
enter the chart; a systolic of 210 is a hypertensive emergency and must. A
validator that treats "outside normal" as "invalid" refuses exactly the reading
the feature exists to capture.

Verifies AC-023-05 (docs/specs/SPEC-023-clinical-encounter.md).
"""

import pytest

from sephiroth.clinical.vitals import (
    VITAL_SPECS,
    VitalError,
    format_vitals,
    parse_blood_pressure,
    validate_vitals,
    vital_findings,
)


class TestWhatMayBeStored:
    def test_a_normal_set_round_trips_as_numbers(self):
        stored = validate_vitals(
            {"systolic": "120", "diastolic": "80", "temperature": "36.8", "heart_rate": 72}
        )
        assert stored == {"systolic": 120.0, "diastolic": 80.0, "temperature": 36.8, "heart_rate": 72.0}

    def test_an_alarming_but_real_reading_is_stored(self):
        """The case the feature exists for. Refusing it would refuse the
        emergency."""
        assert validate_vitals({"systolic": "210", "diastolic": "120"}) == {
            "systolic": 210.0,
            "diastolic": 120.0,
        }

    def test_a_reading_no_body_produces_is_refused(self):
        with pytest.raises(VitalError) as exc:
            validate_vitals({"systolic": "900"})
        assert "outside anything a body produces" in str(exc.value)

    def test_an_unknown_key_is_refused_by_name(self):
        """A vital nobody wrote a range for is a number nobody can interpret."""
        with pytest.raises(VitalError) as exc:
            validate_vitals({"mood": "7"})
        assert "mood" in str(exc.value)

    def test_a_non_number_is_refused(self):
        with pytest.raises(VitalError):
            validate_vitals({"heart_rate": "rápido"})

    def test_empty_fields_are_absent_rather_than_zero(self):
        """An untouched form field sends `""`. Storing that as 0 would record a
        temperature of zero degrees on every visit that did not take one."""
        assert validate_vitals({"systolic": "120", "temperature": "", "glucose": None}) == {"systolic": 120.0}

    def test_a_visit_that_measured_nothing_stores_nothing(self):
        assert validate_vitals({}) == {}

    def test_values_are_rounded_to_their_spec(self):
        assert validate_vitals({"heart_rate": "72.4"}) == {"heart_rate": 72.0}
        assert validate_vitals({"temperature": "36.85"})["temperature"] == pytest.approx(36.9, abs=0.05)


class TestWhatIsWorthSaying:
    def test_normal_readings_produce_no_findings(self):
        assert vital_findings({"systolic": 118, "diastolic": 76, "heart_rate": 70}) == []

    def test_an_abnormal_reading_is_flagged_with_its_normal_range(self):
        (finding,) = vital_findings({"oxygen_saturation": 88})

        assert finding.key == "oxygen_saturation"
        assert finding.severity == "high"
        assert "88" in finding.detail
        assert "94" in finding.detail, "a flag that does not say what normal is cannot be judged"

    def test_severity_scales_with_distance_from_normal(self):
        """One rule for every vital: a hand-written cutoff per vital would be
        ten numbers to keep in step."""
        (slightly_high,) = vital_findings({"systolic": 140})
        (very_high,) = vital_findings({"systolic": 210})

        assert slightly_high.severity == "medium"
        assert very_high.severity == "high"

    def test_weight_and_height_are_never_flagged(self):
        """Flagging every adult's weight would be noise, and noise is what
        makes people stop reading flags."""
        assert vital_findings({"weight": 120.0, "height": 150}) == []

    def test_a_stored_value_that_no_longer_parses_is_skipped_not_raised(self):
        """Read paths must survive data written under an older spec."""
        assert vital_findings({"systolic": "n/a", "diastolic": 76}) == []

    def test_findings_never_raise_on_junk(self):
        assert vital_findings({}) == []
        assert vital_findings(None) == []
        assert vital_findings({"unknown_key": 5}) == []


class TestHowItReads:
    def test_blood_pressure_is_one_reading_not_two(self):
        assert "PA 120/80 mmHg" in format_vitals({"systolic": 120, "diastolic": 80})

    def test_a_lone_systolic_is_not_rendered_as_a_pair(self):
        line = format_vitals({"systolic": 120})
        assert "/" not in line
        assert "120" in line

    def test_other_vitals_carry_their_units(self):
        line = format_vitals({"temperature": 38.4, "oxygen_saturation": 92})
        assert "38.4 °C" in line
        assert "92 %" in line

    def test_nothing_measured_renders_as_nothing(self):
        assert format_vitals({}) == ""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("120/80", (120.0, 80.0)),
            (" 210 / 120 ", (210.0, 120.0)),
            ("120", None),
            ("", None),
            ("a/b", None),
        ],
    )
    def test_a_blood_pressure_typed_as_one_thing_parses_as_two(self, text, expected):
        """A form with two boxes for a blood pressure is a form that gets one
        box filled."""
        assert parse_blood_pressure(text) == expected


class TestTheSpecItself:
    def test_every_clinical_range_sits_inside_its_physiological_range(self):
        """A normal range wider than what a body produces would make the two
        bounds meaningless."""
        for spec in VITAL_SPECS.values():
            assert spec.physiological[0] <= spec.clinical[0]
            assert spec.clinical[1] <= spec.physiological[1]

    def test_every_range_is_ordered(self):
        for spec in VITAL_SPECS.values():
            assert spec.physiological[0] < spec.physiological[1]
            assert spec.clinical[0] <= spec.clinical[1]

    def test_every_vital_has_a_label_a_clinician_would_recognise(self):
        for key, spec in VITAL_SPECS.items():
            assert spec.key == key
            assert spec.label.strip()
