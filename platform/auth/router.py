"""Registration, login, and current-user endpoints."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.deps import get_current_user
from auth.security import create_access_token, hash_password, verify_password
from core.db import get_session
from data.schemas import User

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user.id),
        user=UserOut(id=user.id, email=user.email, name=user.name),
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    request: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    existing = await session.scalar(select(User).where(User.email == request.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=str(uuid4()),
        email=request.email,
        name=request.name,
        hashed_password=hash_password(request.password),
    )
    session.add(user)
    await session.commit()
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    user = await session.scalar(select(User).where(User.email == request.email))
    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_response(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name)
