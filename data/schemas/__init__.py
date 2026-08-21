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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    conditions: Mapped[List[str]] = mapped_column(JSON, default=list)
    medications: Mapped[List[str]] = mapped_column(JSON, default=list)
    allergies: Mapped[List[str]] = mapped_column(JSON, default=list)
    lab_results: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
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
    content: Mapped[str] = mapped_column(Text)
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
    type: Mapped[str] = mapped_column(String(30))  # appointment_booked|result_shared|waitlist_match
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
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Phase 9 (SPEC-011) additions — additive, no data migration needed.
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
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
    assigned_to_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


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
]
