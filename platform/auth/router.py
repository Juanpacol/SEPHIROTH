"""Registration, login, current-user, and patient-portal-claim endpoints."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user, require_clinician_for_registration
from auth.security import create_access_token, hash_password, verify_password
from core.db import get_session
from data.schemas import PatientInvite, User

router = APIRouter()


class RegisterRequest(BaseModel):
    # `extra="forbid"`: a caller must never be able to smuggle `role` or
    # `patient_id` into a clinician registration — those are set only by
    # this handler (always "clinician") or by the invite/claim flow.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ClaimInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1)
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    patient_id: str | None = None


class UpdateProfileRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=120)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user.id),
        user=UserOut(
            id=user.id, email=user.email, name=user.name, role=user.role, patient_id=user.patient_id
        ),
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    dependencies=[Depends(require_clinician_for_registration)],
)
async def register(request: RegisterRequest, session: AsyncSession = Depends(get_session)) -> AuthResponse:
    """Clinician registration only — a patient account is created solely
    via `POST /api/auth/portal/claim` (see below), never here."""
    existing = await session.scalar(select(User).where(User.email == request.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=str(uuid4()),
        email=request.email,
        name=request.name,
        hashed_password=hash_password(request.password),
        role="clinician",
    )
    session.add(user)
    await session.commit()
    return _auth_response(user)


_INVALID_CLAIM_CODE = "Invalid or expired claim code"


@router.post("/portal/claim", response_model=AuthResponse, status_code=201)
async def claim_invite(
    request: ClaimInviteRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    """Redeem a clinician-issued invite code to create a patient portal
    login. Public (no auth) by design — this IS the patient's
    registration path, gated instead by possession of the one-time code a
    clinician handed them in person. Every failure mode (unknown id,
    already redeemed, expired, wrong secret) returns the identical 400
    detail string — distinguishing them would let an attacker use the
    endpoint as an oracle to enumerate valid invite ids."""
    invite_id, _, secret = request.code.partition(".")
    if not invite_id or not secret:
        raise HTTPException(status_code=400, detail=_INVALID_CLAIM_CODE)

    invite = await session.get(PatientInvite, invite_id)
    if (
        invite is None
        or invite.redeemed_at is not None
        or invite.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)
        or not verify_password(secret, invite.code_hash)
    ):
        raise HTTPException(status_code=400, detail=_INVALID_CLAIM_CODE)

    existing_email = await session.scalar(select(User).where(User.email == request.email))
    if existing_email:
        raise HTTPException(status_code=409, detail="Email already registered")

    existing_login = await session.scalar(select(User).where(User.patient_id == invite.patient_id))
    if existing_login:
        raise HTTPException(status_code=400, detail=_INVALID_CLAIM_CODE)

    user = User(
        id=str(uuid4()),
        email=request.email,
        name=request.name,
        hashed_password=hash_password(request.password),
        role="patient",
        patient_id=invite.patient_id,
    )
    session.add(user)
    # `flush()` before setting `redeemed_user_id`: it's a plain FK column,
    # not a relationship SQLAlchemy tracks between these two objects, so
    # nothing tells the unit of work the new user must be INSERTed before
    # this UPDATE — without the flush, Postgres (unlike SQLite) enforces
    # the FK immediately and rejects the still-unflushed user id.
    await session.flush()
    invite.redeemed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    invite.redeemed_user_id = user.id
    await session.commit()
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_session)) -> AuthResponse:
    user = await session.scalar(select(User).where(User.email == request.email))
    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role, patient_id=user.patient_id)


@router.patch("/me", response_model=UserOut)
async def update_profile(
    request: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    if request.email != user.email:
        existing = await session.scalar(select(User).where(User.email == request.email))
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
    user.email = request.email
    user.name = request.name
    await session.commit()
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role, patient_id=user.patient_id)


@router.post("/change-password", status_code=204)
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if not verify_password(request.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user.hashed_password = hash_password(request.new_password)
    await session.commit()
