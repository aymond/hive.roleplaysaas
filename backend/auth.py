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


async def get_current_user(
    authorization: str | None = Header(default=None),
    x_mock_role: str | None = Header(default=None),
) -> AuthenticatedUser:
    """
    Verifies GCP Identity Platform / Firebase ID tokens when SAAS_AUTH_ENABLED=true.
    In local self-hosted mode (SAAS_AUTH_ENABLED=false), defaults to local admin
    unless `X-Mock-Role: user` is supplied for testing RBAC.
    """
    if not SAAS_AUTH_ENABLED:
        role: Literal["user", "admin"] = "user" if x_mock_role == "user" else "admin"
        return AuthenticatedUser(uid="local-owner", email="owner@localhost", role=role, plan="local")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer identity token")

    token = authorization.split(" ", 1)[1].strip()
    if not FIREBASE_AVAILABLE or firebase_auth is None:
        raise HTTPException(status_code=503, detail="GCP Identity Platform SDK not installed")

    try:
        _ensure_firebase_app()
        decoded = firebase_auth.verify_id_token(token)
        role_claim = decoded.get("role", "user")
        role_val: Literal["user", "admin"] = "admin" if role_claim == "admin" else "user"
        return AuthenticatedUser(
            uid=str(decoded["uid"]),
            email=str(decoded.get("email", "")),
            role=role_val,
            plan=str(decoded.get("plan", "free")),
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid identity token: {exc}") from exc


async def require_admin(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return user
