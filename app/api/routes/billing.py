"""
Stripe billing routes.

GET  /billing/plans            — public plan catalogue
POST /billing/checkout         — create Stripe Checkout Session (upgrade flow)
GET  /billing/portal           — Stripe Customer Portal link (manage subscription)
GET  /billing/status           — current plan + subscription info for dashboard
POST /billing/webhook          — Stripe webhook handler (raw body, no JWT)

Stripe test mode setup (no account needed to start):
  1. Create free account at stripe.com
  2. Dashboard → Developers → API keys → copy "Secret key" (sk_test_...)
  3. Create two Products + Prices:
       Starter  $199/month  → copy Price ID (price_...)
       Pro      $499/month  → copy Price ID (price_...)
  4. Set in .env:
       STRIPE_SECRET_KEY=sk_test_...
       STRIPE_STARTER_PRICE_ID=price_...
       STRIPE_PRO_PRICE_ID=price_...
  5. For webhooks locally: stripe listen --forward-to localhost:8000/api/v1/billing/webhook
       Copy the webhook signing secret (whsec_...) → STRIPE_WEBHOOK_SECRET
"""
import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_tenant, get_current_user
from app.db.base import get_db
from app.db.models import Tenant, User

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/billing")

# ── Plan catalogue ────────────────────────────────────────────────────────────

PLANS = {
    "trial": {
        "name": "Trial",
        "price_monthly": 0,
        "device_limit": 5,
        "duration_days": 14,
        "features": ["5 devices", "14-day trial", "All features"],
        "stripe_price_id": None,
    },
    "starter": {
        "name": "Starter",
        "price_monthly": 199,
        "device_limit": 25,
        "duration_days": None,
        "features": ["25 devices", "Entra SSO / PSSO", "Compliance reporting", "Email support"],
        "stripe_price_id": settings.stripe_starter_price_id or None,
    },
    "professional": {
        "name": "Professional",
        "price_monthly": 499,
        "device_limit": 100,
        "duration_days": None,
        "features": ["100 devices", "Everything in Starter", "Audit log export", "Priority support"],
        "stripe_price_id": settings.stripe_pro_price_id or None,
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly": None,
        "device_limit": 999_999,
        "duration_days": None,
        "features": ["Unlimited devices", "Custom SLA", "SSO", "Dedicated support"],
        "stripe_price_id": None,
    },
}


def _stripe_client() -> stripe.StripeClient:
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    return stripe.StripeClient(settings.stripe_secret_key)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans():
    """Public — returns the plan catalogue without Stripe price IDs."""
    return [
        {k: v for k, v in plan.items() if k != "stripe_price_id"}
        for plan in PLANS.values()
    ]


@router.get("/status")
async def billing_status(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Current plan, device limit, trial expiry, and billing status."""
    plan_meta = PLANS.get(tenant.plan, PLANS["trial"])
    return {
        "plan": tenant.plan,
        "plan_name": plan_meta["name"],
        "billing_status": tenant.billing_status,
        "device_limit": tenant.plan_device_limit,
        "trial_ends_at": tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None,
        "trial_expired": (
            tenant.trial_ends_at is not None
            and tenant.trial_ends_at < datetime.utcnow()
        ),
        "features": plan_meta["features"],
        "has_stripe": bool(tenant.stripe_customer_id),
    }


@router.post("/checkout")
async def create_checkout_session(
    plan: str,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(get_current_user),
):
    """
    Create a Stripe Checkout Session for the requested plan.
    Returns {url} — redirect the browser to this URL.
    """
    if plan not in ("starter", "professional"):
        raise HTTPException(status_code=400, detail="Invalid plan. Choose starter or professional")

    price_id = PLANS[plan]["stripe_price_id"]
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Stripe price ID for '{plan}' is not configured. Set STRIPE_{plan.upper()}_PRICE_ID in .env",
        )

    client = _stripe_client()

    # Create or reuse the Stripe Customer
    customer_id = tenant.stripe_customer_id
    if not customer_id:
        customer = client.customers.create(params={
            "email": user.email,
            "name": tenant.name,
            "metadata": {"tenant_id": tenant.id, "tenant_slug": tenant.slug},
        })
        customer_id = customer.id

    session = client.checkout.sessions.create(params={
        "customer": customer_id,
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{settings.app_base_url}/settings?billing=success",
        "cancel_url": f"{settings.app_base_url}/settings?billing=cancel",
        "metadata": {"tenant_id": tenant.id, "plan": plan},
        "subscription_data": {
            "metadata": {"tenant_id": tenant.id, "plan": plan},
        },
        "allow_promotion_codes": True,
    })

    log.info("Checkout session created tenant=%s plan=%s", tenant.slug, plan)
    return {"url": session.url}


@router.get("/portal")
async def billing_portal(
    tenant: Tenant = Depends(get_current_tenant),
):
    """Return a Stripe Customer Portal URL so the tenant can manage their subscription."""
    if not tenant.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No active subscription. Please upgrade first.",
        )

    client = _stripe_client()
    session = client.billing_portal.sessions.create(params={
        "customer": tenant.stripe_customer_id,
        "return_url": f"{settings.app_base_url}/settings",
    })
    return {"url": session.url}


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Stripe sends events here. Must verify the signature before trusting the payload.
    Configure in Stripe Dashboard → Developers → Webhooks.

    Events handled:
      checkout.session.completed       → activate subscription
      customer.subscription.updated    → plan change / renewal
      customer.subscription.deleted    → cancel → downgrade to trial limits
      invoice.payment_failed           → mark billing_status=past_due
    """
    body = await request.body()

    if not settings.stripe_webhook_secret:
        log.warning("Stripe webhook secret not set — skipping signature verification")
        try:
            event = stripe.Event.construct_from(
                await request.json(), stripe.api_key
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")
    else:
        try:
            event = stripe.WebhookSignature.verify_header(
                body.decode(), stripe_signature, settings.stripe_webhook_secret
            )
            # verify_header raises on failure; on success we still need to parse
            event = stripe.Event.construct_from(
                __import__("json").loads(body), settings.stripe_secret_key
            )
        except stripe.SignatureVerificationError:
            log.warning("Stripe webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid signature")

    await _handle_event(event, db)
    return {"received": True}


async def _handle_event(event: stripe.Event, db: AsyncSession) -> None:
    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        tenant_id = obj.get("metadata", {}).get("tenant_id")
        plan = obj.get("metadata", {}).get("plan", "starter")
        customer_id = obj.get("customer")
        subscription_id = obj.get("subscription")
        if not tenant_id:
            return
        await _activate_plan(db, tenant_id, plan, customer_id, subscription_id)

    elif etype == "customer.subscription.updated":
        tenant_id = obj.get("metadata", {}).get("tenant_id")
        plan = obj.get("metadata", {}).get("plan", "starter")
        sub_status = obj.get("status", "active")
        if not tenant_id:
            return
        billing_status = "active" if sub_status == "active" else sub_status
        plan_limit = PLANS.get(plan, PLANS["starter"])["device_limit"]
        await db.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(
                plan=plan,
                billing_status=billing_status,
                plan_device_limit=plan_limit,
                stripe_subscription_id=obj.get("id"),
            )
        )
        log.info("Subscription updated tenant=%s plan=%s status=%s", tenant_id, plan, billing_status)

    elif etype == "customer.subscription.deleted":
        tenant_id = obj.get("metadata", {}).get("tenant_id")
        if not tenant_id:
            return
        # Downgrade to trial limits (don't delete data)
        await db.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(
                plan="trial",
                billing_status="canceled",
                plan_device_limit=5,
                stripe_subscription_id=None,
            )
        )
        log.info("Subscription canceled — tenant=%s downgraded to trial", tenant_id)

    elif etype == "invoice.payment_failed":
        customer_id = obj.get("customer")
        if not customer_id:
            return
        await db.execute(
            update(Tenant)
            .where(Tenant.stripe_customer_id == customer_id)
            .values(billing_status="past_due")
        )
        log.warning("Payment failed for Stripe customer=%s", customer_id)


async def _activate_plan(
    db: AsyncSession,
    tenant_id: str,
    plan: str,
    customer_id: str | None,
    subscription_id: str | None,
) -> None:
    plan_meta = PLANS.get(plan, PLANS["starter"])
    await db.execute(
        update(Tenant)
        .where(Tenant.id == tenant_id)
        .values(
            plan=plan,
            billing_status="active",
            plan_device_limit=plan_meta["device_limit"],
            trial_ends_at=None,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
        )
    )
    log.info("Plan activated tenant=%s plan=%s customer=%s", tenant_id, plan, customer_id)
