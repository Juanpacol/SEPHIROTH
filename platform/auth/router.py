"""Registration, login, current-user, patient-portal-claim, account
lifecycle (deactivate/password-reset/TOTP MFA) endpoints."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

import pyotp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user, require_clinician_for_registration
from auth.security import (
    create_access_token,
    create_mfa_pending_token,
    decode_mfa_pending_token,
    hash_password,
    verify_password,
)
from core.config import settings
from core.db import get_session
from data.schemas import MfaRecoveryCode, PasswordResetToken, PatientInvite, User

router = APIRouter()

PASSWORD_RESET_TTL = timedelta(hours=1)
MFA_RECOVERY_CODE_COUNT = 10
_INVALID_RESET_TOKEN = "Invalid or expired reset token"
_INVALID_MFA_CODE = "Invalid or expired code"


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


class LoginResponse(BaseModel):
    """`POST /login`'s shape when the account has TOTP enabled: the caller
    gets a short-lived `mfa_token` instead of a real session, and must
    complete `POST /login/mfa` to obtain one."""

    mfa_required: bool = False
    mfa_token: Optional[str] = None
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserOut] = None


class DeactivateRequest(BaseModel):
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetResponse(BaseModel):
    # Always 202'd regardless of whether `email` exists (no user
    # enumeration via status code); `reset_token` is present only when it
    # does — see the module docstring on `PasswordResetToken` for why this
    # is returned directly rather than emailed.
    reset_token: Optional[str] = None


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str


class MfaVerifyResponse(BaseModel):
    recovery_codes: List[str]


class MfaDisableRequest(BaseModel):
    password: str
    code: str


class MfaLoginRequest(BaseModel):
    mfa_token: str
    code: str


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


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    user = await session.scalar(select(User).where(User.email == request.email))
    if user is None or not user.is_active or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.mfa_enabled:
        return LoginResponse(mfa_required=True, mfa_token=create_mfa_pending_token(user.id))
    auth = _auth_response(user)
    return LoginResponse(access_token=auth.access_token, token_type=auth.token_type, user=auth.user)


async def _verify_mfa_code(session: AsyncSession, user: User, code: str) -> bool:
    """Accepts either a live 6-digit TOTP code or a single-use recovery
    code — checked in that order since TOTP is the common case."""
    if user.mfa_secret and pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
        return True
    recovery_codes = (
        await session.scalars(
            select(MfaRecoveryCode).where(
                MfaRecoveryCode.user_id == user.id, MfaRecoveryCode.used_at.is_(None)
            )
        )
    ).all()
    for rc in recovery_codes:
        if verify_password(code, rc.code_hash):
            rc.used_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.commit()
            return True
    return False


@router.post("/login/mfa", response_model=AuthResponse)
async def login_mfa(request: MfaLoginRequest, session: AsyncSession = Depends(get_session)) -> AuthResponse:
    user_id = decode_mfa_pending_token(request.mfa_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail=_INVALID_MFA_CODE)
    user = await session.get(User, user_id)
    if user is None or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status_code=401, detail=_INVALID_MFA_CODE)
    if not await _verify_mfa_code(session, user, request.code):
        raise HTTPException(status_code=401, detail=_INVALID_MFA_CODE)
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


@router.post("/account/deactivate", status_code=204)
async def deactivate_account(
    request: DeactivateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Self-service deactivation, gated by re-entering the current
    password (not just an already-valid bearer token) — the same bar as
    `change_password`. Data is never deleted: a clinician's consultations
    and a patient's chart both remain intact; only login is blocked
    (`get_current_user` checks `is_active` on every request)."""
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user.is_active = False
    await session.commit()


@router.post("/password-reset/request", response_model=PasswordResetResponse, status_code=202)
async def request_password_reset(
    request: PasswordResetRequest, session: AsyncSession = Depends(get_session)
) -> PasswordResetResponse:
    """Always 202s. No send capability exists in this codebase (see
    `PatientInvite`'s precedent) — the raw token is returned directly in
    the response when the account exists, rather than emailed."""
    user = await session.scalar(select(User).where(User.email == request.email))
    if user is None or not user.is_active:
        return PasswordResetResponse()

    secret = secrets.token_urlsafe(24)
    reset = PasswordResetToken(
        id=str(uuid4()),
        user_id=user.id,
        code_hash=hash_password(secret),
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + PASSWORD_RESET_TTL,
    )
    session.add(reset)
    await session.commit()
    return PasswordResetResponse(reset_token=f"{reset.id}.{secret}")


@router.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    request: PasswordResetConfirm, session: AsyncSession = Depends(get_session)
) -> None:
    token_id, _, secret = request.token.partition(".")
    if not token_id or not secret:
        raise HTTPException(status_code=400, detail=_INVALID_RESET_TOKEN)

    reset = await session.get(PasswordResetToken, token_id)
    if (
        reset is None
        or reset.redeemed_at is not None
        or reset.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)
        or not verify_password(secret, reset.code_hash)
    ):
        raise HTTPException(status_code=400, detail=_INVALID_RESET_TOKEN)

    user = await session.get(User, reset.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail=_INVALID_RESET_TOKEN)

    user.hashed_password = hash_password(request.new_password)
    reset.redeemed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.commit()


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> MfaEnrollResponse:
    """Generates a new TOTP secret and returns its provisioning URI for
    client-side QR rendering (no server-side QR image generation — one
    less dependency). Does not enable MFA yet; `POST /mfa/verify`
    confirms the enrollment actually works before flipping the switch."""
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    await session.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=settings.api_title)
    return MfaEnrollResponse(secret=secret, provisioning_uri=uri)


@router.post("/mfa/verify", response_model=MfaVerifyResponse)
async def mfa_verify(
    request: MfaVerifyRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MfaVerifyResponse:
    if not user.mfa_secret or not pyotp.TOTP(user.mfa_secret).verify(request.code, valid_window=1):
        raise HTTPException(status_code=400, detail=_INVALID_MFA_CODE)

    user.mfa_enabled = True
    codes = [secrets.token_hex(5) for _ in range(MFA_RECOVERY_CODE_COUNT)]
    session.add_all(
        [MfaRecoveryCode(id=str(uuid4()), user_id=user.id, code_hash=hash_password(c)) for c in codes]
    )
    await session.commit()
    return MfaVerifyResponse(recovery_codes=codes)


@router.post("/mfa/disable", status_code=204)
async def mfa_disable(
    request: MfaDisableRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if not await _verify_mfa_code(session, user, request.code):
        raise HTTPException(status_code=400, detail=_INVALID_MFA_CODE)

    user.mfa_enabled = False
    user.mfa_secret = None
    existing_codes = (
        await session.scalars(select(MfaRecoveryCode).where(MfaRecoveryCode.user_id == user.id))
    ).all()
    for rc in existing_codes:
        await session.delete(rc)
    await session.commit()
