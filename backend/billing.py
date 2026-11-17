from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from .auth import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    price_id: str
    mode: Literal["subscription", "payment"] = "subscription"
    success_url: str
    cancel_url: str


@router.get("/status")
async def get_billing_status(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "uid": user.uid,
        "plan": user.plan,
        "stripe_configured": bool(os.getenv("STRIPE_SECRET_KEY")),
    }


@router.post("/checkout")
async def create_checkout_session(
    req: CheckoutRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured (missing STRIPE_SECRET_KEY)")
    try:
        import stripe  # type: ignore[import-not-found]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"stripe package not installed: {exc}") from exc

    stripe.api_key = secret_key
    session = stripe.checkout.Session.create(
        mode=req.mode,
        line_items=[{"price": req.price_id, "quantity": 1}],
        success_url=req.success_url,
        cancel_url=req.cancel_url,
        client_reference_id=user.uid,
        customer_email=user.email or None,
        metadata={"uid": user.uid},
    )
    return {"checkout_url": str(session.url), "session_id": str(session.id)}


@router.post("/portal")
async def create_billing_portal(
    return_url: str,
    customer_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured (missing STRIPE_SECRET_KEY)")
    try:
        import stripe  # type: ignore[import-not-found]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"stripe package not installed: {exc}") from exc

    stripe.api_key = secret_key
    portal = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return {"portal_url": str(portal.url)}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook secret not configured")
    try:
        import stripe  # type: ignore[import-not-found]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"stripe package not installed: {exc}") from exc

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe webhook signature: {exc}") from exc

    return {"received": True, "event_type": event.get("type"), "event_id": event.get("id")}
