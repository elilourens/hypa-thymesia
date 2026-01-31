"""FastAPI application entry point."""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from routers import (
    health_router,
    documents_router,
    search_router,
    groups_router,
    stripe_router,
    user_settings_router,
    audit_router,
    storage_router,
    videos_router,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Ragie Backend API",
    description="Lean document management backend using Ragie.ai",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(search_router, prefix=settings.api_prefix)
app.include_router(groups_router, prefix=settings.api_prefix)
app.include_router(stripe_router, prefix=settings.api_prefix)
app.include_router(user_settings_router, prefix=settings.api_prefix)
app.include_router(audit_router, prefix=settings.api_prefix)
app.include_router(storage_router, prefix=settings.api_prefix)
app.include_router(videos_router, prefix=settings.api_prefix)


@app.on_event("startup")
async def startup_event():
    """Called on application startup."""
    logger.info(" Ragie Backend API starting...")
    logger.info(f"API Prefix: {settings.api_prefix}")
    logger.info(f"Debug Mode: {settings.debug}")

    # Security: Validate Stripe webhook secret is configured
    if not settings.stripe_webhook_secret:
        logger.error(
            "CRITICAL: STRIPE_WEBHOOK_SECRET is not configured. "
            "Webhook signature validation will fail. "
            "Set STRIPE_WEBHOOK_SECRET environment variable."
        )
        raise RuntimeError(
            "STRIPE_WEBHOOK_SECRET is not configured. "
            "Webhook endpoint requires valid signature verification."
        )


@app.on_event("shutdown")
async def shutdown_event():
    """Called on application shutdown."""
    logger.info(" Ragie Backend API shutting down...")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
