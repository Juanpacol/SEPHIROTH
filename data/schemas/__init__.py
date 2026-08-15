"""
Database models (SQLAlchemy 2.0 typed style).

JSON columns are used for list-shaped clinical attributes (conditions,
medications, ...) so API response shapes stay identical to the original
demo store; relational tables are used where querying matters
(timeline events, notes, consultations).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {Dict[str, Any]: JSON, List[str]: JSON}


class User(Base):
    """Clinician account (single role)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    consultations: Mapped[List["Consultation"]] = relationship(back_populates="user")


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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="consultations")


class GuidelineDocument(Base):
    """Persisted clinical guideline document, ingested via `/api/rag`.

    `embedding` uses `JSON` on SQLite (the in-memory test DB — pgvector has
    no SQLite equivalent) and `pgvector`'s native type on Postgres, so
    `Base.metadata.create_all` keeps working in both. Retrieval scoring
    itself always runs against the in-memory vector store
    (`data.vectors.InMemoryVectorStore`), not a live query against this
    table — see `data/rag/__init__.py`. This table exists purely so
    API-ingested documents survive a restart.

    No HNSW/IVFFlat index yet -- intentional while this table is empty (no
    ingestion endpoint writes to it today). Add one once real rows start
    landing here via `/api/rag` ingestion, not before.
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
    "TimelineEvent",
    "ClinicalNote",
    "Consultation",
    "GuidelineDocument",
]
