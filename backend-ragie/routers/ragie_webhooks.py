"""Ragie webhook handlers for document processing events."""

import logging
import hmac
import hashlib
import time
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from supabase import Client
import json
from collections import defaultdict

from core.config import settings
from core.deps import get_supabase_for_webhook, get_ragie_service
from core.sse import get_sse_manager, SSEManager
from services.ragie_service import RagieService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ragie-webhooks", tags=["ragie-webhooks"])

# Rate limiting: Track webhook calls per IP
# Limit: 100 requests per minute per IP
_webhook_rate_limits = defaultdict(list)
WEBHOOK_RATE_LIMIT = 100
WEBHOOK_RATE_WINDOW = 60  # seconds


def _check_webhook_rate_limit(client_ip: str) -> bool:
    """
    Check if webhook request from client_ip is within rate limit.

    Args:
        client_ip: Client IP address

    Returns:
        True if within rate limit, False if exceeded
    """
    current_time = time.time()

    # Clean up old requests (older than the rate window)
    _webhook_rate_limits[client_ip] = [
        req_time for req_time in _webhook_rate_limits[client_ip]
        if current_time - req_time < WEBHOOK_RATE_WINDOW
    ]

    # Check if we've exceeded the limit
    if len(_webhook_rate_limits[client_ip]) >= WEBHOOK_RATE_LIMIT:
        return False

    # Record this request
    _webhook_rate_limits[client_ip].append(current_time)
    return True


def _verify_ragie_signature(request_body: bytes, signature: str, secret: str) -> bool:
    """
    Verify Ragie webhook signature.

    Ragie uses HMAC SHA-256 with the signing secret.

    Args:
        request_body: Raw request body bytes
        signature: X-Signature header value (should be base64 encoded)
        secret: Ragie webhook signing secret

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature or not secret:
        return False

    try:
        # Compute HMAC SHA-256
        computed_signature = hmac.new(
            secret.encode(),
            request_body,
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(computed_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
        return False


@router.post("/webhook")
async def ragie_webhook(
    request: Request,
    x_signature: str = Header(None, alias="x-signature"),
    supabase: Client = Depends(get_supabase_for_webhook),
    ragie_service: RagieService = Depends(get_ragie_service),
    sse_manager: SSEManager = Depends(get_sse_manager),
):
    """
    Handle Ragie webhook events for document processing status updates.

    SECURITY: This endpoint requires valid Ragie webhook signature verification.
    Unsigned webhooks are always rejected to prevent forged events.

    Rate limited to 100 requests per minute per IP to prevent abuse.

    Payload structure:
    {
        "type": "document_status_updated",
        "nonce": "unique-nonce-for-idempotency",
        "payload": {
            "document_id": "...",
            "status": "ready",
            ...
        }
    }
    """
    # Check rate limit
    client_ip = request.client.host if request.client else "unknown"
    if not _check_webhook_rate_limit(client_ip):
        logger.warning(f"Webhook rate limit exceeded for IP {client_ip}")
        raise HTTPException(status_code=429, detail="Too many requests")

    # Get Ragie webhook signing secret from environment
    # Note: This should be configured in .env as RAGIE_WEBHOOK_SECRET
    ragie_webhook_secret = getattr(settings, 'ragie_webhook_secret', None)

    if not ragie_webhook_secret:
        logger.error("RAGIE_WEBHOOK_SECRET is not configured. Webhook rejected.")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not x_signature:
        logger.warning("Webhook request missing x-signature header")
        raise HTTPException(status_code=400, detail="Missing signature header")

    # Get raw request body for signature verification
    body = await request.body()

    # Verify signature
    if not _verify_ragie_signature(body, x_signature, ragie_webhook_secret):
        logger.error("Invalid Ragie webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        # Parse JSON payload
        event = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    try:
        event_type = event.get("type")
        nonce = event.get("nonce")
        payload = event.get("payload", {})

        logger.info(f"Received Ragie webhook: type={event_type}, nonce={nonce}")

        # Check if we've already processed this webhook (idempotency guard using nonce)
        if nonce:
            # We could track nonces in a table, but for now we'll just log
            # In production, store processed nonces in database to prevent duplicates
            logger.info(f"Processing webhook with nonce: {nonce}")

        # Handle document_status_updated events
        if event_type == "document_status_updated":
            document_id = payload.get("document_id")
            status = payload.get("status")

            if not document_id:
                logger.warning(f"Webhook missing document_id in payload")
                return {"status": "ignored"}

            logger.info(f"Document {document_id} status update: {status}")

            # Update document status in database
            # Find the ragie_documents record by ragie_document_id
            doc_response = supabase.table("ragie_documents").select(
                "id, user_id"
            ).eq("ragie_document_id", str(document_id)).execute()

            if doc_response.data and len(doc_response.data) > 0:
                doc = doc_response.data[0]
                doc_local_id = doc["id"]

                # Map Ragie status to our status field
                # Ragie statuses: indexed, keyword_indexed, ready, failed, etc.
                # Our statuses: pending, partitioning, partitioned, refined, chunked, indexed, summary_indexed, keyword_indexed, ready, failed

                update_data = {
                    "status": status,
                    "updated_at": __import__("datetime").datetime.utcnow().isoformat()
                }

                # Clear error if processing completed successfully
                if status in ("indexed", "keyword_indexed", "ready"):
                    update_data["processing_error"] = None
                elif status == "failed":
                    update_data["processing_error"] = payload.get("error", "Processing failed")

                # If status is "ready", retrieve chunks and store them in database
                if status == "ready":
                    try:
                        # Get the full document to access user_id and storage info
                        full_doc = supabase.table("ragie_documents").select(
                            "user_id, storage_bucket, storage_path"
                        ).eq("id", doc_local_id).single().execute()

                        if full_doc.data:
                            user_id = full_doc.data["user_id"]
                            storage_bucket = full_doc.data.get("storage_bucket")
                            storage_path = full_doc.data.get("storage_path")

                            # Retrieve chunks from Ragie for this document
                            chunks_response = await ragie_service.retrieve(
                                query="",  # Get all chunks for this document
                                user_id=user_id,
                                top_k=1000,  # Retrieve all chunks
                                rerank=False
                            )

                            # Filter chunks for this document
                            doc_chunks = [
                                chunk for chunk in chunks_response.scored_chunks
                                if chunk.document_id == document_id
                            ]

                            # Get thumbnail path if it's a video
                            thumbnail_path = None
                            if storage_bucket == "videos":
                                thumbnail_path = f"thumbnails/{doc_local_id}.jpg"

                            # Store chunks in database
                            chunk_records = []
                            for i, chunk in enumerate(doc_chunks):
                                # Extract timing info from chunk metadata for videos
                                start_time = 0
                                end_time = 0
                                if hasattr(chunk, "metadata") and chunk.metadata:
                                    start_time = chunk.metadata.get("start_time", 0)
                                    end_time = chunk.metadata.get("end_time", 0)

                                chunk_record = {
                                    "user_id": user_id,
                                    "ragie_chunk_id": chunk.chunk_id,
                                    "ragie_document_id": str(document_id),
                                    "chunk_index": i,
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "audio_transcript": chunk.text if hasattr(chunk, "text") else "",
                                    "video_description": chunk.metadata.get("video_description", "") if (hasattr(chunk, "metadata") and chunk.metadata) else "",
                                    "thumbnail_url": thumbnail_path if (i == 0 and thumbnail_path) else None
                                }
                                chunk_records.append(chunk_record)

                            if chunk_records:
                                supabase.table("video_chunks").insert(chunk_records).execute()
                                update_data["chunk_count"] = len(chunk_records)
                                logger.info(f"Stored {len(chunk_records)} chunks for document {document_id}")

                    except Exception as e:
                        logger.error(f"Error retrieving chunks for document {document_id}: {e}")
                        # Don't fail the webhook - document is ready even if chunk storage fails
                        # The document status will be updated, but chunk_count may remain zero

                supabase.table("ragie_documents").update(update_data).eq(
                    "id", doc_local_id
                ).execute()

                logger.info(f"Updated document {doc_local_id} status to {status}")

                # Broadcast status update via SSE to all connected clients
                try:
                    sse_update = {
                        "event": "status_update",
                        "video_id": doc_local_id,
                        "status": status,
                        "chunk_count": update_data.get("chunk_count"),
                        "timestamp": update_data.get("updated_at")
                    }
                    # Run SSE broadcast without awaiting (fire-and-forget)
                    asyncio.create_task(sse_manager.broadcast(doc_local_id, sse_update))
                except Exception as e:
                    logger.error(f"Error broadcasting SSE update for {doc_local_id}: {e}")
            else:
                logger.warning(f"Document {document_id} not found in database")

            return {"status": "success"}

        # Handle other event types
        elif event_type == "connection_sync_finished":
            logger.info("Connection sync finished")
            return {"status": "success"}

        else:
            logger.info(f"Unhandled Ragie webhook event type: {event_type}")
            return {"status": "success"}

    except Exception as e:
        logger.error(f"Error handling Ragie webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Webhook handler failed")
