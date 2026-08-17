"""Authentication and authorization dependencies for protected routes."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.security import decode_access_token
from core.config import settings
from core.db import get_session
from data.schemas import Patient, User

ROLE_CLINICIAN = "clinician"
ROLE_PATIENT = "patient"

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


async def require_clinician(user: User = Depends(get_current_user)) -> User:
    """Guards every clinician surface. 403, not 404 — the caller is
    authenticated, just not entitled; hiding the route's existence buys
    nothing here."""
    if user.role != ROLE_CLINICIAN:
        raise HTTPException(status_code=403, detail="Clinician access required")
    return user


async def require_patient(user: User = Depends(get_current_user)) -> User:
    """Guards the patient portal. The DB `CheckConstraint` already
    guarantees a patient role carries a `patient_id`, but re-assert it
    here — a 403 is strictly better than an `AttributeError` deeper in a
    handler."""
    if user.role != ROLE_PATIENT or user.patient_id is None:
        raise HTTPException(status_code=403, detail="Patient portal access required")
    return user


async def require_clinician_for_registration(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Guards `POST /api/auth/register`. When
    `settings.allow_bootstrap_registration` is on (the dev/test default),
    registration is open — there's no clinician yet on a fresh database to
    gate behind. When it's off, a valid clinician bearer token is
    required, so account creation can't be self-service in a deployed
    environment. Never lets a patient token through, even with the flag
    off — a patient account is created only via `PatientInvite` claim."""
    if settings.allow_bootstrap_registration:
        return

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    if user.role != ROLE_CLINICIAN:
        raise HTTPException(status_code=403, detail="Clinician access required")


async def current_patient_record(
    user: User = Depends(require_patient),
    session: AsyncSession = Depends(get_session),
) -> Patient:
    """The portal's one data entrypoint: the patient is derived entirely
    from the token, never from a client-supplied id, so there is no
    parameter for a caller to tamper with."""
    patient = await session.scalar(
        select(Patient).where(Patient.id == user.patient_id).options(selectinload(Patient.timeline))
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient record not found")
    return patient
