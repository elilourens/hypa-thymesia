"""
Stripe payment integration for subscription management.
Handles checkout sessions, webhooks, and subscription status.
"""
import os
import logging
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Header
import stripe

from core.deps import get_supabase
from core.security import get_current_user, AuthUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stripe", tags=["stripe"])

# Initialize Stripe with your secret key
# Set this in your .env file: STRIPE_SECRET_KEY=sk_test_...
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")  # For webhook verification

# Stripe Price ID for the £2.99/month plan (you'll create this in Stripe Dashboard)
# Set this in your .env file: STRIPE_PRICE_ID=price_...
PREMIUM_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
PREMIUM_MAX_FILES = 100  # Premium tier allows 100 files


class CreateCheckoutSessionRequest(BaseModel):
    """Request to create a Stripe checkout session"""
    success_url: str  # Where to redirect after successful payment
    cancel_url: str   # Where to redirect if user cancels


class CheckoutSessionResponse(BaseModel):
    """Response containing checkout session URL"""
    session_id: str
    url: str


class SubscriptionStatusResponse(BaseModel):
    """User's current subscription status"""
    is_subscribed: bool
    subscription_id: Optional[str] = None
    status: Optional[str] = None
    current_period_end: Optional[int] = None
    cancel_at_period_end: Optional[bool] = None


@router.post("/create-checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    request: CreateCheckoutSessionRequest,
    auth: AuthUser = Depends(get_current_user),
    supabase = Depends(get_supabase),
):
    """
    Create a Stripe checkout session for the premium subscription.
    Returns a URL to redirect the user to Stripe's hosted checkout page.
    """
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
        # Create a Stripe checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": PREMIUM_PRICE_ID,
                "quantity": 1,
            }],
            mode="subscription",
            success_url=request.success_url,
            cancel_url=request.cancel_url,
            client_reference_id=auth.id,  # Store user ID to link subscription
            customer_email=auth.email,
            metadata={
                "user_id": auth.id,
            },
            subscription_data={
                "metadata": {
                    "user_id": auth.id,
                }
            }
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
    supabase = Depends(get_supabase),
):
    """
    Get the current user's subscription status from the database.
    """
    try:
        # Check user_settings for subscription info
        response = supabase.table("user_settings").select(
            "stripe_subscription_id, stripe_subscription_status, stripe_current_period_end, stripe_cancel_at_period_end"
        ).eq("user_id", auth.id).execute()

        if not response.data or len(response.data) == 0:
            return SubscriptionStatusResponse(is_subscribed=False)

        settings = response.data[0]
        subscription_id = settings.get("stripe_subscription_id")
        status = settings.get("stripe_subscription_status")

        # Consider user subscribed if they have an active or trialing subscription
        is_subscribed = status in ["active", "trialing"]

        return SubscriptionStatusResponse(
            is_subscribed=is_subscribed,
            subscription_id=subscription_id,
            status=status,
            current_period_end=settings.get("stripe_current_period_end"),
            cancel_at_period_end=settings.get("stripe_cancel_at_period_end", False)
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
    supabase = Depends(get_supabase),
):
    """
    Cancel the user's subscription at the end of the current billing period.
    """
    if not stripe.api_key:
        raise HTTPException(
            status_code=500,
            detail="Stripe is not configured"
        )

    try:
        # Get subscription ID from database
        response = supabase.table("user_settings").select(
            "stripe_subscription_id"
        ).eq("user_id", auth.id).execute()

        if not response.data or not response.data[0].get("stripe_subscription_id"):
            raise HTTPException(
                status_code=404,
                detail="No active subscription found"
            )

        subscription_id = response.data[0]["stripe_subscription_id"]

        # Cancel subscription at period end (don't cancel immediately)
        subscription = stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=True
        )

        # Update database
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
    supabase = Depends(get_supabase),
):
    """
    Handle Stripe webhook events.
    This endpoint is called by Stripe when subscription events occur.

    Important: Add this URL to your Stripe webhook settings:
    https://yourdomain.com/api/v1/stripe/webhook

    Events handled:
    - checkout.session.completed: When user completes payment
    - customer.subscription.updated: When subscription changes
    - customer.subscription.deleted: When subscription is cancelled
    """
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook called but STRIPE_WEBHOOK_SECRET not configured")
        # In development, you might skip verification, but NEVER in production
        payload = await request.body()
        event = stripe.Event.construct_from(
            await request.json(), stripe.api_key
        )
    else:
        # Verify webhook signature
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

    # Handle the event
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
    """Handle successful checkout - activate subscription"""
    user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
    subscription_id = session.get("subscription")

    if not user_id:
        logger.error(f"Checkout session {session.id} has no user_id")
        return

    logger.info(f"Checkout completed for user {user_id}, subscription {subscription_id}")

    # Get full subscription details
    subscription = stripe.Subscription.retrieve(subscription_id)

    # Ensure user_settings record exists
    from core.user_limits import ensure_user_settings_exist
    ensure_user_settings_exist(supabase, user_id)

    # Update user settings with subscription info
    supabase.table("user_settings").update({
        "stripe_customer_id": session.customer,
        "stripe_subscription_id": subscription_id,
        "stripe_subscription_status": subscription.status,
        "stripe_current_period_end": subscription.current_period_end,
        "stripe_cancel_at_period_end": subscription.cancel_at_period_end,
        "max_files": PREMIUM_MAX_FILES,  # Upgrade to premium tier
    }).eq("user_id", user_id).execute()

    logger.info(f"Activated premium subscription for user {user_id}")


async def handle_subscription_updated(subscription, supabase):
    """Handle subscription updates (renewals, cancellations, etc.)"""
    user_id = subscription.get("metadata", {}).get("user_id")

    if not user_id:
        logger.error(f"Subscription {subscription.id} has no user_id in metadata")
        return

    logger.info(f"Subscription updated for user {user_id}: status={subscription.status}")

    # Update subscription status
    update_data = {
        "stripe_subscription_status": subscription.get("status"),
        "stripe_current_period_end": subscription.get("current_period_end"),
        "stripe_cancel_at_period_end": subscription.get("cancel_at_period_end", False),
    }

    # If subscription is active, ensure premium tier
    if subscription.get("status") in ["active", "trialing"]:
        update_data["max_files"] = PREMIUM_MAX_FILES
    # If subscription ended or cancelled, revert to free tier
    elif subscription.get("status") in ["canceled", "unpaid", "past_due"]:
        update_data["max_files"] = 50  # Revert to free tier

    supabase.table("user_settings").update(update_data).eq("user_id", user_id).execute()


async def handle_subscription_deleted(subscription, supabase):
    """Handle subscription deletion - downgrade to free tier"""
    user_id = subscription.get("metadata", {}).get("user_id")

    if not user_id:
        logger.error(f"Subscription {subscription.id} has no user_id in metadata")
        return

    logger.info(f"Subscription deleted for user {user_id}")

    # Revert to free tier
    supabase.table("user_settings").update({
        "stripe_subscription_status": "canceled",
        "stripe_cancel_at_period_end": False,
        "max_files": 50,  # Free tier limit
    }).eq("user_id", user_id).execute()

    logger.info(f"Downgraded user {user_id} to free tier")
