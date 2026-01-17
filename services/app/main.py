"""
Formatting & Tagging Microservice - FastAPI Application
Handles text chunk formatting using Ollama LLM and image/document tagging.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import formatting, tagging
from app.core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Formatting & Tagging Microservice")
    settings = get_settings()
    logger.info(f"Ollama URL: {settings.OLLAMA_URL}")
    logger.info(f"Ollama Model: {settings.OLLAMA_MODEL}")

    # Warm up image tagging models (CLIP + OWL-ViT)
    # This is done in the background to not block startup
    if os.getenv("WARMUP_MODELS", "true").lower() == "true":
        try:
            from app.services.image_tagger import warmup_models
            warmup_models()
        except Exception as e:
            logger.warning(f"Failed to warm up image tagging models: {e}")

    yield
    logger.info("Shutting down Formatting & Tagging Microservice")


app = FastAPI(
    title="Formatting & Tagging Microservice",
    description="Text chunk formatting and document/image tagging service",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(formatting.router, prefix="/api/v1")
app.include_router(tagging.router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "formatting-tagging-microservice"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "formatting-tagging-microservice",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "formatting": "/api/v1/formatting",
            "tagging": "/api/v1/tagging"
        }
    }
