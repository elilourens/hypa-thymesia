"""Celery tasks for formatting service (image tagging, document tagging, chunk formatting)."""
import logging
import os
import httpx
from celery import shared_task
from app.celery_app import celery_app

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=120,  # 2 minutes
    soft_time_limit=110,
)
def tag_image(
    self,
    chunk_id: str,
    user_id: str,
    doc_id: str,
    image_embedding: list,
    image_bytes: bytes,
):
    """Tag an image using CLIP and OWL-ViT verification."""
    try:
        logger.info(f"Starting image tagging: chunk_id={chunk_id}, doc_id={doc_id}")
        
        # TODO: Implement OWL-ViT image tagging logic
        # For now, just log and return
        
        logger.info(f"Image tagging completed: chunk_id={chunk_id}")
        return {"status": "tagged", "chunk_id": chunk_id}
        
    except Exception as exc:
        logger.error(f"Image tagging failed: chunk_id={chunk_id}, error={exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=180,  # 3 minutes
    soft_time_limit=170,
)
def tag_document(
    self,
    doc_id: str,
    user_id: str,
    filename: str,
    text_chunks: list,
):
    """Tag a document using LLM (8-dimensional classification)."""
    try:
        logger.info(f"Starting document tagging: doc_id={doc_id}, filename={filename}")
        
        # TODO: Implement Ollama LLM-based 8D document classification
        # Categories: type, domain, topic, characteristics, intent, audience, recency, industry
        
        document_tags = {
            "type": "unknown",
            "domain": "general",
            "topic": "unknown",
            "characteristics": [],
            "intent": "unknown",
            "audience": "unknown",
            "recency": "unknown",
            "industry": "unknown",
        }
        
        logger.info(f"Document tagging completed: doc_id={doc_id}")
        return {"status": "tagged", "doc_id": doc_id, "tags": document_tags}
        
    except Exception as exc:
        logger.error(f"Document tagging failed: doc_id={doc_id}, error={exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=300,  # 5 minutes
    soft_time_limit=290,
)
def format_chunks(
    self,
    doc_id: str,
    user_id: str,
    chunk_ids: list,
    texts: list,
):
    """Format text chunks using Ollama for improved readability."""
    try:
        logger.info(f"Starting chunk formatting: doc_id={doc_id}, num_chunks={len(texts)}")
        
        formatted_chunks = []
        
        # TODO: Implement Ollama formatting for each chunk
        # Use Mistral or another model to improve readability
        
        logger.info(f"Chunk formatting completed: doc_id={doc_id}")
        return {"status": "formatted", "doc_id": doc_id, "num_chunks": len(texts)}
        
    except Exception as exc:
        logger.error(f"Chunk formatting failed: doc_id={doc_id}, error={exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)
