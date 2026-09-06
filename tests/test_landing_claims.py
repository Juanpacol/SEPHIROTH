"""The landing page makes claims. This checks the product still backs them.

A marketing page drifting away from the product is the ordinary way software
starts lying, and it is invisible from inside either half: the copy is
reviewed by whoever writes copy, the defaults are changed by whoever changes
defaults, and nothing sits between them. The page this replaces described the
product as it was eight phases ago.

Two kinds of check here. The first ties a specific promise to a specific
default, so flipping the default fails the build rather than quietly making the
page false. The second refuses claims a clinical product must never make,
whoever writes them.

Verifies AC-026-01, AC-026-02 (docs/specs/SPEC-026-landing.md).
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DICTIONARIES = {
    "en": REPO_ROOT / "platform/frontend/lib/i18n/dictionaries.en.ts",
    "es": REPO_ROOT / "platform/frontend/lib/i18n/dictionaries.es.ts",
}

_ENTRY = re.compile(r'^\s{2}"(marketing\.[^"]+)":\s*(".*?"),\s*$', re.MULTILINE)


def marketing_copy(language: str) -> dict:
    """Every `marketing.*` string, decoded the way TypeScript wrote it."""
    source = DICTIONARIES[language].read_text()
    out = {}
    for key, raw in _ENTRY.findall(source):
        try:
            out[key] = json.loads(raw)
        except json.JSONDecodeError:  # pragma: no cover - a line the regex mangled
            continue
    return out


@pytest.fixture(scope="module", params=sorted(DICTIONARIES))
def copy(request):
    strings = marketing_copy(request.param)
    assert strings, f"no marketing copy found in {request.param}"
    return strings


class TestThePrivacyPromiseIsTrue:
    """AC-026-01 — the page says nothing leaves by default. It has to be so.

    These are the two settings the claim rests on. Changing either without
    changing the copy makes the landing page a false statement about where
    patient data goes, which is the one kind of marketing error that matters.
    """

    def test_the_default_provider_is_local(self):
        from core.config import Settings

        assert Settings(_env_file=None, environment="development").llm_provider == "ollama"

    def test_patient_content_may_not_leave_by_default(self):
        from core.config import Settings

        assert Settings(_env_file=None, environment="development").ai_allow_phi is False

    def test_turning_on_a_cloud_model_does_not_by_itself_send_patient_data(self):
        """The copy says this in as many words: two settings, and the second is
        specifically about whether patient data may go there."""
        from sephiroth.models import ProviderInfo
        from sephiroth.models.egress import phi_egress_allowed

        class _Remote:
            def describe(self):
                return ProviderInfo(provider="gemini", model="m", local=False, endpoint="google")

        assert phi_egress_allowed(_Remote()) is False

    def test_the_clinical_columns_the_page_names_are_encrypted(self):
        """ "Notes, conditions, medications and allergies are encrypted"."""
        from core.crypto import EncryptedJSON, EncryptedText
        from data.schemas import ClinicalNote, Patient

        assert isinstance(ClinicalNote.__table__.c.content.type, EncryptedText)
        for column in ("conditions", "medications", "allergies", "lab_results"):
            assert isinstance(Patient.__table__.c[column].type, EncryptedJSON), column

    def test_reading_a_patient_is_recorded(self):
        """ "Opening a patient writes an access log entry"."""
        from data.schemas import PhiAccessLog

        assert {"user_id", "patient_id", "route", "method"} <= set(PhiAccessLog.__table__.c.keys())


#: The interactive demo, which quotes real guideline text and real lab values.
#: A "7%" there is an A1C target being cited, not a claim about the product --
#: exempting it by prefix keeps the rule below strict everywhere it means
#: something.
_WORKED_EXAMPLE = (
    "marketing.claim",
    "marketing.sample",
    "marketing.walkthrough",
    "marketing.abstention",
    "marketing.citationToggle",
)


class TestClaimsAClinicalProductMustNotMake:
    """AC-026-02.

    Running locally removes one specific exposure. It is not a compliance
    programme, and a reader who infers one from the other has been misled —
    so the page says that in as many words, and this makes sure nobody
    later removes the qualifier and keeps the claim.
    """

    #: Phrases that assert compliance rather than describe behaviour.
    FORBIDDEN = (
        "hipaa compliant",
        "hipaa-compliant",
        "cumple con hipaa",
        "cumple hipaa",
        "gdpr compliant",
        "gdpr-compliant",
        "cumple con gdpr",
        "cumple gdpr",
        "fda approved",
        "fda-approved",
        "aprobado por la fda",
        "clinically validated",
        "clínicamente validado",
        "diagnostica",
        "diagnoses patients",
    )

    def test_no_compliance_or_approval_is_claimed(self, copy):
        rendered = " ".join(copy.values()).lower()
        for phrase in self.FORBIDDEN:
            assert phrase not in rendered, f"the landing page claims {phrase!r}"

    def test_the_not_a_medical_device_notice_survives(self, copy):
        badge = copy["marketing.hero.badge"].lower()
        assert "medical device" in badge or "dispositivo médico" in badge

    def test_the_privacy_section_states_what_it_is_not(self, copy):
        disclaimer = copy["marketing.privacy.disclaimer"].lower()
        assert "hipaa" in disclaimer and "gdpr" in disclaimer
        # It has to be a denial, not a mention.
        assert any(word in disclaimer for word in ("not", "no es"))

    def test_no_invented_numbers(self, copy):
        """A percentage or a customer count on a landing page is a claim
        somebody has to be able to defend. There is no measurement behind one
        here, so there must not be one on the page."""
        for key, value in copy.items():
            if key.startswith(_WORKED_EXAMPLE):
                continue
            assert "%" not in value, f"{key} carries a percentage"
            assert not re.search(
                r"\b\d{2,}[,.]?\d*\s*(clinics|clínicas|doctors|médicos|users|usuarios)", value
            ), key


class TestTheCopyDescribesTheProductThatExists:
    """AC-026-03. The failure this rewrite fixed: the page sold the consultation copilot
    and never mentioned the inbox, the encounter, the results loop or local
    inference — all of which had shipped."""

    @pytest.mark.parametrize(
        "key",
        [
            "marketing.painPoints.scattered.solution",
            "marketing.painPoints.results.solution",
            "marketing.painPoints.notes.solution",
            "marketing.privacy.body",
            "marketing.day.step3.body",
        ],
    )
    def test_the_new_sections_are_written_in_both_languages(self, copy, key):
        assert copy.get(key, "").strip(), f"{key} is missing or empty"

    def test_the_replaced_copy_is_gone(self, copy):
        """Left behind, it would be dead weight the next editor has to guess
        about."""
        for stale in (
            "marketing.painPoints.lookups.problem",
            "marketing.painPoints.trust.problem",
            "marketing.trace.step1",
        ):
            assert stale not in copy, f"{stale} survived the rewrite"

    def test_the_results_promise_names_the_guard_that_backs_it(self, copy):
        """ "cannot be marked done until they have been told" is a real
        constraint (SPEC-024 B-8), not a turn of phrase."""
        from api.services.result_service import NEEDS_CONTACT

        assert NEEDS_CONTACT == "needs_patient_contact"
        promise = copy["marketing.painPoints.results.solution"].lower()
        assert "told" in promise or "avise" in promise

    def test_the_note_promise_names_the_gate_that_backs_it(self, copy):
        """ "Nothing reaches the chart until you sign it" is what
        `sign_encounter` enforces (ADR-016)."""
        from api.services.encounter_service import OPEN_STATUSES

        assert "draft" in OPEN_STATUSES
        promise = copy["marketing.painPoints.notes.solution"].lower()
        assert "sign" in promise or "firm" in promise
