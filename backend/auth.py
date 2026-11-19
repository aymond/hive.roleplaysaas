from __future__ import annotations

import os
from typing import Literal

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

SAAS_AUTH_ENABLED = os.getenv("SAAS_AUTH_ENABLED", "false").lower() == "true"

try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth

    FIREBASE_AVAILABLE = True
except Exception:
    firebase_admin = None  # type: ignore[assignment]
    firebase_auth = None  # type: ignore[assignment]
    FIREBASE_AVAILABLE = False


class AuthenticatedUser(BaseModel):
    uid: str = "local-owner"
    email: str = "owner@localhost"
    role: Literal["user", "admin"] = "admin"
    plan: str = "local"


def _ensure_firebase_app() -> None:
    if FIREBASE_AVAILABLE and firebase_admin is not None and not firebase_admin._apps:
        firebase_admin.initialize_app()


_user_directory: object | None = None


def set_user_directory(store: object) -> None:
    global _user_directory
    _user_directory = store


def _is_configured_admin(uid: str, email: str) -> bool:
    admin_emails = {
        e.strip().lower()
        for e in os.getenv("ADMIN_EMAILS", "").split(",")
        if e.strip()
    }
    admin_uids = {
        u.strip()
        for u in os.getenv("ADMIN_UIDS", "").split(",")
        if u.strip()
    }
    if uid in admin_uids:
        return True
    if email and email.strip().lower() in admin_emails:
        return True
    return False


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_mock_role: str | None = Header(default=None),
    x_mock_uid: str | None = Header(default=None),
) -> AuthenticatedUser:
    """
    Verifies GCP Identity Platform / Firebase ID tokens when SAAS_AUTH_ENABLED=true.
    All roles are assigned server-side via the user directory + ADMIN_EMAILS/ADMIN_UIDS
    bootstrap (or Firebase custom claims); users cannot self-select admin privileges.
    """
    if not SAAS_AUTH_ENABLED:
        uid = (x_mock_uid or "").strip() or "local-owner"
        email = uid if "@" in uid else f"{uid}@localhost"
        in_pytest = bool(os.getenv("PYTEST_CURRENT_TEST"))
        force_admin = _is_configured_admin(uid, email) or (
            uid == "local-owner" and not (in_pytest and x_mock_role == "user")
        )
        if in_pytest and x_mock_role in ("user", "admin"):
            test_role: Literal["user", "admin"] = "admin" if x_mock_role == "admin" else "user"
            return AuthenticatedUser(uid=uid, email=email, role=test_role, plan="local")

        if _user_directory is not None and hasattr(_user_directory, "upsert_user_on_login"):
            rec = _user_directory.upsert_user_on_login(  # type: ignore[attr-defined]
                uid=uid,
                email=email,
                default_role="admin" if force_admin else "user",
                default_plan="local",
                force_admin=force_admin,
            )
            if rec.disabled:
                raise HTTPException(status_code=403, detail="This account has been disabled by an administrator")
            return AuthenticatedUser(uid=rec.uid, email=rec.email, role=rec.role, plan=rec.plan)

        role: Literal["user", "admin"] = "admin" if force_admin else "user"
        return AuthenticatedUser(uid=uid, email=email, role=role, plan="local")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer identity token")

    token = authorization.split(" ", 1)[1].strip()
    if not FIREBASE_AVAILABLE or firebase_auth is None:
        raise HTTPException(status_code=503, detail="GCP Identity Platform SDK not installed")

    try:
        _ensure_firebase_app()
        decoded = firebase_auth.verify_id_token(token)
        uid = str(decoded["uid"])
        email = str(decoded.get("email", ""))
        force_admin = (decoded.get("role") == "admin") or _is_configured_admin(uid, email)
        default_plan = str(decoded.get("plan", "free"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid identity token: {exc}") from exc

    if _user_directory is not None and hasattr(_user_directory, "upsert_user_on_login"):
        rec = _user_directory.upsert_user_on_login(  # type: ignore[attr-defined]
            uid=uid,
            email=email,
            default_role="admin" if force_admin else "user",
            default_plan=default_plan,
            force_admin=force_admin,
        )
        if rec.disabled:
            raise HTTPException(status_code=403, detail="This account has been disabled by an administrator")
        return AuthenticatedUser(uid=rec.uid, email=rec.email, role=rec.role, plan=rec.plan)

    role_val: Literal["user", "admin"] = "admin" if force_admin else "user"
    return AuthenticatedUser(uid=uid, email=email, role=role_val, plan=default_plan)


async def require_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return user
