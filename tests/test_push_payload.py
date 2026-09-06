"""What a push notification is allowed to say.

The first class is the one that matters. A push payload leaves this product's
control completely — the OS renders it on a locked screen, mirrors it to a
watch, reads it aloud in a car, and files it in a history that outlives the
application — and none of that is reached by the PHI column encryption
(ADR-014) or the egress gate (ADR-015).

So the test is not "the payload looks right". It is: given a notification whose
message contains a patient's name, a diagnosis and a value, the payload
contains none of them. And structurally, that there is no argument through
which a message could arrive at all.

Verifies AC-025-01 (docs/specs/SPEC-025-pwa-push.md).
"""

import inspect

import pytest

from api.workflows.push_payload import PAYLOAD_KEYS, SAFE_COPY, build_payload, safe_copy_for

PATIENT_MESSAGE = (
    "Ana Gómez (MRN-4471) tiene un potasio de 6.2 mEq/L — hiperkalemia grave, "
    "diagnóstico de insuficiencia renal crónica"
)
LEAKS = ["Ana", "Gómez", "MRN-4471", "6.2", "potasio", "hiperkalemia", "renal"]


class TestNoPatientContentEverLeaves:
    """AC-025-01."""

    @pytest.mark.parametrize("type_", sorted(SAFE_COPY))
    def test_no_payload_contains_anything_from_a_patient(self, type_):
        payload = build_payload(notification_id="N1", type_=type_)

        rendered = " ".join(str(value) for value in payload.values()).lower()
        for fragment in LEAKS:
            assert fragment.lower() not in rendered, f"{type_} leaked {fragment!r}"

    def test_the_message_cannot_even_be_passed(self):
        """Structural, not behavioural: `build_payload` takes an id, a type and
        a route. There is no argument a message could arrive through, which is
        what makes "be careful at the call site" unnecessary rather than
        merely advised."""
        parameters = set(inspect.signature(build_payload).parameters)

        assert parameters == {"notification_id", "type_", "url"}

    def test_a_payload_carries_exactly_the_declared_keys(self):
        """An added field is a failing build rather than a quiet new channel
        for whatever somebody put in it."""
        assert set(build_payload(notification_id="N1", type_="clinical_alert")) == set(PAYLOAD_KEYS)

    def test_the_id_is_opaque(self):
        """It identifies a row, not a person, and is useless without an
        authenticated session."""
        payload = build_payload(
            notification_id="8f14e45f-ea1a-4b3c-9d2e-000000000001", type_="clinical_alert"
        )

        assert payload["notification_id"] == "8f14e45f-ea1a-4b3c-9d2e-000000000001"


class TestTheCopyItself:
    @pytest.mark.parametrize("type_", sorted(SAFE_COPY))
    def test_every_entry_is_written(self, type_):
        title, body, url = SAFE_COPY[type_]

        assert title.strip() and body.strip()
        assert url.startswith("/"), "a route, not an absolute URL"

    @pytest.mark.parametrize("type_", sorted(SAFE_COPY))
    def test_no_entry_carries_a_placeholder(self, type_):
        """A `{patient}` in a template is one interpolation away from being the
        thing this module exists to prevent."""
        title, body, _url = SAFE_COPY[type_]

        assert "{" not in title and "{" not in body

    def test_an_unknown_type_degrades_toward_less_information(self):
        """Never toward the message. A missing entry must not be a silent route
        back to patient content."""
        title, body, url = safe_copy_for("something_nobody_wrote_copy_for")

        assert title == "SEPHIROTH"
        assert url == "/work"
        for fragment in LEAKS:
            assert fragment.lower() not in f"{title} {body}".lower()

    def test_a_type_a_user_can_choose_has_copy(self):
        """`notify_types` is validated against this table, so a choosable type
        with no copy would push the generic fallback -- not wrong, but not what
        the person choosing it meant."""
        assert "alert_escalated" in SAFE_COPY
        assert "appointment_reminder" in SAFE_COPY


class TestRouting:
    def test_the_type_supplies_a_default_destination(self):
        assert build_payload(notification_id="N1", type_="alert_escalated")["url"].startswith("/tasks")

    def test_a_caller_may_override_it(self):
        """Where to land is a route, not patient content, and the destination
        page enforces its own auth."""
        payload = build_payload(notification_id="N1", type_="alert_escalated", url="/tasks/T7")

        assert payload["url"] == "/tasks/T7"

    def test_the_tag_is_the_type_not_the_subject(self):
        """Grouping on a patient id would put an identifier in the payload --
        and because a matching tag *replaces* a notification, it would also
        mean a second critical alert silently replacing the first."""
        payload = build_payload(notification_id="N1", type_="clinical_alert")

        assert payload["tag"] == "clinical_alert"
