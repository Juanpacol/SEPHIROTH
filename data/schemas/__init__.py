"""
Database models (SQLAlchemy 2.0 typed style).

JSON columns are used for list-shaped clinical attributes (conditions,
medications, ...) so API response shapes stay identical to the original
demo store; relational tables are used where querying matters
(timeline events, notes, consultations).
"""

from __future__ import annotations

from datetime import date, datetime
from datetime import time as time_
from typing import Any, Dict, List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.crypto import EncryptedJSON, EncryptedText


class Base(DeclarativeBase):
    type_annotation_map = {Dict[str, Any]: JSON, List[str]: JSON}


class User(Base):
    """A clinician or patient-portal account.

    `role` distinguishes the two ("clinician" | "patient"); `patient_id`
    binds a patient login to exactly one `Patient` record. Both are
    additive since Phase B of the patient-portal plan — every pre-existing
    row backfills to `role="clinician"` via `server_default` (see the
    migration), so no data migration step is needed. Role is re-read from
    the DB on every request (`auth.deps`), never carried in the JWT, so a
    role change takes effect immediately.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role != 'patient' OR patient_id IS NOT NULL",
            name="ck_users_patient_has_record",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(20), default="clinician", server_default="clinician", index=True)
    patient_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("patients.id"), nullable=True, unique=True, index=True
    )
    # Checked in `get_current_user` on every request — a deactivated account
    # is rejected immediately regardless of an already-issued JWT's `exp`
    # (there is no token revocation list; this is the only kill switch).
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Login brute-force lockout (`auth.router::login`): a wrong password
    # increments this and, on crossing the threshold, sets `locked_until`;
    # a correct login resets both. Checked alongside `is_active` so a
    # locked-but-active account still can't log in until the window lapses.
    failed_login_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    consultations: Mapped[List["Consultation"]] = relationship(back_populates="user")
    patient: Mapped[Optional["Patient"]] = relationship()


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int]
    sex: Mapped[str] = mapped_column(String(1))
    medical_record_number: Mapped[str] = mapped_column(String(20), unique=True)
    # PHI at rest, encrypted transparently (core/crypto.py) — the DB column
    # is TEXT ciphertext, not JSON; every ORM read/write still sees a plain
    # list/dict, and nothing in this codebase filters on these by value in
    # SQL (confirmed before encrypting them — see ADR-014), so there is no
    # query-layer fallout from ciphertext being opaque.
    conditions: Mapped[List[str]] = mapped_column(EncryptedJSON, default=list)
    medications: Mapped[List[str]] = mapped_column(EncryptedJSON, default=list)
    allergies: Mapped[List[str]] = mapped_column(EncryptedJSON, default=list)
    lab_results: Mapped[Dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    timeline: Mapped[List["TimelineEvent"]] = relationship(
        back_populates="patient", order_by="TimelineEvent.date"
    )


class PatientInvite(Base):
    """A one-time, clinician-issued claim code letting a known `Patient`
    create a portal login. There is deliberately no patient
    self-registration path — identity proofing (confirming the person
    claiming a chart is actually that patient) is a human, in-clinic step,
    not something this system can verify from form fields alone. The
    bearer secret is hashed (bcrypt, via `auth.security`) since it is a
    credential to a full medical record; redemption looks it up by `id`
    (indexed PK) and verifies only the secret half, so lookup never scans.
    """

    __tablename__ = "patient_invites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    issued_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    redeemed_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PasswordResetToken(Base):
    """A one-time, expiring token letting a user set a new password without
    knowing the old one — same shape as `PatientInvite` (hashed bearer
    secret, expiry, one-time redemption). TTL is 1 hour, much shorter than
    `PatientInvite`'s 72 hours: this token grants takeover of an already-live
    account, not just onboarding. No email-sending capability exists in this
    codebase (see `PatientInvite`'s precedent), so the raw token is returned
    directly in the request response rather than mailed."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MfaRecoveryCode(Base):
    """A single-use backup code issued (10 at a time) when a user completes
    TOTP enrollment, for the case their authenticator device is lost.
    Hashed at rest like every other bearer secret in this codebase."""

    __tablename__ = "mfa_recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PhiAccessLog(Base):
    """Append-only record of who read which patient's data, when, and via
    which route. No update/delete route is ever exposed for this table —
    an audit trail that could be edited by the audited party is not a
    trail. Written at each existing PHI-read call site (patients.py,
    portal.py, results.py) rather than derived from generic request
    logging, since only the handler knows which `patient_id` was touched."""

    __tablename__ = "phi_access_log"
    __table_args__ = (Index("ix_phi_access_log_patient_created", "patient_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    route: Mapped[str] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class TimelineEvent(Base):
    """One event on a patient's Intelligent Timeline."""

    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(20))  # diagnosis|medication|lab|imaging|event
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    ai_generated: Mapped[bool] = mapped_column(default=False)

    patient: Mapped["Patient"] = relationship(back_populates="timeline")


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    note_type: Mapped[str] = mapped_column(String(40), default="progress_note")
    content: Mapped[str] = mapped_column(EncryptedText)  # PHI at rest, see Patient's columns above
    extracted_entities: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AvailabilityRule(Base):
    """A clinician's recurring weekly working-hours window.

    Stored in **wall-clock time + IANA timezone**, not UTC — "Tuesdays
    09:00-17:00" must stay 09:00 local across a DST transition; storing
    the rule pre-converted to UTC would silently shift it by an hour
    twice a year. `platform/api/scheduling.py::expand_slots` is the one
    place this gets localized and converted to UTC instants.
    """

    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("start_time < end_time", name="ck_availability_rule_time_order"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_rule_weekday"),
        UniqueConstraint(
            "clinician_id", "weekday", "start_time", "end_time", name="uq_availability_rule_window"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Mon .. 6=Sun (date.weekday())
    start_time: Mapped[time_] = mapped_column(Time)
    end_time: Mapped[time_] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    slot_minutes: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AvailabilityException(Base):
    """A one-off block (time off) or extra opening for a clinician, as an
    absolute UTC instant — unlike `AvailabilityRule`, this describes a
    specific day, not a recurring pattern, so UTC is the right storage
    shape here."""

    __tablename__ = "availability_exceptions"
    __table_args__ = (CheckConstraint("start_at < end_at", name="ck_availability_exception_time_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[str] = mapped_column(String(10))  # "block" | "open"
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Appointment(Base):
    """A booked slot between a clinician and a patient.

    No DB-level exclusion constraint against double-booking — Postgres's
    `EXCLUDE USING gist` has no SQLite equivalent and would break
    `Base.metadata.create_all` in the test fixture. Overlap is enforced in
    a single transaction in `platform/api/routers/scheduling.py` instead
    (documented residual: a genuinely simultaneous race is possible at
    demo scale). Cancellation is a status change, never a row delete, so
    history and a later rebook both work.
    """

    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="ck_appointment_time_order"),
        Index("ix_appointments_clinician_start", "clinician_id", "start_at"),
        Index("ix_appointments_patient_start", "patient_id", "start_at"),
        # The no-show sweep (SPEC-020) selects on `status` first, and neither
        # index above leads with it.
        Index("ix_appointments_status_end", "status", "end_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(
        String(12), default="booked", server_default="booked", index=True
    )  # booked|completed|cancelled|no_show
    mode: Mapped[str] = mapped_column(String(12), default="in_person", server_default="in_person")
    reason: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")  # clinician-only, never returned to a patient
    created_by_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancellation_reason: Mapped[str] = mapped_column(String(200), default="")
    # Phase 10 (SPEC-012). Deliberately NOT a new `status` value -- `status`
    # has no CheckConstraint, `status == "booked"` is hardcoded at several
    # sites in this router, and the Postgres double-booking exclusion index
    # is partial (`WHERE status = 'booked'`, see the booking_exclusion
    # migration). A `confirmed` status would silently fall out of all of
    # that. These two columns are orthogonal to `status` on purpose.
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_by_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Set only for an occurrence created by POST /scheduling/series, which
    # expands every occurrence eagerly at creation time (no background job
    # exists to expand a series lazily — see AppointmentSeries).
    series_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("appointment_series.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    patient: Mapped["Patient"] = relationship()


class AppointmentSeries(Base):
    """A recurring booking pattern (e.g. "every Tuesday for 8 weeks").
    Deliberately not full RFC 5545 — just frequency/interval/count — and
    deliberately expanded **eagerly**, all `count` `Appointment` rows
    created up front in one transaction, rather than lazily by a
    scheduler: no background-job infrastructure exists anywhere in this
    deployment (single API container, no Celery/RQ/APScheduler), so a
    lazy-expansion design would need one. `count` is capped at
    `MAX_SERIES_COUNT` (see the router) to bound that eager insert."""

    __tablename__ = "appointment_series"
    __table_args__ = (CheckConstraint("occurrence_count > 0", name="ck_appointment_series_count_positive"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    frequency: Mapped[str] = mapped_column(String(10))  # "weekly" | "biweekly" | "monthly"
    occurrence_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(10), default="active", server_default="active"
    )  # active|cancelled
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    occurrences: Mapped[List["Appointment"]] = relationship(order_by="Appointment.start_at")


class AppointmentWaitlist(Base):
    """A patient's request to be notified if a slot opens in a clinician's
    fully-booked window. No auto-booking on a match: `cancel_appointment`
    (see `platform/api/routers/scheduling.py`) synchronously checks for
    the earliest waiting match and sends an in-app `Notification` — the
    patient still has to book the freed slot themselves, which sidesteps
    a silent double-commit race between "notify" and "book"."""

    __tablename__ = "appointment_waitlist"
    __table_args__ = (CheckConstraint("window_start < window_end", name="ck_waitlist_window_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Notification(Base):
    """An in-app notification — no email/SMS/push channel exists in this
    codebase (no SMTP/Twilio dependency, no worker process to send from),
    so this is the whole delivery mechanism for now. Created at three
    hook points: a successful booking, a result share, and a waitlist
    match. Read via `GET /api/notifications`, which wires the previously
    dead bell icon in `components/topbar.tsx`."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(
        String(30)
    )  # appointment_booked|result_shared|waitlist_match|followup_message
    message: Mapped[str] = mapped_column(String(300))
    related_appointment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("appointments.id"), nullable=True
    )
    # NULL for every pre-existing/non-workflow row (Postgres and SQLite both
    # allow unlimited NULLs in a unique index, so this is additive, no
    # backfill). Set by workflow steps to f"step:{step_id}:{user_id}" so a
    # re-run of the same step can never double-notify the same recipient --
    # see platform/api/workflows/channels.py::InAppChannel.
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, unique=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class ResultShare(Base):
    """A clinician sharing one `TimelineEvent` (a lab or imaging result)
    with the patient it belongs to. Deliberately references the existing
    timeline rather than inventing a third "lab result" concept —
    `Patient.lab_results` is a denormalized current-values panel with no
    row identity to reference, `TimelineEvent` already has identity, a
    date, and a narrative. Sharing is restricted at the API layer to
    `type in ("lab", "imaging")` events belonging to the same patient."""

    __tablename__ = "result_shares"
    __table_args__ = (UniqueConstraint("timeline_event_id", "patient_id", name="uq_result_share_event"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    timeline_event_id: Mapped[int] = mapped_column(ForeignKey("timeline_events.id"), index=True)
    shared_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), default="sent", server_default="sent")  # sent|revoked
    shared_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    #: Which result this share communicated, when it came from one (SPEC-024).
    #: Nullable and additive: shares made before this existed point at a
    #: timeline event and keep doing so, because rewriting them to point
    #: somewhere else would rewrite what was actually shared.
    result_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    result_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    event: Mapped["TimelineEvent"] = relationship()
    attachments: Mapped[List["ResultAttachment"]] = relationship(
        back_populates="share", cascade="all, delete-orphan", lazy="selectin"
    )


class ResultAttachment(Base):
    """One file attached to a `ResultShare`. Bytes live behind
    `platform/core/storage.py::BlobStore` — Postgres `LargeBinary` by
    default (`deferred=True` so a list query never drags them into
    memory), or S3 when `settings.storage_backend == "s3"`. `content` is
    nullable because the S3 backend never populates it — the bytes live
    in the bucket, keyed by this row's `id`, and `content` staying NULL
    for those rows is the signal of where to look. Capped at 10MB/file,
    3 files/share, enforced at the API layer."""

    __tablename__ = "result_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result_share_id: Mapped[str] = mapped_column(
        ForeignKey("result_shares.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[Optional[bytes]] = mapped_column(LargeBinary, deferred=True, nullable=True)
    uploaded_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    share: Mapped["ResultShare"] = relationship(back_populates="attachments")


class Consultation(Base):
    """One multi-agent consultation, owned by the requesting clinician."""

    __tablename__ = "consultations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    patient_id: Mapped[Optional[str]] = mapped_column(ForeignKey("patients.id"), nullable=True)
    query: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    agents: Mapped[List[str]] = mapped_column(JSON, default=list)
    tool_calls: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    citation_report: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    verification_report: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    abstention: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    # SPEC-006 (ADR-009): the replayable ExecutionTrace, plus the 4 indexed
    # scalars ADR-009 names — nullable so pre-Phase-5 rows (and any future
    # run with tracing disabled) don't need a backfill.
    trace: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=None)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    risk_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    abstained: Mapped[Optional[bool]] = mapped_column(nullable=True, index=True)
    supported_claim_ratio: Mapped[Optional[float]] = mapped_column(nullable=True, index=True)
    # Outcome tracking: did the clinician act on this recommendation, and did
    # the patient improve? Same nullable-scalar-no-backfill pattern as the
    # trace columns above — `acted_on is None` means "never touched" (distinct
    # from `False`, an explicit "no"), and `outcome` is only ever set once
    # `acted_on` is true, recorded at a separate, later time.
    acted_on: Mapped[Optional[bool]] = mapped_column(nullable=True, index=True)
    acted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True
    )  # improved|not_improved|unclear
    outcome_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="consultations")


class GuidelineDocument(Base):
    """Schema for a future clinical guideline ingestion endpoint — no route
    reads or writes this table today (`DEBT-003`, resolved by documenting
    this as intentional cold storage, not by building the endpoint).
    Retrieval scoring always runs against the in-memory vector store
    (`data.vectors.InMemoryVectorStore`, seeded at startup), not a query
    against this table — see `data/rag/__init__.py`.

    `embedding` uses `JSON` on SQLite (the in-memory test DB — pgvector has
    no SQLite equivalent) and `pgvector`'s native type on Postgres, so
    `Base.metadata.create_all` keeps working in both, ready for whichever
    dialect a real ingestion endpoint eventually targets.

    No HNSW/IVFFlat index — intentionally deferred until a real ingestion
    endpoint exists and rows actually land here; indexing an empty table
    has no use case to validate against.
    """

    __tablename__ = "guideline_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(255))
    doc_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        Vector(768).with_variant(JSON, "sqlite"), nullable=True
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Alert(Base):
    """A clinical alert surfaced on the dashboard — the persisted analogue
    of the transient risk flags `sephiroth.safety.risk` computes at
    read-time (decision #10): those flags have no identity to review or
    resolve, so anything the dashboard needs to track lifecycle for
    (reviewed by whom, resolved when) needs a real row. Never auto-deleted;
    lifecycle is a status change, same convention as `Appointment`."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "category IN ('medication','lab','imaging','ai','clinical')", name="ck_alert_category"
        ),
        CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_alert_severity"),
        CheckConstraint("status IN ('active','reviewed','resolved')", name="ck_alert_status"),
        CheckConstraint("kind IN ('clinical','administrative')", name="ck_alert_kind"),
        # One open alert per rule per patient. A partial index would be the
        # precise expression of that, but SQLite (the test database) does not
        # support the `WHERE status <> 'resolved'` clause portably, so the
        # invariant is enforced in `generate_alerts_for_patient` and this
        # index exists to make that check cheap.
        Index("ix_alerts_patient_rule", "patient_id", "rule_key", "status"),
        Index("ix_alerts_status_severity", "status", "severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    category: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active", index=True)
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(60))  # which engine/rule raised it
    #: Stable identity of the *rule*, independent of what it is called on
    #: screen (SPEC-021). Deduplication keys on this rather than on `title`,
    #: which is display copy -- rewording a label would otherwise duplicate
    #: every open alert. Nullable because alerts predating this column have
    #: none, and backfilling display strings into a machine key would invent
    #: identities that were never real.
    rule_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    #: `clinical` (a finding about the patient) or `administrative` (a finding
    #: about the process -- an unconfirmed appointment, a failed automation).
    #: They deserve different urgency and different filters: treating "critical
    #: potassium" and "nobody confirmed a booking" as one queue is how the
    #: second teaches people to skim past the first.
    kind: Mapped[str] = mapped_column(String(20), default="clinical", server_default="clinical", index=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Phase 9 (SPEC-011) additions — additive, no data migration needed.
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    patient: Mapped["Patient"] = relationship()


class LabResult(Base):
    """One discrete lab measurement with real row identity and a
    timestamp, unlike `Patient.lab_results` (a denormalized
    current-values JSON snapshot with no history). Powers trend/
    deterioration queries the JSON blob structurally cannot answer.
    Newly captured results only — the existing JSON snapshot is not
    backfilled retroactively."""

    __tablename__ = "lab_results"
    __table_args__ = (Index("ix_lab_results_patient_test_taken", "patient_id", "test_name", "taken_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    test_name: Mapped[str] = mapped_column(String(60))
    value: Mapped[float]
    unit: Mapped[str] = mapped_column(String(20), default="")
    reference_low: Mapped[Optional[float]] = mapped_column(nullable=True)
    reference_high: Mapped[Optional[float]] = mapped_column(nullable=True)
    is_abnormal: Mapped[bool] = mapped_column(default=False, server_default="false")
    is_critical: Mapped[bool] = mapped_column(default=False, server_default="false")
    taken_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    patient: Mapped["Patient"] = relationship()


class MedicationOrder(Base):
    """A structured medication order, gradually replacing
    `Patient.medications` (a flat name-only list) as the source for the
    drug-interaction/dosage-anomaly checks in `sephiroth.safety.risk`.
    That module keeps reading the JSON list when a patient has no
    `MedicationOrder` rows, so existing patients don't need a backfill."""

    __tablename__ = "medication_orders"
    __table_args__ = (
        CheckConstraint("status IN ('active','discontinued')", name="ck_medication_order_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    dose: Mapped[str] = mapped_column(String(60), default="")
    route: Mapped[str] = mapped_column(String(30), default="")
    frequency: Mapped[str] = mapped_column(String(60), default="")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_high_risk: Mapped[bool] = mapped_column(default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(15), default="active", server_default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    patient: Mapped["Patient"] = relationship()


class ImagingStudy(Base):
    """A tracked imaging study and its AI-assisted read — `TimelineEvent`
    (`type="imaging"`) still carries the narrative entry shown on a
    patient's timeline; this table adds the structured fields (severity,
    review flag, new-vs-prior comparison) the dashboard's Imaging section
    needs that a free-text timeline entry can't answer."""

    __tablename__ = "imaging_studies"
    __table_args__ = (
        CheckConstraint("status IN ('pending','analyzed')", name="ck_imaging_study_status"),
        CheckConstraint("severity IN ('critical','review','none')", name="ck_imaging_study_severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    modality: Mapped[str] = mapped_column(String(20))
    body_part: Mapped[str] = mapped_column(String(60))
    study_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending", index=True)
    finding_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="none", server_default="none")
    is_new_finding: Mapped[bool] = mapped_column(default=False, server_default="false")
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    patient: Mapped["Patient"] = relationship()


class AIEvaluation(Base):
    """One AI assessment tracked for the dashboard's Inteligencia Artificial
    section — complements, not replaces, `Consultation`'s own
    `risk_level`/`abstained`/`supported_claim_ratio`/`acted_on` columns:
    those describe one consultation's outcome, this tracks review/override
    state across any AI evaluation (not only full multi-agent
    consultations)."""

    __tablename__ = "ai_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[Optional[str]] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    consultation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("consultations.id"), nullable=True, index=True
    )
    eval_type: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(default=0.0)
    requires_human_review: Mapped[bool] = mapped_column(default=False, server_default="false")
    reviewed_by_clinician: Mapped[bool] = mapped_column(default=False, server_default="false")
    clinician_modified: Mapped[Optional[bool]] = mapped_column(nullable=True)
    clinician_rejected: Mapped[Optional[bool]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class FollowupPlan(Base):
    """A clinician-approved post-consultation follow-up schedule
    (SPEC-014). Creating one IS the clinician's approval of the
    schedule itself (day 3/7/30) -- the human-in-the-loop gate
    (`PendingAction`) governs each check's *drafted patient message*,
    not whether the follow-up happens at all."""

    __tablename__ = "followup_plans"
    __table_args__ = (
        CheckConstraint("status IN ('active','completed','cancelled')", name="ck_followup_plan_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    consultation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("consultations.id"), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(12), default="active", server_default="active", index=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Workflow(Base):
    """One running instance of a workflow definition (defined as Python
    literals in `platform/api/workflows/registry.py`, never a DB row).
    Anchored to at most one of an appointment/consultation/alert/followup
    plan -- the thing whose lifecycle drove this workflow into existence.
    `version` snapshots the definition version at instantiation time so
    editing a definition later never retroactively alters a live instance."""

    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint("status IN ('active','completed','cancelled','failed')", name="ck_workflow_status"),
        CheckConstraint(
            "(CASE WHEN appointment_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN consultation_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN alert_id IS NULL THEN 0 ELSE 1 END"
            " + CASE WHEN followup_plan_id IS NULL THEN 0 ELSE 1 END) <= 1",
            name="ck_workflow_single_anchor",
        ),
        Index("ix_workflows_patient_definition_status", "patient_id", "definition_key", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    definition_key: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    appointment_id: Mapped[Optional[str]] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    consultation_id: Mapped[Optional[str]] = mapped_column(ForeignKey("consultations.id"), nullable=True)
    alert_id: Mapped[Optional[str]] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    followup_plan_id: Mapped[Optional[str]] = mapped_column(ForeignKey("followup_plans.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active", server_default="active", index=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    steps: Mapped[List["WorkflowStep"]] = relationship(back_populates="workflow")


class WorkflowStep(Base):
    """One due-dated unit of work inside a `Workflow`, claimed and
    executed by the tick (`POST /internal/tick` -> `platform/api/workflows/engine.py`).
    `due_at` is the immutable anchor used for staleness math;
    `run_after` is the mutable column the tick actually selects on
    (starts equal to `due_at`, bumped by backoff on retry) -- kept
    separate so `is_stale()` never has to reverse-engineer a step's
    original due time from a value retries have since moved."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_id", "step_key", name="uq_workflow_step_key"),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','skipped','superseded','cancelled')",
            name="ck_workflow_step_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_workflow_step_attempts_nonneg"),
        CheckConstraint("max_attempts > 0", name="ck_workflow_step_max_attempts_positive"),
        Index("ix_workflow_steps_status_run_after", "status", "run_after"),
        Index("ix_workflow_steps_workflow_status", "workflow_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    step_key: Mapped[str] = mapped_column(String(60))
    step_type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending", index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    run_after: Mapped[datetime] = mapped_column(DateTime, index=True)
    max_lateness_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    #: Times this step said "not now" (SPEC-020). Counted separately from
    #: `attempts` because a deferral is a decision, not a failure -- charging it
    #: a retry would mean three quiet nights in a row permanently kill a
    #: reminder. It still needs a ceiling: a quiet-hours window misconfigured to
    #: cover the whole day would otherwise defer forever, and a notification
    #: that never sends and never errors is the worst of both.
    deferred_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    claimed_by: Mapped[str] = mapped_column(String(40), default="", server_default="")
    last_error: Mapped[str] = mapped_column(String(300), default="", server_default="")
    failure_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    workflow: Mapped["Workflow"] = relationship(back_populates="steps")


class PendingAction(Base):
    """A proposed patient-facing action awaiting a clinician's
    approve/reject click (SPEC-013) -- the human-in-the-loop gate. Anything
    the *patient* will see must have a row here that reaches `approved`
    before it can be sent; internal/fixed-template automation (Phase 9's
    escalation, Phase 10's T-24h reminder) never creates one.

    `ck_pending_action_requires_reviewer` makes the gate auditable as a
    query, not just a code path: `SELECT * FROM pending_actions WHERE
    status IN ('approved','rejected') AND reviewed_by IS NULL` must always
    return zero rows, enforced at the DB level, not only by the router.
    """

    __tablename__ = "pending_actions"
    __table_args__ = (
        UniqueConstraint("workflow_step_id", name="uq_pending_action_workflow_step"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired')", name="ck_pending_action_status"
        ),
        CheckConstraint("draft_source IN ('template','llm')", name="ck_pending_action_draft_source"),
        CheckConstraint(
            "status NOT IN ('approved','rejected') OR reviewed_by IS NOT NULL",
            name="ck_pending_action_requires_reviewer",
        ),
        # Same reasoning as the constraint above, applied to the draft itself
        # (SPEC-020): a rule that lives only in a router is a comment. An empty
        # draft in the approvals inbox is a row that asks the clinician to
        # babysit the automation before they can review its output.
        CheckConstraint("draft_text <> ''", name="ck_pending_action_draft_nonempty"),
        Index("ix_pending_actions_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_step_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("workflow_steps.id"), nullable=True, index=True
    )
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending", index=True)
    draft_text: Mapped[str] = mapped_column(Text, default="")
    draft_source: Mapped[str] = mapped_column(String(10), default="template", server_default="template")
    draft_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    final_text: Mapped[str] = mapped_column(Text, default="")
    proposed_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class AutomationMemory(Base):
    """Namespaced operational preferences (SPEC-015) -- quiet hours,
    reminder lead time, contact preference. Explicitly NOT a place for
    clinical facts: `platform/api/workflows/memory.py::ALLOWED_KEYS` is
    an allow-listed key set (same discipline as `ALLOWED_SPAN_ATTRIBUTES`,
    `src/sephiroth/contracts/trace.py`), enforced in code, not here --
    a CheckConstraint can't express "key is one of a Python-side set"
    portably, so the allow-list lives at the one write path
    (`set_memory`) instead. Authoritative clinical memory stays in
    `Patient`/`Consultation`/etc, never here (decision: CLAUDE.md #16)."""

    __tablename__ = "automation_memory"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "key", name="uq_automation_memory_scope_key"),
        CheckConstraint("scope IN ('clinic','user','patient')", name="ck_automation_memory_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(10), index=True)
    scope_id: Mapped[str] = mapped_column(String(36), index=True)
    key: Mapped[str] = mapped_column(String(60))
    value: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class WorkflowEvent(Base):
    """A durable record of something that happened, written inside the
    same transaction as the domain change that caused it -- an outbox,
    not a broker (SPEC-010). A rolled-back booking can never leave a
    phantom event; that atomicity is the actual property a message
    broker cannot give for free. `dispatch_pending()`
    (`platform/api/workflows/events.py`) runs from the tick and marks
    each row `dispatched` (a registered handler ran) or `no_subscriber`
    (recorded, nothing wired to it yet) -- never left `pending` forever."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','dispatched','no_subscriber')", name="ck_workflow_event_status"
        ),
        Index("ix_workflow_events_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36))
    patient_id: Mapped[Optional[str]] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(14), default="pending", server_default="pending", index=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Task(Base):
    """One piece of clinical work somebody has to do (SPEC-018).

    Alerts, approvals, follow-ups, results to review and appointment chores
    were five separate inboxes, and `GET /api/dashboard/action-items` derived
    a sixth, read-only view over them with no row identity -- so nothing on
    it could be claimed, snoozed, commented on, or tracked to closure. This
    table is the one place that work lives.

    **It does not replace those entities.** Each keeps its own domain state;
    a task owns the *workflow* state around it (who has it, when it is due,
    what has happened to it) and is kept in step with its source by
    `platform/api/services/task_service.py`, which both sides call.

    The link to the source is `source_type` + `source_id` rather than a
    nullable FK per source. Two reasons, and the second is the load-bearing
    one: the sources have incompatible primary-key types (`LabResult.id` and
    `TimelineEvent.id` are integers, the rest are String(36)), and two
    categories -- a deteriorating trend, a drug interaction -- have no source
    row at all, so there is nothing for a foreign key to point at. The cost
    is no referential integrity to the source; `ck_task_source_type` bounds
    the values and `task_service.reconcile_tasks` sweeps for orphans.

    `escalated_at`/`escalation_level` are a timestamp and a counter, not a
    status, for the same reason `Appointment.confirmed_at` is orthogonal to
    `Appointment.status`: an escalated task is still open work, and folding
    it into the status would make "show me everything open" wrong.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_task_dedupe_key"),
        CheckConstraint(
            "source_type IN ('alert','approval','followup','result','appointment',"
            "'automation','consultation','deteriorating','interaction','encounter',"
            "'result_review')",
            name="ck_task_source_type",
        ),
        CheckConstraint("severity IN ('critical','high','medium','low')", name="ck_task_severity"),
        CheckConstraint(
            "status IN ('open','in_progress','snoozed','done','dismissed','superseded')",
            name="ck_task_status",
        ),
        # Same trick as `ck_pending_action_requires_reviewer`: a closed task
        # with nobody recorded against it makes the audit query lie, so the
        # database refuses it rather than trusting every write path.
        CheckConstraint(
            "status NOT IN ('done','dismissed') OR closed_by IS NOT NULL",
            name="ck_task_closed_requires_actor",
        ),
        Index("ix_tasks_status_due", "status", "due_at"),
        Index("ix_tasks_assigned_status", "assigned_to_user_id", "status"),
        Index("ix_tasks_source", "source_type", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    #: Stable identity of the work, not of the row. Re-deriving the same task
    #: on every 5-minute tick must not create a second one, which is what the
    #: unique constraint above enforces -- for a derived task this is a
    #: content key, since there is no source row to key on.
    dedupe_key: Mapped[str] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    patient_id: Mapped[Optional[str]] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    #: Free clinical text, so it goes through the PHI column types (ADR-014)
    #: exactly like `ClinicalNote.content`.
    detail: Mapped[str] = mapped_column(EncryptedText, default="")
    context: Mapped[Dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)
    severity: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(12), default="open", server_default="open", index=True)
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    snoozed_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    dismiss_reason: Mapped[str] = mapped_column(String(300), default="")
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    patient: Mapped[Optional["Patient"]] = relationship()


class TaskEvent(Base):
    """What happened to a task, and who did it.

    A child table rather than a JSON column on `Task`, because the questions
    this has to answer are queries -- "what did the team do with overdue
    critical tasks last month", "how long from raised to claimed" -- and a
    JSON array can be neither indexed nor joined.

    It does not replace `PhiAccessLog` and is not a substitute for it: this
    records *work provenance*, that records *PHI reads*. A task read that
    touches a patient still writes a `PhiAccessLog` row.

    Append-only by convention, like `PhiAccessLog` -- no route updates or
    deletes a row here.
    """

    __tablename__ = "task_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created','claimed','assigned','snoozed','resumed','escalated',"
            "'completed','dismissed','superseded','reopened','commented')",
            name="ck_task_event_type",
        ),
        Index("ix_task_events_task_created", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20))
    #: NULL means the system did it (the tick, a source adapter) -- the same
    #: convention `PhiAccessLog` uses for `SYSTEM_WORKFLOW_USER_ID` work.
    actor_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    note: Mapped[str] = mapped_column(EncryptedText, default="")
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Encounter(Base):
    """One clinical visit: what was measured, what was said, what was decided.

    `Appointment` said a visit was booked and `ClinicalNote` said something was
    written afterwards; nothing joined them, so the work of a consultation
    landed as a wall of free text or not at all (SPEC-023 §2).

    Four narrative columns rather than one blob, because SOAP is what a
    clinician already thinks in and what every template renders into -- and
    because a single `note` field would make a model's draft and the
    clinician's edit fight over the same column.

    `draft` -> `signed` is the review gate for AI-drafted content (ADR-016):
    an unsigned encounter has no `ClinicalNote`, contributes nothing to the
    timeline, files no tasks and is invisible to the patient, so there is no
    path by which unreviewed text reaches the chart.
    """

    __tablename__ = "encounters"
    __table_args__ = (
        CheckConstraint("status IN ('draft','signed','amended')", name="ck_encounter_status"),
        CheckConstraint("note_source IN ('clinician','llm','template')", name="ck_encounter_note_source"),
        # A signed record without a signer is a clinical record nobody stands
        # behind. Same posture as `ck_pending_action_requires_reviewer` and
        # `ck_task_closed_requires_actor`.
        CheckConstraint(
            "status = 'draft' OR (signed_at IS NOT NULL AND signed_by IS NOT NULL)",
            name="ck_encounter_signed_requires_signer",
        ),
        CheckConstraint("amended_at IS NULL OR amendment_reason <> ''", name="ck_encounter_amendment_reason"),
        # One encounter per booking. Nullable elsewhere, so a walk-in and a
        # second unlinked encounter on the same day both stay possible.
        Index(
            "uq_encounter_appointment",
            "appointment_id",
            unique=True,
            sqlite_where=text("appointment_id IS NOT NULL"),
            postgresql_where=text("appointment_id IS NOT NULL"),
        ),
        Index("ix_encounters_patient_started", "patient_id", "started_at"),
        Index("ix_encounters_clinician_status", "clinician_id", "status"),
        Index("ix_encounters_status_started", "status", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    clinician_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    appointment_id: Mapped[Optional[str]] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    #: Chooses a note template and nothing else -- no taxonomy, no routing.
    specialty: Mapped[str] = mapped_column(String(40), default="general", server_default="general")
    status: Mapped[str] = mapped_column(String(12), default="draft", server_default="draft", index=True)

    chief_complaint: Mapped[str] = mapped_column(EncryptedText, default="")
    #: Keys bounded by `sephiroth.clinical.vitals.VITAL_SPECS`. JSON rather
    #: than columns for the same reason `Patient.lab_results` is: nothing
    #: filters on a vital in SQL, and a trend view would want a normalised
    #: table rather than nine columns nobody reads (SPEC-023 §11 risk 2).
    vitals: Mapped[Dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)

    subjective: Mapped[str] = mapped_column(EncryptedText, default="")
    objective: Mapped[str] = mapped_column(EncryptedText, default="")
    assessment: Mapped[str] = mapped_column(EncryptedText, default="")
    plan: Mapped[str] = mapped_column(EncryptedText, default="")
    #: The one output the patient actually leaves with.
    patient_instructions: Mapped[str] = mapped_column(EncryptedText, default="")

    #: Whether the persisted narrative started as a model's draft. Kept on the
    #: content itself so a later reader can see it without a join (ADR-016).
    note_source: Mapped[str] = mapped_column(String(10), default="clinician", server_default="clinician")
    note_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    signed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    amended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    amendment_reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    #: Written on signing. The note carries the narrative as it stood then, so
    #: an amendment cannot erase what was originally committed (SPEC-023 NG-5).
    clinical_note_id: Mapped[Optional[str]] = mapped_column(ForeignKey("clinical_notes.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    #: Declared so the cascade is the database's job rather than the
    #: caller's. Application code reads orders through
    #: `encounter_service.list_orders`, never through this attribute: touching
    #: a lazy collection on a flushed instance issues IO from wherever it is
    #: touched, which under asyncio surfaces as a `MissingGreenlet` far from
    #: the cause.
    orders: Mapped[List["EncounterOrder"]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", lazy="raise"
    )


class EncounterOrder(Base):
    """Something decided in the room that somebody has to do afterwards.

    A child table rather than a JSON list on the encounter, for the same
    reason `task_events` is one: "which orders were never acted on" has to be
    answerable by query, not by loading every encounter and reading a blob.

    It becomes a `Task` on signing, never before -- a task created from an
    unsigned decision is work nobody committed to, and the inbox is only worth
    reading because everything in it is real (SPEC-023 §11 risk 3).
    """

    __tablename__ = "encounter_orders"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('lab','imaging','referral','followup','medication')",
            name="ck_encounter_order_kind",
        ),
        CheckConstraint("due_in_days IS NULL OR due_in_days > 0", name="ck_encounter_order_due"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(EncryptedText)
    due_in_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    #: Set on signing. Its presence is what makes signing idempotent.
    task_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    encounter: Mapped["Encounter"] = relationship(back_populates="orders")


class ResultReview(Base):
    """What a human did about a result.

    A separate row rather than columns on `lab_results` and `imaging_studies`
    (ADR-017): those two have incompatible primary-key types, so the column
    approach is two implementations of one concept from the first day, and
    every "what is unreviewed" query would be written twice and unioned.

    It also keeps the measurement and the judgement apart. A lab value is true
    forever; a review is one clinician's decision on one day, in their own
    words, and `note` carries PHI accordingly.

    The state machine's one load-bearing guard is that a result whose
    disposition was "tell the patient" cannot be closed until they have been
    told. Without it the states are decoration.
    """

    __tablename__ = "result_reviews"
    __table_args__ = (
        UniqueConstraint("result_type", "result_id", name="uq_result_review_result"),
        CheckConstraint("result_type IN ('lab','imaging')", name="ck_result_review_type"),
        CheckConstraint(
            "status IN ('received','reviewed','communicated','closed')",
            name="ck_result_review_status",
        ),
        CheckConstraint(
            "severity IN ('critical','abnormal','normal','unclassified')",
            name="ck_result_review_severity",
        ),
        CheckConstraint(
            "disposition IS NULL OR disposition IN "
            "('normal','abnormal_expected','action_taken','needs_patient_contact')",
            name="ck_result_review_disposition",
        ),
        # A reviewed result with no reviewer is a decision nobody made. Same
        # posture as `ck_encounter_signed_requires_signer`.
        CheckConstraint(
            "status = 'received' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="ck_result_review_reviewed",
        ),
        CheckConstraint(
            "status <> 'closed' OR (closed_at IS NOT NULL AND closed_by IS NOT NULL)",
            name="ck_result_review_closed",
        ),
        Index("ix_result_reviews_status_severity", "status", "severity"),
        Index("ix_result_reviews_patient_created", "patient_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result_type: Mapped[str] = mapped_column(String(10))
    #: String even for a lab, whose own id is an integer -- one column has to
    #: hold both key types, the same compromise `tasks.source_id` makes.
    result_id: Mapped[str] = mapped_column(String(64))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    status: Mapped[str] = mapped_column(String(14), default="received", server_default="received", index=True)
    #: From `sephiroth.clinical.results`, computed once at intake. Stored rather
    #: than derived on read because the reference range that produced it came
    #: with the result and may not be the one in code tomorrow.
    severity: Mapped[str] = mapped_column(String(12))
    #: The one line explaining the severity, so a clinician can check the
    #: judgement instead of trusting it.
    classification_reason: Mapped[str] = mapped_column(String(300), default="", server_default="")

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    disposition: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    #: The clinician's own words. Free clinical text, so it goes through the
    #: PHI column types (ADR-014).
    note: Mapped[str] = mapped_column(EncryptedText, default="")

    share_id: Mapped[Optional[str]] = mapped_column(ForeignKey("result_shares.id"), nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tasks.id"), nullable=True)

    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PushSubscription(Base):
    """One browser on one device, as the push service identifies it.

    `endpoint` is the unique key rather than `(user_id, device)`: the push
    service issues it, the browser can throw it away and get a new one at any
    time, and the same endpoint moving between accounts on a shared machine is
    something that has to be handled rather than refused.

    A gone subscription is disabled, never deleted. `disabled_at` plus
    `failure_count` is what lets a person look at their device list and see
    that the phone they replaced stopped working in March, instead of finding
    a row silently absent.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
        Index("ix_push_subscriptions_user_active", "user_id", "disabled_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(String(500))
    #: The browser's public key and shared secret. Not PHI and not a
    #: credential for this system -- they authorise sending *to* one browser,
    #: and are useless without the VAPID private key.
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    #: So a person can tell their own devices apart in the settings list.
    user_agent: Mapped[str] = mapped_column(String(200), default="", server_default="")
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    disabled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PushDelivery(Base):
    """One attempt to reach one device with one notification.

    A row per device rather than per notification, so a failure is attributable
    to a phone rather than to a person: one dead subscription must not make a
    clinician's other devices look broken.

    Shaped like a workflow step on purpose -- `attempts`, `send_after`,
    `last_error` -- because it is the same problem the engine already solved,
    and a second retry vocabulary would be a second set of bugs.
    """

    __tablename__ = "push_deliveries"
    __table_args__ = (
        # One buzz per device per notification. A retried enqueue is a no-op
        # rather than a phone vibrating twice.
        UniqueConstraint("subscription_id", "notification_id", name="uq_push_delivery"),
        CheckConstraint("status IN ('pending','sent','failed','dropped')", name="ck_push_delivery_status"),
        Index("ix_push_deliveries_due", "status", "send_after"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("push_subscriptions.id", ondelete="CASCADE"), index=True
    )
    notification_id: Mapped[str] = mapped_column(ForeignKey("notifications.id"), index=True)
    #: Where a tap should land. A route, never patient content -- and stored on
    #: the row rather than held in a process dictionary, which would grow
    #: without bound and lose every pending destination on restart.
    url: Mapped[str] = mapped_column(String(200), default="", server_default="")
    status: Mapped[str] = mapped_column(String(10), default="pending", server_default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    send_after: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    #: Truncated deliberately: a push service's error body can be long, and
    #: none of it is worth storing beyond the first line.
    last_error: Mapped[str] = mapped_column(String(200), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


__all__ = [
    "Base",
    "User",
    "Patient",
    "PatientInvite",
    "PasswordResetToken",
    "MfaRecoveryCode",
    "PhiAccessLog",
    "TimelineEvent",
    "ClinicalNote",
    "AvailabilityRule",
    "AvailabilityException",
    "Appointment",
    "AppointmentSeries",
    "AppointmentWaitlist",
    "Notification",
    "ResultShare",
    "ResultAttachment",
    "Consultation",
    "GuidelineDocument",
    "Alert",
    "LabResult",
    "MedicationOrder",
    "ImagingStudy",
    "AIEvaluation",
    "Workflow",
    "WorkflowStep",
    "WorkflowEvent",
    "PendingAction",
    "FollowupPlan",
    "AutomationMemory",
    "Task",
    "TaskEvent",
    "Encounter",
    "EncounterOrder",
    "ResultReview",
    "PushSubscription",
    "PushDelivery",
]
