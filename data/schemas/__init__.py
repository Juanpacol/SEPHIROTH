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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    patient: Mapped["Patient"] = relationship()


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
    """One file attached to a `ResultShare`. Bytes live in Postgres
    (`LargeBinary`, `deferred=True` so a list query never drags them into
    memory) rather than the filesystem (Render's free tier has no
    persistent disk — a redeploy would destroy uploaded files) or S3 (no
    new infra for an MVP shipping zero files today). Capped at 10MB/file,
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
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
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
    "ResultShare",
    "ResultAttachment",
    "Consultation",
    "GuidelineDocument",
]
