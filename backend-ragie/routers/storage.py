"""Storage endpoints for generating signed URLs and accessing file metadata."""

import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from supabase import Client

from core import get_current_user, AuthUser
from core.deps import get_supabase, get_ragie_service
from core.config import settings
from services.ragie_service import RagieService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/signed-url")
async def get_signed_url(
    request: Request,
    bucket: str = Query(...),
    path: str = Query(...),
    download: bool = Query(False),
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    ragie_service: RagieService = Depends(get_ragie_service),
):
    """
    Generate a signed URL for accessing a file.

    For files stored in Ragie, retrieves the document and gets access.

    Args:
        request: FastAPI request object (for building full URLs)
        bucket: The storage bucket name or "ragie" for Ragie-stored files
        path: The file path or document ID
        download: If true, forces download; if false, displays inline
        current_user: Current authenticated user
        supabase: Supabase client
        ragie_service: Ragie service

    Returns:
        JSON with signed_url field
    """
    try:
        # If bucket is "ragie", get from Ragie
        if bucket == "ragie":
            # path is the document ID in this case
            doc_id = path
            try:
                # Get document from Ragie to verify it exists
                doc = await ragie_service.get_document_status(doc_id)

                # Return a full URL to our proxy endpoint that will fetch from Ragie
                base_url = str(request.base_url).rstrip('/')
                proxy_url = f"{base_url}/api/v1/storage/file/ragie/{doc_id}"

                logger.info(f"Generated proxy URL for Ragie document {doc_id}: {proxy_url}")
                return {
                    "signed_url": proxy_url,
                    "provider": "ragie"
                }
            except Exception as e:
                logger.error(f"Error getting Ragie document {doc_id}: {e}")
                raise HTTPException(status_code=404, detail="Document not found in Ragie")

        # Otherwise, try Supabase Storage
        try:
            response = supabase.storage.from_(bucket).create_signed_url(
                path=path,
                expires_in=3600
            )

            if not response:
                raise HTTPException(status_code=404, detail="Failed to generate signed URL")

            signed_url = response.get("signedURL") or response.get("signed_url")
            if not signed_url:
                raise HTTPException(status_code=500, detail="No signed URL in response")

            # Append download parameter if needed
            if download:
                signed_url += "&download="

            return {
                "signed_url": signed_url,
                "provider": "supabase"
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating signed URL for {bucket}/{path}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_signed_url: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/file/ragie/{doc_id}")
async def get_ragie_file(
    doc_id: str,
    ragie_service: RagieService = Depends(get_ragie_service),
):
    """
    Stream a document's source file from Ragie.

    Uses Ragie's document source API to retrieve the original uploaded file.

    Note: This endpoint doesn't require authentication because the user must be
    authenticated to obtain the signed URL from /signed-url first.

    Args:
        doc_id: Ragie document ID
        ragie_service: Ragie service

    Returns:
        Streamed file content from Ragie
    """
    try:
        # Verify document exists in Ragie
        logger.info(f"Fetching document status for {doc_id}")
        doc = await ragie_service.get_document_status(doc_id)
        logger.info(f"Document {doc_id} status check passed, fetching source")

        # Call Ragie's document source API
        ragie_api_url = f"https://api.ragie.ai/documents/{doc_id}/source"
        headers = {"Authorization": f"Bearer {settings.ragie_api_key}"}
        logger.info(f"Calling Ragie source API: {ragie_api_url}")

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(ragie_api_url, headers=headers)
                logger.info(f"Ragie API response status: {response.status_code}")
                response.raise_for_status()

                # Stream the file back to the client
                return StreamingResponse(
                    iter([response.content]),
                    media_type=response.headers.get("content-type", "application/octet-stream"),
                    headers={
                        "Content-Disposition": response.headers.get(
                            "content-disposition",
                            f"inline; filename=document_{doc_id}"
                        )
                    }
                )
        except httpx.HTTPStatusError as e:
            logger.error(f"Ragie API HTTP error for {doc_id}: status={e.response.status_code}, detail={e.response.text}")
            raise HTTPException(status_code=500, detail=f"Ragie API error: {e.response.status_code}")
        except httpx.HTTPError as e:
            logger.error(f"Ragie API request error for {doc_id}: {type(e).__name__}: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to retrieve file from Ragie")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_ragie_file for {doc_id}: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="File processing failed")


@router.get("/video-info/{doc_id}")
async def get_video_info(
    doc_id: str,
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Get video file information by document ID.

    Args:
        doc_id: Document ID
        current_user: Current authenticated user
        supabase: Supabase client

    Returns:
        JSON with doc_id, filename, bucket, and storage_path
    """
    try:
        # Fetch document from database
        response = supabase.table("ragie_documents").select(
            "id, filename, storage_bucket, storage_path, mime_type, ragie_document_id"
        ).eq("id", doc_id).eq("user_id", current_user.id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        doc = response.data

        # Use Ragie as the bucket for Ragie-stored documents
        bucket = doc.get("storage_bucket") or "ragie"
        storage_path = doc.get("storage_path") or doc.get("ragie_document_id", "")

        return {
            "doc_id": doc["id"],
            "filename": doc.get("filename", "video"),
            "bucket": bucket,
            "storage_path": storage_path,
            "mime_type": doc.get("mime_type")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting video info for {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
