"""Note scaffolding, and the text a visit becomes.

Both pure. The templates are deliberately not model output: a template a model
wrote would vary between visits, and the entire value of a template is that it
does not.

Verifies AC-023-06's template half (docs/specs/SPEC-023-clinical-encounter.md).
"""

import pytest

from sephiroth.clinical.templates import (
    SPECIALTIES,
    encounter_template,
    fallback_draft,
    render_note,
)


class TestTemplates:
    def test_every_specialty_fills_all_four_sections(self):
        for specialty in SPECIALTIES:
            prompts = encounter_template(specialty).as_dict()
            assert set(prompts) == {"subjective", "objective", "assessment", "plan"}
            assert all(text.strip() for text in prompts.values()), specialty

    def test_a_specialty_overrides_only_what_genuinely_differs(self):
        """A table restating the general text under five headings would be five
        places to edit for one change."""
        general = encounter_template("general")
        cardiology = encounter_template("cardiology")

        assert cardiology.subjective != general.subjective
        assert cardiology.assessment == general.assessment

    def test_an_unknown_specialty_degrades_to_general(self):
        """A typo in a specialty must not cost someone their note."""
        assert encounter_template("dermatologia").as_dict() == encounter_template("general").as_dict()
        assert encounter_template("").as_dict() == encounter_template("general").as_dict()

    def test_specialty_matching_ignores_case_and_padding(self):
        assert encounter_template(" Cardiology ").subjective == encounter_template("cardiology").subjective

    def test_psychiatry_asks_about_suicidal_ideation_explicitly(self):
        """A prompt that says "ask" is the difference between a checklist and a
        reminder to do the thing the checklist exists for."""
        assert "suicida" in encounter_template("psychiatry").subjective.lower()


class TestRenderedNote:
    def _note(self, **overrides):
        base = {
            "chief_complaint": "Cefalea",
            "vitals": {"systolic": 210, "diastolic": 120},
            "subjective": "Tres días de cefalea occipital.",
            "assessment": "Crisis hipertensiva.",
            "plan": "Losartán 50mg.",
        }
        base.update(overrides)
        return render_note(**base)

    def test_it_reads_in_the_order_a_clinician_writes(self):
        note = self._note()
        assert note.index("MOTIVO DE CONSULTA") < note.index("SUBJETIVO")
        assert note.index("SUBJETIVO") < note.index("OBJETIVO")
        assert note.index("OBJETIVO") < note.index("ANÁLISIS")
        assert note.index("ANÁLISIS") < note.index("PLAN")

    def test_vitals_lead_the_objective_section(self):
        """They are the measured part of the exam, so they belong with it
        rather than in a box of their own."""
        note = self._note(objective="Sin focalización.")
        objective = note.split("OBJETIVO\n")[1]
        assert objective.startswith("PA 210/120 mmHg")
        assert "Sin focalización." in objective

    def test_an_empty_section_is_omitted_not_printed_blank(self):
        """A note whose headings outnumber its content reads as though the
        visit was incomplete."""
        note = render_note(subjective="Solo esto.")
        assert "SUBJETIVO" in note
        assert "ANÁLISIS" not in note
        assert "PLAN" not in note

    def test_orders_are_listed_with_their_deadline(self):
        note = self._note(
            orders=[
                {"kind": "lab", "detail": "Creatinina", "due_in_days": 1},
                {"kind": "followup", "detail": "Control", "due_in_days": None},
            ]
        )
        assert "- Laboratorio: Creatinina (en 1 día)" in note
        assert "- Control: Control" in note

    def test_a_deadline_of_several_days_is_pluralised(self):
        note = self._note(orders=[{"kind": "lab", "detail": "Potasio", "due_in_days": 7}])
        assert "(en 7 días)" in note

    def test_an_order_with_no_detail_is_dropped(self):
        note = self._note(orders=[{"kind": "lab", "detail": "   "}])
        assert "ÓRDENES" not in note

    def test_patient_instructions_close_the_note(self):
        """The one part the patient leaves with, last where it is easy to find."""
        note = self._note(patient_instructions="Volver si empeora.")
        assert note.rstrip().endswith("Volver si empeora.")

    def test_an_entirely_empty_encounter_renders_as_nothing(self):
        assert render_note() == ""


class TestFallbackDraft:
    def test_it_keeps_the_clinicians_words_rather_than_guessing(self):
        """A wrong guess about which sentence is a plan costs more to correct
        than an honest blank costs to fill."""
        draft = fallback_draft("PA alta, inicio losartán", "general")

        assert draft["subjective"] == "PA alta, inicio losartán"
        assert draft["objective"] == ""
        assert draft["assessment"] == ""
        assert draft["plan"] == ""

    def test_it_carries_the_specialty_prompts_for_the_empty_sections(self):
        draft = fallback_draft("algo", "cardiology")
        assert draft["_prompts"]["objective"] == encounter_template("cardiology").objective

    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_no_text_yields_an_empty_draft_rather_than_an_error(self, text):
        assert fallback_draft(text)["subjective"] == ""
