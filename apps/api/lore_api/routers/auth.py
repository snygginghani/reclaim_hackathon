import random

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from ..deps import CurrentUser, DbSession
from ..models import User
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    decode_token,
    hash_password,
    set_auth_cookies,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, response: Response, db: DbSession) -> User:
    email = body.email.lower()
    exists = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        name=body.name.strip(),
        avatar_hue=random.randint(0, 359),
    )
    db.add(user)
    await db.commit()
    set_auth_cookies(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
async def login(body: LoginIn, response: Response, db: DbSession) -> User:
    email = body.email.lower()
    user = (
        await db.execute(select(User).where(func.lower(User.email) == email))
    ).scalar_one_or_none()
    # Same error for unknown email and wrong password: no account enumeration.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    set_auth_cookies(response, user.id)
    return user


@router.post("/refresh", response_model=UserOut)
async def refresh(request: Request, response: Response, db: DbSession) -> User:
    token = request.cookies.get(REFRESH_COOKIE)
    user_id = decode_token(token, "refresh") if token else None
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        clear_auth_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    set_auth_cookies(response, user.id)  # rotation: both cookies reissued
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    clear_auth_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
