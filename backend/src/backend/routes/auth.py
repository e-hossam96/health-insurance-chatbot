from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.auth import (
    SESSION_COOKIE,
    create_session,
    delete_session,
    hash_password,
    purge_expired,
    set_active_mode,
    verify_password,
)
from backend.deps import (
    ClockDep,
    CurrentAccount,
    CurrentSession,
    Db,
    SettingsDep,
)
from backend.errors import api_error, forbidden, rate_limited
from backend.metrics import record_rate_limit, signups_total
from backend.models import Account, AccountRole
from backend.ownership import find_profile
from backend.rate_limit import login_fail_limiter, signup_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    username: str
    password: str


class ModeRequest(BaseModel):
    mode: str


class MeResponse(BaseModel):
    username: str
    role: str
    has_profile: bool
    mode: str


def _set_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def _require_json(request: Request) -> None:
    ct = request.headers.get("content-type", "")
    if "application/json" not in ct:
        raise api_error("validation_error", "Content-Type must be application/json.", 422)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


@router.post("/signup", status_code=201)
async def signup(
    request: Request,
    body: SignupRequest,
    db: Db,
    settings: SettingsDep,
    clock: ClockDep,
    response: Response,
) -> dict[str, str]:
    _require_json(request)

    ip = _client_ip(request)
    retry = signup_limiter.check(ip, clock=clock)
    if retry is not None:
        record_rate_limit("signup")
        raise rate_limited("Too many requests.", retry)

    existing = await db.execute(
        select(Account).where(func.lower(Account.username) == body.username.lower())
    )
    if existing.scalar_one_or_none() is not None:
        signup_limiter.record(ip, clock=clock)
        raise api_error("username_taken", "Username is already taken.", 409)

    password_hash = hash_password(body.password)
    account = Account(
        username=body.username,
        password_hash=password_hash,
        role=AccountRole.user,
    )
    db.add(account)
    await db.flush()

    token = await create_session(
        db, account, settings.session_lifetime_days, clock=clock
    )
    await db.commit()

    signup_limiter.record(ip, clock=clock)
    signups_total.inc()
    _set_cookie(response, token, settings.session_lifetime_days * 86400)
    return {"message": "Account created."}


@router.post("/login")
async def login(
    request: Request,
    body: LoginRequest,
    db: Db,
    settings: SettingsDep,
    clock: ClockDep,
    response: Response,
) -> dict[str, str]:
    _require_json(request)

    ip = _client_ip(request)
    login_key = f"{ip}:{body.username.lower()}"
    retry = login_fail_limiter.check(login_key, clock=clock)
    if retry is not None:
        record_rate_limit("login")
        raise rate_limited("Too many requests.", retry)

    await purge_expired(db, clock=clock)

    result = await db.execute(
        select(Account).where(func.lower(Account.username) == body.username.lower())
    )
    account = result.scalar_one_or_none()
    if account is None or not verify_password(account.password_hash, body.password):
        login_fail_limiter.record(login_key, clock=clock)
        raise api_error("invalid_credentials", "Invalid username or password.", 401)

    token = await create_session(
        db, account, settings.session_lifetime_days, clock=clock
    )
    await db.commit()

    _set_cookie(response, token, settings.session_lifetime_days * 86400)
    return {"message": "Logged in."}


@router.post("/logout")
async def logout(
    request: Request,
    session: CurrentSession,
    db: Db,
    response: Response,
) -> dict[str, str]:
    _require_json(request)

    raw_token = request.cookies.get(SESSION_COOKIE, "")
    await delete_session(db, raw_token)
    await db.commit()

    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"message": "Logged out."}


@router.get("/me")
async def me(
    session: CurrentSession,
    account: CurrentAccount,
    db: Db,
) -> MeResponse:
    has_profile = await find_profile(db, account.id) is not None

    return MeResponse(
        username=account.username,
        role=account.role.value,
        has_profile=has_profile,
        mode=session.active_mode.value,
    )


@router.post("/mode")
async def set_mode(
    request: Request,
    body: ModeRequest,
    session: CurrentSession,
    account: CurrentAccount,
    db: Db,
) -> dict[str, str]:
    _require_json(request)

    if body.mode not in ("admin", "user"):
        raise api_error("validation_error", "Mode must be 'admin' or 'user'.", 422)

    mode = AccountRole(body.mode)
    if mode == AccountRole.admin and account.role != AccountRole.admin:
        raise forbidden("Only admins can set admin mode.")

    await set_active_mode(db, session, mode)
    await db.commit()

    return {"mode": mode.value}
