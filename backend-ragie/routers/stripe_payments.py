"""Stripe payment integration for subscription management."""

import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Header
import stripe

from core import get_current_user, AuthUser, settings, get_supabase_for_webhook
from core.deps import get_supabase
from core.user_limits import (
    ensure_user_settings_exist,
    TIER_LIMITS,
    PRO_MAX_FILES,
    MAX_MAX_FILES,
    DEFAULT_MAX_FILES,
    PRO_MAX_MONTHLY_FILES,
    MAX_MAX_MONTHLY_FILES,
    DEFAULT_MAX_MONTHLY_FILES,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stripe", tags=["stripe"])

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key
STRIPE_WEBHOOK_SECRET = settings.stripe_webhook_secret
PRO_PRICE_ID = settings.stripe_pro_price_id
MAX_PRICE_ID = settings.stripe_max_price_id


class CreateCheckoutSessionRequest(BaseModel):
    """Request to create a Stripe checkout session."""

    tier: str  # "pro" or "max"
    success_url: str
    cancel_url: str


class CheckoutSessionResponse(BaseModel):
    """Response containing checkout session URL."""

    session_id: str
    url: str


class SubscriptionStatusResponse(BaseModel):
    """User's current subscription status."""

    is_subscribed: bool
    subscription_id: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[int] = None
    cancel_at_period_end: Optional[bool] = None
    tier: Optional[str] = None


def get_tier_from_price_id(price_id: str) -> str:
    """Map Stripe price ID to subscription tier."""
    if price_id == PRO_PRICE_ID:
        return "pro"
    elif price_id == MAX_PRICE_ID:
        return "max"
    return "free"


def get_price_id_from_tier(tier: str) -> str:
    """Map subscription tier to Stripe price ID."""
    if tier == "pro":
        return PRO_PRICE_ID
    elif tier == "max":
        return MAX_PRICE_ID
    raise ValueError(f"Invalid tier: {tier}. Must be 'pro' or 'max'.")


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """Create a Stripe checkout session for Pro or Max subscription."""
    if not stripe.api_key:
        raise HTTPException(
            status_code=500,
            detail="Stripe is not configured. Please contact support."
        )

    # Validate tier
    if request.tier not in ["pro", "max"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid tier. Must be 'pro' or 'max'."
        )

    try:
        price_id = get_price_id_from_tier(request.tier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not price_id:
        raise HTTPException(
            status_code=500,
            detail="Payment plan not configured. Please contact support."
        )

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            client_reference_id=auth.id,
            customer_email=auth.email,
            metadata={"user_id": auth.id, "tier": request.tier},
            subscription_data={"metadata": {"user_id": auth.id, "tier": request.tier}}
        )

        logger.info(f"Created {request.tier} checkout session {session.id} for user {auth.id}")

        return CheckoutSessionResponse(
            session_id=session.id,
            url=session.url
        )

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Payment system error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create checkout session"
        )


@router.get("/subscription-status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """Get current subscription status."""
    try:
        response = supabase.table("user_settings").select(
            "stripe_subscription_id, stripe_subscription_status, stripe_current_period_end, stripe_cancel_at_period_end, subscription_tier"
        ).eq("user_id", auth.id).execute()

        if not response.data or len(response.data) == 0:
            return SubscriptionStatusResponse(is_subscribed=False, tier="free")

        settings_data = response.data[0]
        subscription_id = settings_data.get("stripe_subscription_id")
        status = settings_data.get("stripe_subscription_status")
        tier = settings_data.get("subscription_tier", "free")

        is_subscribed = status in ["active", "trialing"]

        return SubscriptionStatusResponse(
            is_subscribed=is_subscribed,
            subscription_id=subscription_id,
            status=status,
            tier=tier,
            current_period_end=settings_data.get("stripe_current_period_end"),
            cancel_at_period_end=settings_data.get("stripe_cancel_at_period_end", False)
        )

    except Exception as e:
        logger.error(f"Error getting subscription status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get subscription status"
        )


@router.post("/cancel-subscription")
async def cancel_subscription(
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """Cancel subscription at end of billing period."""
    if not stripe.api_key:
        raise HTTPException(
            status_code=500,
            detail="Stripe is not configured"
        )

    try:
        response = supabase.table("user_settings").select(
            "stripe_subscription_id"
        ).eq("user_id", auth.id).execute()

        if not response.data or not response.data[0].get("stripe_subscription_id"):
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )

        subscription_id = response.data[0]["stripe_subscription_id"]

        subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True
        )

        supabase.table("user_settings").update({
            "stripe_cancel_at_period_end": True
        }).eq("user_id", auth.id).execute()

        logger.info(f"Cancelled subscription {subscription_id} for user {auth.id}")

        return {
            "success": True,
            "message": "Subscription will be cancelled at the end of the billing period",
            "current_period_end": subscription.current_period_end
        }

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error cancelling subscription: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Payment system error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to cancel subscription"
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    supabase=Depends(get_supabase_for_webhook),
):
    """Handle Stripe webhook events.

    SECURITY: This endpoint requires valid Stripe webhook signature verification.
    Unsigned webhooks are always rejected to prevent forged events.
    """
    if not STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured. Webhook rejected.")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not stripe_signature:
        logger.error("Webhook request missing stripe-signature header")
        raise HTTPException(status_code=400, detail="Missing signature header")

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        # Check if we've already processed this webhook event (idempotency guard)
        event_id = event.id
        existing = supabase.table("webhook_events").select("id").eq("stripe_event_id", event_id).execute()

        if existing.data and len(existing.data) > 0:
            logger.info(f"Webhook event {event_id} already processed, skipping")
            return {"status": "success"}

        if event.type == "checkout.session.completed":
            session = event.data.object
            await handle_checkout_completed(session, supabase)

        elif event.type == "customer.subscription.updated":
            subscription = event.data.object
            await handle_subscription_updated(subscription, supabase)

        elif event.type == "customer.subscription.deleted":
            subscription = event.data.object
            await handle_subscription_deleted(subscription, supabase)

        else:
            logger.info(f"Unhandled webhook event type: {event.type}")
            return {"status": "success"}

        # Record that we processed this event
        user_id = None
        if event.type in ["customer.subscription.updated", "customer.subscription.deleted"]:
            user_id = event.data.object.get("metadata", {}).get("user_id")
        elif event.type == "checkout.session.completed":
            user_id = event.data.object.get("client_reference_id") or event.data.object.get("metadata", {}).get("user_id")

        try:
            supabase.table("webhook_events").insert({
                "stripe_event_id": event_id,
                "event_type": event.type,
                "user_id": user_id
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to record webhook event {event_id}: {e}")
            # Continue anyway - event was processed successfully

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error handling webhook event {event.type}: {e}")
        raise HTTPException(status_code=500, detail="Webhook handler failed")


async def handle_checkout_completed(session, supabase):
    """Handle successful checkout."""
    user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
    subscription_id = session.get("subscription")

    if not user_id:
        logger.error(f"Checkout session {session.get('id')} has no user_id")
        return

    logger.info(f"Checkout completed for user {user_id}, subscription {subscription_id}")

    subscription = stripe.Subscription.retrieve(subscription_id)

    # Determine tier from subscription item price ID (most reliable source)
    tier = "free"
    for item in subscription.get("items", {}).get("data", []):
        detected_tier = get_tier_from_price_id(item.get("price", {}).get("id", ""))
        if detected_tier != "free":
            tier = detected_tier
            break

    # Fall back to metadata if no tier was detected from items
    if tier == "free" and session.get("metadata", {}).get("tier"):
        tier = session.get("metadata", {}).get("tier")

    logger.info(f"Detected tier: {tier}")

    ensure_user_settings_exist(supabase, user_id)

    # Get tier limits
    tier_limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    supabase.table("user_settings").update({
        "stripe_customer_id": session.get("customer"),
        "stripe_subscription_id": subscription_id,
        "stripe_subscription_status": subscription.get("status"),
        "stripe_current_period_end": subscription.get("current_period_end"),
        "stripe_cancel_at_period_end": subscription.get("cancel_at_period_end"),
        "subscription_tier": tier,
        "max_files": tier_limits["max_files"],
        "max_monthly_files": tier_limits["max_monthly_files"],
        "max_monthly_throughput_bytes": tier_limits["max_monthly_throughput"],
    }).eq("user_id", user_id).execute()

    logger.info(f"Activated {tier} subscription for user {user_id}")


async def handle_subscription_updated(subscription, supabase):
    """Handle subscription updates."""
    user_id = subscription.get("metadata", {}).get("user_id")

    if not user_id:
        logger.error(f"Subscription {subscription.id} has no user_id in metadata")
        return

    logger.info(f"Subscription updated for user {user_id}: status={subscription.status}")

    # Determine tier from subscription items
    tier = "free"
    if subscription.get("status") in ["active", "trialing"]:
        for item in subscription.get("items", {}).get("data", []):
            tier = get_tier_from_price_id(item.get("price", {}).get("id", ""))
            if tier != "free":
                break

    # Get tier limits
    tier_limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    update_data = {
        "stripe_subscription_status": subscription.get("status"),
        "stripe_current_period_end": subscription.get("current_period_end"),
        "stripe_cancel_at_period_end": subscription.get("cancel_at_period_end", False),
        "subscription_tier": tier,
        "max_files": tier_limits["max_files"],
        "max_monthly_files": tier_limits["max_monthly_files"],
        "max_monthly_throughput_bytes": tier_limits["max_monthly_throughput"],
    }

    supabase.table("user_settings").update(update_data).eq("user_id", user_id).execute()
    logger.info(f"Updated subscription for user {user_id} to tier {tier}")


async def handle_subscription_deleted(subscription, supabase):
    """Handle subscription deletion."""
    user_id = subscription.get("metadata", {}).get("user_id")

    if not user_id:
        logger.error(f"Subscription {subscription.id} has no user_id in metadata")
        return

    logger.info(f"Subscription deleted for user {user_id}")

    from core.user_limits import DEFAULT_MAX_MONTHLY_THROUGHPUT

    supabase.table("user_settings").update({
        "stripe_subscription_status": "canceled",
        "stripe_cancel_at_period_end": False,
        "subscription_tier": "free",
        "max_files": DEFAULT_MAX_FILES,
        "max_monthly_files": DEFAULT_MAX_MONTHLY_FILES,
        "max_monthly_throughput_bytes": DEFAULT_MAX_MONTHLY_THROUGHPUT,
    }).eq("user_id", user_id).execute()

    logger.info(f"Downgraded user {user_id} to free tier")
