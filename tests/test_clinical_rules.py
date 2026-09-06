"""Deterministic clinical rules, and alerts that do not repeat themselves.

Two things are held here. First, that a rule has an identity independent of
what it is called on screen — the deduplication key used to be the display
title, which means rewording a label would silently duplicate every open alert
in the system. Second, that an alert a clinician has *reviewed* but not
resolved is not filed again — nor one they resolved a few hours ago while the
condition persists. That was a live defect, and SPEC-020 made it worse by
turning `alert_refresh` from once-per-deploy into every six hours.

Every rule here is a lookup or a comparison. Nothing in this file asks a model
anything, and nothing should: the LLM explains and drafts, the rule decides.

Verifies AC-021-01, AC-021-02, AC-021-03, AC-021-04, AC-021-05
(docs/specs/SPEC-021-clinical-rules.md).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from data.schemas import Alert, Patient
from sephiroth.safety.alerts import RESOLVED_SUPPRESSION, generate_alerts_for_patient
from sephiroth.safety.risk import LAB_RULES, assess_patient_risk

# Only the alert-persistence class needs a database; the rule tests are pure,
# so the marker goes on that class rather than the module.


def _keys(flags):
    return {f["rule_key"] for f in flags}


class TestRuleIdentity:
    def test_every_rule_carries_a_stable_key_and_a_source(self):
        """A warning a clinician cannot trace back to its threshold is one they
        have to take on faith."""
        flags = assess_patient_risk(
            {"potassium": "6.2", "hba1c": "11", "bp": "170/105"},
            ["warfarina", "aspirina"],
            ["penicilina"],
        )
        assert flags
        for flag in flags:
            assert flag["rule_key"], flag
            assert flag["rule_source"], flag
            assert flag["kind"] in ("clinical", "administrative")

    def test_rule_keys_are_unique_across_the_whole_rule_set(self):
        keys = [rule.key for rules in LAB_RULES.values() for _, rule in rules]
        assert len(keys) == len(set(keys))

    def test_a_key_does_not_move_when_the_value_does(self):
        """Identity is the rule, not the reading. A potassium that drifts from
        6.2 to 6.8 is the same open problem, not a second one."""
        first = assess_patient_risk({"potassium": "6.2"})
        second = assess_patient_risk({"potassium": "6.8"})
        assert _keys(first) == _keys(second)
        assert first[0]["detail"] != second[0]["detail"]

    def test_a_drug_pair_has_one_identity_regardless_of_order(self):
        one = assess_patient_risk({}, ["warfarina", "aspirina"])
        other = assess_patient_risk({}, ["aspirina", "warfarina"])
        assert _keys(one) == _keys(other)


class TestNewRules:
    def test_a_medication_matching_a_recorded_allergy_is_flagged_high(self):
        flags = assess_patient_risk({}, ["Penicilina V 500mg"], ["penicilina"])

        conflict = [f for f in flags if f["rule_key"].startswith("allergy.conflict")]
        assert len(conflict) == 1
        # Not a matter of degree: a documented allergy against an active
        # prescription is always high.
        assert conflict[0]["severity"] == "high"
        assert "Penicilina V 500mg" in conflict[0]["label"]

    def test_dose_and_form_do_not_hide_an_allergy(self):
        assert assess_patient_risk({}, ["amoxicilina 875 mg tablet"], ["amoxicilina"])

    def test_an_unrelated_medication_is_not_flagged(self):
        assert not [
            f
            for f in assess_patient_risk({}, ["metformina 500mg"], ["penicilina"])
            if f["rule_key"].startswith("allergy.conflict")
        ]

    def test_a_very_short_allergy_entry_is_ignored_rather_than_matching_everything(self):
        """A recorded allergy of "e" would otherwise flag most of the formulary."""
        assert not [
            f
            for f in assess_patient_risk({}, ["metformina"], ["e"])
            if f["rule_key"].startswith("allergy.conflict")
        ]

    def test_the_same_drug_listed_twice_is_flagged_once(self):
        flags = assess_patient_risk({}, ["Metformina 500mg", "metformina", "Losartán 50mg"])

        duplicates = [f for f in flags if f["rule_key"].startswith("drug.duplicate")]
        assert len(duplicates) == 1
        assert "metformina" in duplicates[0]["rule_key"]

    def test_two_different_drugs_are_not_a_duplicate(self):
        assert not [
            f
            for f in assess_patient_risk({}, ["metformina", "losartán"])
            if f["rule_key"].startswith("drug.duplicate")
        ]

    def test_allergies_are_optional_so_every_old_call_site_still_works(self):
        """Two-argument callers get no allergy flags rather than an error."""
        assert assess_patient_risk({"potassium": "6.2"}, [])


@pytest.mark.asyncio
class TestAlertsDoNotRepeat:
    async def _patient(self, session, **kwargs):
        p = Patient(
            id=kwargs.pop("pid", "PCR1"),
            name="Rule Patient",
            age=61,
            sex="F",
            medical_record_number=f"MRN-{kwargs.pop('mrn', 'PCR1')}",
            **kwargs,
        )
        session.add(p)
        await session.commit()
        return p

    async def test_a_reviewed_alert_is_not_filed_again(self, db_session):
        """The defect: the dedup set only held `active` alerts, so an alert a
        clinician had reviewed but not resolved came straight back. Once per
        deploy before SPEC-020 made the refresh periodic; every six hours
        after."""
        patient = await self._patient(db_session, lab_results={"potassium": "6.2"}, medications=[])
        await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()

        alert = (await db_session.scalars(select(Alert))).one()
        alert.status = "reviewed"
        await db_session.commit()

        created = await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()

        assert created == []
        assert len((await db_session.scalars(select(Alert))).all()) == 1

    async def test_a_just_resolved_alert_is_not_raised_again_on_the_next_sweep(self, db_session):
        """The chronic case. Potassium that stays at 6.2 is not new information
        six hours after the clinician resolved it -- it is the same finding,
        and re-filing it is the flooding this phase exists to stop."""
        patient = await self._patient(
            db_session, pid="PCR2", mrn="PCR2", lab_results={"potassium": "6.2"}, medications=[]
        )
        await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()
        alert = (await db_session.scalars(select(Alert))).one()
        alert.status = "resolved"
        alert.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db_session.commit()

        created = await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()

        assert created == []
        assert len((await db_session.scalars(select(Alert))).all()) == 1

    async def test_a_resolved_alert_is_raised_again_once_the_window_passes(self, db_session):
        """Suppression is a delay, not a mute: a condition still true a week
        later is a recurrence the clinician should see again."""
        patient = await self._patient(
            db_session, pid="PCR5", mrn="PCR5", lab_results={"potassium": "6.2"}, medications=[]
        )
        await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()
        alert = (await db_session.scalars(select(Alert))).one()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        alert.status = "resolved"
        alert.resolved_at = now - RESOLVED_SUPPRESSION - timedelta(minutes=1)
        await db_session.commit()

        created = await generate_alerts_for_patient(db_session, patient, now=now)
        await db_session.commit()

        assert len(created) == 1

    async def test_the_alert_records_the_rule_and_its_threshold(self, db_session):
        patient = await self._patient(
            db_session, pid="PCR3", mrn="PCR3", lab_results={"potassium": "6.2"}, medications=[]
        )
        await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()

        alert = (await db_session.scalars(select(Alert))).one()
        assert alert.rule_key == "lab.potassium.high"
        assert alert.source == "K+ > 5.5 mEq/L"
        assert alert.kind == "clinical"

    async def test_an_alert_predating_rule_keys_still_dedupes(self, db_session):
        """Backfilling display strings into a machine key would invent
        identities that were never real, so old rows keep the old comparison."""
        patient = await self._patient(
            db_session, pid="PCR4", mrn="PCR4", lab_results={"potassium": "6.2"}, medications=[]
        )
        db_session.add(
            Alert(
                id="LEGACY1",
                patient_id=patient.id,
                category="lab",
                severity="high",
                title="Hyperkalemia",
                detail="",
                source="risk_engine",
                rule_key=None,
            )
        )
        await db_session.commit()

        created = await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()

        assert created == []

    async def test_an_allergy_conflict_becomes_its_own_alert(self, db_session):
        patient = await self._patient(
            db_session,
            pid="PCR5",
            mrn="PCR5",
            lab_results={},
            medications=["Penicilina V 500mg"],
            allergies=["penicilina"],
        )

        created = await generate_alerts_for_patient(db_session, patient)
        await db_session.commit()

        assert len(created) == 1
        assert created[0].severity == "high"
        assert created[0].category == "medication"


class TestCodedAllergyEntries:
    """A real allergy list is coded, not free text.

    Synthea — the corpus this repository imports — records SNOMED
    descriptions, so every entry arrives wrapped ("Allergy to penicillin").
    The rule compares against a medication name, which never carries that
    wrapper, so without unwrapping the whole rule is inert on every imported
    patient and fires only on the hand-seeded literal.
    """

    @pytest.mark.parametrize(
        "entry",
        [
            "Allergy to penicillin",
            "Allergic to penicillin",
            "Penicillin allergy",
            "Hypersensitivity to penicillin",
            "  Allergy to Penicillin  ",
        ],
    )
    def test_a_coded_allergy_entry_still_matches_the_medication(self, entry):
        flags = assess_patient_risk({}, ["Penicilina V 500mg", "penicillin v 500mg"], [entry])
        assert [f for f in flags if f["rule_key"].startswith("allergy.conflict")]

    def test_unwrapping_does_not_invent_a_match(self):
        assert not [
            f
            for f in assess_patient_risk({}, ["metformina 500mg"], ["Allergy to penicillin"])
            if f["rule_key"].startswith("allergy.conflict")
        ]

    def test_a_wrapper_with_nothing_left_after_it_is_ignored(self):
        """ "Allergy to e" must not become a bare "e" that matches the formulary."""
        assert not [
            f
            for f in assess_patient_risk({}, ["metformina"], ["Allergy to e", "allergy"])
            if f["rule_key"].startswith("allergy.conflict")
        ]
