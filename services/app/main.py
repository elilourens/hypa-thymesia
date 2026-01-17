"""
Formatting Microservice - FastAPI Application
Handles text chunk formatting using Ollama LLM.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import formatting
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
    logger.info("Starting Formatting Microservice")
    settings = get_settings()
    logger.info(f"Ollama URL: {settings.OLLAMA_URL}")
    logger.info(f"Ollama Model: {settings.OLLAMA_MODEL}")
    yield
    logger.info("Shutting down Formatting Microservice")


app = FastAPI(
    title="Formatting Microservice",
    description="Text chunk formatting service using Ollama LLM",
    version="1.0.0",
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "formatting-microservice"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "formatting-microservice",
        "version": "1.0.0",
        "docs": "/docs"
    }
