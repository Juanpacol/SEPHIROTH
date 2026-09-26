"""SPEC-031: every risk flag explains itself in structured fields.

`rule_code` + `factors` let the dashboard draw "value vs threshold" and
translate the reason without parsing the English `detail` string, which stays
byte-identical because alert de-duplication keys on the label.
"""

import pytest

from sephiroth.safety.risk import LAB_RULES, assess_patient_risk, bp_abnormality


def _firing_value(rule) -> float:
    return {
        ">": rule.threshold + 0.1,
        "<": rule.threshold - 0.1,
        "≥": rule.threshold,
    }[rule.comparator]


def _just_missing_value(rule) -> float:
    return {
        ">": rule.threshold,
        "<": rule.threshold,
        "≥": rule.threshold - 0.01,
    }[rule.comparator]


@pytest.mark.parametrize(
    "test_name, index",
    [(test_name, i) for test_name, rules in LAB_RULES.items() for i in range(len(rules))],
)
def test_every_lab_rule_declares_the_threshold_its_predicate_uses(test_name, index):
    """AC-031-01: a firing value yields the rule's code and one factor with the
    declared comparator/threshold/unit; the declared threshold is exactly where
    the predicate flips (B-1, B-2)."""
    predicate, rule = LAB_RULES[test_name][index]
    value = _firing_value(rule)
    assert predicate(value), f"{rule.code}: declared threshold does not fire its own predicate"
    assert not predicate(_just_missing_value(rule)), (
        f"{rule.code}: predicate fires past the declared threshold"
    )

    flags = [f for f in assess_patient_risk({test_name: str(value)}) if f["label"] == rule.label]
    assert len(flags) == 1
    flag = flags[0]
    assert flag["rule_code"] == rule.code
    assert flag["factors"] == [
        {
            "test": test_name,
            "value": value,
            "comparator": rule.comparator,
            "threshold": rule.threshold,
            "unit": rule.unit,
        }
    ]


def test_rule_codes_are_unique_snake_case():
    """AC-031-01: rule codes are stable translation keys, one per rule."""
    codes = [rule.code for rules in LAB_RULES.values() for _, rule in rules]
    assert len(codes) == len(set(codes))
    assert all(code == code.lower() and " " not in code for code in codes)


@pytest.mark.parametrize(
    "labs",
    [{"bp_systolic": "170.0 mm[Hg]", "bp_diastolic": "95.0 mm[Hg]"}, {"bp": "170/95"}],
)
def test_hypertensive_flag_carries_both_pressures(labs):
    """AC-031-02: the BP flag names both factors, whichever one fired (B-3)."""
    (flag,) = [f for f in assess_patient_risk(labs) if f["label"] == "Hypertensive range"]
    assert flag["rule_code"] == "hypertensive_range"
    assert flag["factors"] == [
        {"test": "bp_systolic", "value": 170.0, "comparator": "≥", "threshold": 160.0, "unit": "mmHg"},
        {"test": "bp_diastolic", "value": 95.0, "comparator": "≥", "threshold": 100.0, "unit": "mmHg"},
    ]


def test_interaction_flag_names_the_pair_without_factors():
    """AC-031-03: a drug interaction has no numeric factor, only the pair."""
    (flag,) = [f for f in assess_patient_risk({}, ["warfarin", "aspirin"]) if f["source"] == "drug"]
    assert flag["rule_code"] == "drug_interaction"
    assert flag["factors"] == []
    assert sorted(flag["drugs"]) == ["aspirin", "warfarin"]


@pytest.mark.parametrize(
    "labs, meds, expected",
    [
        (
            {"potassium": "6.8 mEq/L"},
            [],
            {
                "source": "lab",
                "label": "Hyperkalemia",
                "severity": "high",
                "detail": "Potassium 6.8 mEq/L (> 5.5)",
            },
        ),
        (
            {"bmi": "32"},
            [],
            {
                "source": "lab",
                "label": "Obesity",
                "severity": "medium",
                "detail": (
                    "BMI 32.0 (≥ 30) — raises risk of diabetes, high blood pressure, and joint problems."
                ),
            },
        ),
        (
            {"bp": "170/95"},
            [],
            {
                "source": "lab",
                "label": "Hypertensive range",
                "severity": "medium",
                "detail": "BP 170/95 (≥ 160/100)",
            },
        ),
        (
            {},
            ["warfarin", "aspirin"],
            {
                "source": "drug",
                "label": "Interaction: aspirin + warfarin",
                "severity": "high",
                "detail": "Additive anticoagulation markedly increases bleeding risk.",
            },
        ),
    ],
)
def test_existing_flag_fields_are_unchanged(labs, meds, expected):
    """AC-031-04: structured fields are additive; label/detail/severity/source
    stay byte-identical, so alert dedupe and auto-resolve are unaffected (B-4)."""
    (flag,) = assess_patient_risk(labs, meds)
    assert {key: flag[key] for key in expected} == expected


def test_threshold_helpers_keep_their_verdicts():
    """AC-031-04: the persisted is_abnormal/is_critical path is untouched."""
    assert bp_abnormality(185, 112) == (True, True)
    assert bp_abnormality(120, 80) == (False, False)
