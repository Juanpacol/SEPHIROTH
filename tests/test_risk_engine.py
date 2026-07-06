"""Risk engine tests — deterministic rule table, no LLM or DB needed."""

from intelligence.agents.risk_engine import assess_patient_risk, assess_risk_level


def test_hypokalemia_flags_high():
    flags = assess_patient_risk({"potassium": "3.1 mEq/L"})
    assert any(f["label"] == "Hypokalemia" and f["severity"] == "high" for f in flags)
    assert assess_risk_level(flags) == "high"


def test_normal_labs_no_flags():
    flags = assess_patient_risk({"potassium": "4.2 mEq/L", "inr": "1.1", "hba1c": "5.6%"})
    assert flags == []
    assert assess_risk_level(flags) == "low"


def test_drug_interaction_flag_via_shared_logic():
    flags = assess_patient_risk({}, ["warfarin", "aspirin"])
    drug_flags = [f for f in flags if f["source"] == "drug"]
    assert len(drug_flags) == 1
    assert drug_flags[0]["severity"] == "high"  # major interaction → high
    assert "warfarin" in drug_flags[0]["label"]


def test_medium_only_flags_yield_medium_level():
    flags = assess_patient_risk({"hba1c": "9.5%"})
    assert all(f["severity"] == "medium" for f in flags)
    assert assess_risk_level(flags) == "medium"


def test_blood_pressure_parsing():
    assert assess_patient_risk({"bp": "138/86"}) == []
    flags = assess_patient_risk({"bp": "165/102"})
    assert any(f["label"] == "Hypertensive range" for f in flags)


def test_unparseable_values_ignored():
    flags = assess_patient_risk({"potassium": "pending", "inr": None, "unknown_lab": "7"})
    assert flags == []


def test_seed_patient_p002_profile_is_high_risk():
    # Mirrors the seeded P002: EF 35% (< 40) is high; digoxin+furosemide is moderate.
    flags = assess_patient_risk(
        {"bnp": "450 pg/mL", "ef": "35%", "inr": "2.4", "potassium": "3.4 mEq/L"},
        ["warfarin", "furosemide", "digoxin"],
    )
    assert assess_risk_level(flags) == "high"
    labels = {f["label"] for f in flags}
    assert "Reduced ejection fraction" in labels
    assert "Hypokalemia" in labels
    assert "Elevated BNP" in labels
