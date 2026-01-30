"""Stripe payment integration for subscription management."""

import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Header
import stripe

from core import get_current_user, AuthUser, settings
from core.deps import get_supabase
from core.user_limits import ensure_user_settings_exist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stripe", tags=["stripe"])

# Initialize Stripe
stripe.api_key = settings.stripe_secret_key
STRIPE_WEBHOOK_SECRET = settings.stripe_webhook_secret
PREMIUM_PRICE_ID = settings.stripe_price_id
PREMIUM_MAX_FILES = 2000  # Premium tier page limit
FREE_MAX_FILES = 200  # Free tier page limit
PREMIUM_MAX_MONTHLY_FILES = 500  # Premium tier monthly file uploads
FREE_MAX_MONTHLY_FILES = 50  # Free tier monthly file uploads


class CreateCheckoutSessionRequest(BaseModel):
    """Request to create a Stripe checkout session."""

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


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    auth: AuthUser = Depends(get_current_user),
    supabase=Depends(get_supabase),
):
    """Create a Stripe checkout session for premium subscription."""
    if not stripe.api_key:
        raise HTTPException(
            status_code=500,
            detail="Stripe is not configured. Please contact support."
        )

    if not PREMIUM_PRICE_ID:
        raise HTTPException(
            status_code=500,
            detail="Payment plan not configured. Please contact support."
        )

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": PREMIUM_PRICE_ID,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            client_reference_id=auth.id,
            customer_email=auth.email,
            metadata={"user_id": auth.id},
            subscription_data={"metadata": {"user_id": auth.id}}
        )

        logger.info(f"Created checkout session {session.id} for user {auth.id}")

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
            "stripe_subscription_id, stripe_subscription_status, stripe_current_period_end, stripe_cancel_at_period_end"
        ).eq("user_id", auth.id).execute()

        if not response.data or len(response.data) == 0:
            return SubscriptionStatusResponse(is_subscribed=False)

        settings_data = response.data[0]
        subscription_id = settings_data.get("stripe_subscription_id")
        status = settings_data.get("stripe_subscription_status")

        is_subscribed = status in ["active", "trialing"]

        return SubscriptionStatusResponse(
            is_subscribed=is_subscribed,
            subscription_id=subscription_id,
            status=status,
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
    supabase=Depends(get_supabase),
):
    """Handle Stripe webhook events."""
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook called but STRIPE_WEBHOOK_SECRET not configured")
        payload = await request.body()
        event = stripe.Event.construct_from(
            await request.json(), stripe.api_key
        )
    else:
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
            raise HTTPException(status_code=400, detail="Invalid signature")

    try:
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

    except Exception as e:
        logger.error(f"Error handling webhook event {event.type}: {e}")
        raise HTTPException(status_code=500, detail="Webhook handler failed")


async def handle_checkout_completed(session, supabase):
    """Handle successful checkout."""
    user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
    subscription_id = session.get("subscription")

    if not user_id:
        logger.error(f"Checkout session {session.id} has no user_id")
        return

    logger.info(f"Checkout completed for user {user_id}, subscription {subscription_id}")

    subscription = stripe.Subscription.retrieve(subscription_id)

    ensure_user_settings_exist(supabase, user_id)

    supabase.table("user_settings").update({
        "stripe_customer_id": session.customer,
        "stripe_subscription_id": subscription_id,
        "stripe_subscription_status": subscription.status,
        "stripe_current_period_end": subscription.current_period_end,
        "stripe_cancel_at_period_end": subscription.cancel_at_period_end,
        "max_files": PREMIUM_MAX_FILES,
        "max_monthly_files": PREMIUM_MAX_MONTHLY_FILES,
    }).eq("user_id", user_id).execute()

    logger.info(f"Activated premium subscription for user {user_id}")


async def handle_subscription_updated(subscription, supabase):
    """Handle subscription updates."""
    user_id = subscription.get("metadata", {}).get("user_id")

    if not user_id:
        logger.error(f"Subscription {subscription.id} has no user_id in metadata")
        return

    logger.info(f"Subscription updated for user {user_id}: status={subscription.status}")

    update_data = {
        "stripe_subscription_status": subscription.get("status"),
        "stripe_current_period_end": subscription.get("current_period_end"),
        "stripe_cancel_at_period_end": subscription.get("cancel_at_period_end", False),
    }

    if subscription.get("status") in ["active", "trialing"]:
        update_data["max_files"] = PREMIUM_MAX_FILES
        update_data["max_monthly_files"] = PREMIUM_MAX_MONTHLY_FILES
    elif subscription.get("status") in ["canceled", "unpaid", "past_due"]:
        update_data["max_files"] = FREE_MAX_FILES
        update_data["max_monthly_files"] = FREE_MAX_MONTHLY_FILES

    supabase.table("user_settings").update(update_data).eq("user_id", user_id).execute()


async def handle_subscription_deleted(subscription, supabase):
    """Handle subscription deletion."""
    user_id = subscription.get("metadata", {}).get("user_id")

    if not user_id:
        logger.error(f"Subscription {subscription.id} has no user_id in metadata")
        return

    logger.info(f"Subscription deleted for user {user_id}")

    supabase.table("user_settings").update({
        "stripe_subscription_status": "canceled",
        "stripe_cancel_at_period_end": False,
        "max_files": FREE_MAX_FILES,
        "max_monthly_files": FREE_MAX_MONTHLY_FILES,
    }).eq("user_id", user_id).execute()

    logger.info(f"Downgraded user {user_id} to free tier")
