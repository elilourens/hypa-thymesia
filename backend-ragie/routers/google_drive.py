"""Google Drive sync endpoints."""

import logging
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from supabase import Client
from googleapiclient.discovery import build
import io

from core import get_current_user, AuthUser
from core.deps import get_supabase, get_supabase_admin, get_google_drive_service, get_ragie_service
from core.rate_limiting import rate_limit
from core.encryption import token_encryptor
from core.user_limits import check_user_can_upload, add_to_user_monthly_throughput, add_to_user_monthly_file_count
from services.google_drive_service import GoogleDriveService
from services.ragie_service import RagieService
from services.video_service import VideoService
from services.thumbnail_service import ThumbnailService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/google-drive", tags=["google-drive"])

# Supported file types
SUPPORTED_VIDEO_TYPES = {'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/mpeg'}
SUPPORTED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp'}
SUPPORTED_DOC_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
    'text/csv'
}


class ConnectFolderRequest(BaseModel):
    folder_id: str
    folder_name: str
    group_id: Optional[str] = None
    access_token: str
    refresh_token: str
    token_expires_in: int  # seconds until expiration


class ConnectFolderResponse(BaseModel):
    status: str
    sync_config_id: str
    message: str


class SyncConfigResponse(BaseModel):
    id: str
    folder_id: str
    folder_name: str
    sync_enabled: bool
    last_sync_at: Optional[str]
    last_sync_status: str
    files_count: int = 0


class FailedFile(BaseModel):
    name: str
    error: str


class SyncResponse(BaseModel):
    status: str
    files_processed: int
    files_failed: Optional[int] = 0
    total_files: Optional[int] = 0
    failed_files: Optional[List[FailedFile]] = []


@router.post("/connect-folder", response_model=ConnectFolderResponse)
@rate_limit(calls_per_minute=10)
async def connect_google_drive_folder(
    request: ConnectFolderRequest,
    current_user: AuthUser = Depends(get_current_user),
    google_drive_service: GoogleDriveService = Depends(get_google_drive_service),
    supabase: Client = Depends(get_supabase_admin),
):
    """
    Connect a Google Drive folder for syncing.

    This endpoint:
    1. Encrypts and stores OAuth tokens
    2. Gets initial page token from Google Drive Changes API
    3. Stores sync config in database
    """
    try:
        # Encrypt tokens
        access_token_encrypted = token_encryptor.encrypt(request.access_token)
        refresh_token_encrypted = token_encryptor.encrypt(request.refresh_token)
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=request.token_expires_in)

        # Build Google Drive service to get initial page token
        from google.oauth2.credentials import Credentials
        from core.config import settings

        credentials = Credentials(
            token=request.access_token,
            refresh_token=request.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/drive.metadata.readonly"
            ]
        )

        service = build('drive', 'v3', credentials=credentials)

        # Don't get initial page token yet - we'll do that on first sync
        # This allows us to list ALL existing files on first sync
        # Then subsequent syncs will use Changes API for incremental updates

        # Check if user already has a sync config
        existing = supabase.table("google_drive_sync_config").select(
            "*"
        ).eq("user_id", current_user.id).execute()

        if existing.data and len(existing.data) > 0:
            # User can only have one sync config - update it
            sync_config = existing.data[0]

            supabase.table("google_drive_sync_config").update({
                "folder_id": request.folder_id,
                "folder_name": request.folder_name,
                "group_id": request.group_id,
                "access_token_encrypted": access_token_encrypted,
                "refresh_token_encrypted": refresh_token_encrypted,
                "token_expires_at": token_expires_at.isoformat(),
                "page_token": "",  # Empty until first sync
                "sync_enabled": True,
                "last_sync_status": "pending"
            }).eq("id", sync_config["id"]).execute()

            return ConnectFolderResponse(
                status="updated",
                sync_config_id=sync_config["id"],
                message=f"Updated sync folder to {request.folder_name}"
            )
        else:
            # Create new sync config
            result = supabase.table("google_drive_sync_config").insert({
                "user_id": current_user.id,
                "group_id": request.group_id,
                "folder_id": request.folder_id,
                "folder_name": request.folder_name,
                "access_token_encrypted": access_token_encrypted,
                "refresh_token_encrypted": refresh_token_encrypted,
                "token_expires_at": token_expires_at.isoformat(),
                "page_token": "",  # Empty until first sync
                "sync_enabled": True,
                "last_sync_status": "pending"
            }).execute()

            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create sync config")

            return ConnectFolderResponse(
                status="created",
                sync_config_id=result.data[0]["id"],
                message=f"Connected folder {request.folder_name}"
            )

    except Exception as e:
        logger.error(f"Error connecting folder: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync-config", response_model=Optional[SyncConfigResponse])
async def get_sync_config(
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_admin),
):
    """Get user's Google Drive sync configuration."""
    try:
        response = supabase.table("google_drive_sync_config").select(
            "id, folder_id, folder_name, sync_enabled, last_sync_at, last_sync_status"
        ).eq("user_id", current_user.id).execute()

        if not response.data or len(response.data) == 0:
            return None

        config = response.data[0]

        # Count synced files for this config
        files_response = supabase.table("google_drive_files").select(
            "id", count="exact"
        ).eq("sync_config_id", config["id"]).execute()

        files_count = files_response.count or 0

        return SyncConfigResponse(
            **config,
            files_count=files_count
        )

    except Exception as e:
        logger.error(f"Error getting sync config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/disconnect")
async def disconnect_google_drive(
    current_user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_admin),
):
    """Disconnect Google Drive sync and delete sync config."""
    try:
        # Delete sync config (cascade will delete google_drive_files)
        supabase.table("google_drive_sync_config").delete().eq(
            "user_id", current_user.id
        ).execute()

        return {"status": "disconnected"}

    except Exception as e:
        logger.error(f"Error disconnecting: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync", response_model=SyncResponse)
@rate_limit(calls_per_minute=10)
async def sync_folder_manual(
    current_user: AuthUser = Depends(get_current_user),
    google_drive_service: GoogleDriveService = Depends(get_google_drive_service),
    ragie_service: RagieService = Depends(get_ragie_service),
    supabase: Client = Depends(get_supabase_admin),
):
    """
    Manually trigger sync of user's Google Drive folder.

    Called when user clicks "Sync Now" button.
    """
    try:
        # Load sync config for current user
        config_response = supabase.table("google_drive_sync_config").select(
            "*"
        ).eq("user_id", current_user.id).execute()

        if not config_response.data or len(config_response.data) == 0:
            raise HTTPException(status_code=404, detail="No Google Drive folder connected")

        config = config_response.data[0]

        if not config["sync_enabled"]:
            raise HTTPException(status_code=400, detail="Sync is disabled")

        # Update status to syncing
        supabase.table("google_drive_sync_config").update({
            "last_sync_status": "syncing"
        }).eq("id", config["id"]).execute()

        # Build Google Drive service
        credentials = google_drive_service.build_credentials(config)
        service = build('drive', 'v3', credentials=credentials)

        # Always list all files in folder and compare against google_drive_files
        # This is the simplest approach: full reconciliation each sync
        # Handles: new files, deleted files, and deleted+re-added files
        logger.info(f"Listing all files in folder {config['folder_id']}")
        all_folder_files = google_drive_service.list_all_files_in_folder(service, config["folder_id"])
        logger.info(f"Found {len(all_folder_files)} total files in folder")

        # Get list of file IDs we've already synced
        synced_records = supabase.table("google_drive_files").select(
            "gdrive_file_id"
        ).eq("sync_config_id", config["id"]).execute()

        synced_file_ids = set(r["gdrive_file_id"] for r in (synced_records.data or []))
        logger.info(f"Already have {len(synced_file_ids)} files in google_drive_files")

        # Determine which files need to be synced
        files_to_sync = []
        for file_change in all_folder_files:
            file_id = file_change.get('fileId')
            if file_id not in synced_file_ids:
                logger.info(f"File {file_change['file']['name']} not synced yet - will ingest")
                files_to_sync.append(file_change)

        # Also clean up: delete ragie_documents for files no longer in folder
        # CASCADE constraint will automatically delete google_drive_files
        current_folder_file_ids = set(f.get('fileId') for f in all_folder_files)
        for synced_id in synced_file_ids:
            if synced_id not in current_folder_file_ids:
                logger.info(f"File {synced_id} no longer in folder - cleaning up")

                # Get ragie_document_id before deleting
                gd_file = supabase.table("google_drive_files").select("ragie_document_id").eq(
                    "sync_config_id", config["id"]
                ).eq("gdrive_file_id", synced_id).execute()

                if gd_file.data and len(gd_file.data) > 0 and gd_file.data[0].get("ragie_document_id"):
                    # Delete ragie_documents (CASCADE will delete google_drive_files)
                    ragie_doc_id = gd_file.data[0]["ragie_document_id"]
                    supabase.table("ragie_documents").delete().eq(
                        "id", ragie_doc_id
                    ).execute()
                    logger.info(f"Deleted ragie_document {ragie_doc_id} for removed file {synced_id}")
                else:
                    # Orphaned google_drive_files with no ragie_document - delete directly
                    supabase.table("google_drive_files").delete().eq(
                        "sync_config_id", config["id"]
                    ).eq("gdrive_file_id", synced_id).execute()
                    logger.info(f"Deleted orphaned google_drive_files record for {synced_id}")

        changes = files_to_sync
        total_files = len(changes)
        logger.info(f"Will sync {total_files} files")

        files_processed = 0
        files_failed = 0
        failed_files_list = []

        # Process each change
        for change in changes:
            file = change.get('file')
            if not file:
                continue

            file_id = file['id']

            # Handle deleted files
            if file.get('trashed'):
                # Delete the google_drive_files record so if file is restored it will be re-synced
                supabase.table("google_drive_files").delete().eq(
                    "sync_config_id", config["id"]
                ).eq("gdrive_file_id", file_id).execute()
                logger.info(f"Removed trashed file from sync: {file['name']}")
                continue

            # Check if file already synced
            existing_file = supabase.table("google_drive_files").select(
                "*"
            ).eq("sync_config_id", config["id"]).eq("gdrive_file_id", file_id).execute()

            should_sync = False

            if not existing_file.data or len(existing_file.data) == 0:
                # New file - download and ingest
                logger.info(f"New file detected: {file['name']}")
                should_sync = True
            else:
                # File exists in google_drive_files - check if ragie_documents still exists
                existing_gdrive_file = existing_file.data[0]
                ragie_doc_id = existing_gdrive_file.get("ragie_document_id")

                if ragie_doc_id:
                    # Check if ragie_documents record still exists
                    ragie_doc_check = supabase.table("ragie_documents").select(
                        "id"
                    ).eq("ragie_document_id", ragie_doc_id).execute()

                    if not ragie_doc_check.data or len(ragie_doc_check.data) == 0:
                        # Document was deleted from dashboard - re-sync it
                        logger.info(f"File {file['name']} was deleted from dashboard, re-syncing...")
                        # Delete old google_drive_files record
                        supabase.table("google_drive_files").delete().eq(
                            "id", existing_gdrive_file["id"]
                        ).execute()
                        should_sync = True
                    else:
                        # File already synced and document still exists - skip
                        logger.debug(f"File {file['name']} already synced, skipping")
                else:
                    # No ragie_document_id - old or corrupt record, re-sync
                    logger.info(f"File {file['name']} has no ragie_document_id, re-syncing...")
                    supabase.table("google_drive_files").delete().eq(
                        "id", existing_gdrive_file["id"]
                    ).execute()
                    should_sync = True

            if should_sync:

                try:
                    file_size = int(file.get('size') or 0)

                    # Validate file size metadata
                    if file_size == 0:
                        logger.warning(f"File {file['name']} has no size metadata, skipping")
                        continue

                    # Check user quota before downloading
                    try:
                        check_user_can_upload(supabase, current_user.id, file_size_bytes=file_size)
                    except HTTPException as quota_error:
                        logger.warning(f"Upload quota exceeded for {file['name']}: {quota_error.detail}")
                        # Skip this file - will retry on next sync when quota is available
                        continue

                    # Download file with size validation
                    file_buffer = google_drive_service.download_file(
                        service, file_id, file['name']
                    )
                    file_buffer.seek(0)

                    # Validate downloaded size matches metadata (allow 10% variance)
                    downloaded_size = file_buffer.getbuffer().nbytes
                    if downloaded_size > file_size * 1.1:
                        logger.error(f"Downloaded size ({downloaded_size}) exceeds expected size ({file_size}) for {file['name']}")
                        continue

                    mime_type = file.get('mimeType', '')

                    # Validate file type is supported
                    if not mime_type:
                        logger.warning(f"File {file['name']} has no MIME type, skipping")
                        continue

                    is_supported = (
                        mime_type in SUPPORTED_VIDEO_TYPES or
                        mime_type in SUPPORTED_IMAGE_TYPES or
                        mime_type in SUPPORTED_DOC_TYPES
                    )

                    if not is_supported:
                        logger.warning(f"Unsupported file type {mime_type} for {file['name']}, skipping")
                        continue

                    # Handle videos: upload to Supabase storage
                    if mime_type.startswith('video/') or file['name'].lower().endswith('.mp4'):
                        try:
                            video_service = VideoService(supabase, ragie_service)

                            # Create UploadFile-like object for video service
                            upload_file = UploadFile(
                                filename=file['name'],
                                file=file_buffer
                            )

                            # Upload video to storage
                            video_result = await video_service.upload_video(
                                file=upload_file,
                                user_id=current_user.id,
                                group_id=config.get("group_id")
                            )

                            # Create ragie_documents record with storage info
                            doc_record = supabase.table("ragie_documents").insert({
                                "user_id": current_user.id,
                                "group_id": config.get("group_id"),
                                "filename": file['name'],
                                "mime_type": mime_type or "video/mp4",
                                "file_size_bytes": file_size,
                                "status": "pending",
                                "source": "google_drive",
                                "external_id": file_id,
                                "storage_bucket": "videos",
                                "storage_path": video_result["storage_path"],
                                "ragie_metadata": {
                                    "user_id": current_user.id,
                                    "group_id": config.get("group_id"),
                                    "mime_type": mime_type or "video/mp4",
                                    "source": "google_drive"
                                }
                            }).execute()

                            if not doc_record.data:
                                raise Exception("Failed to create document record")

                            doc = doc_record.data[0]

                            # If video service extracted a thumbnail, update the record
                            if video_result.get("_thumbnail_path"):
                                supabase.table("ragie_documents").update({
                                    "thumbnail_storage_path": video_result["_thumbnail_path"],
                                    "has_thumbnail": True
                                }).eq("id", doc["id"]).execute()
                                logger.info(f"Thumbnail extracted for video {file['name']}")

                            # Process video with Ragie (async, will update via webhook)
                            await video_service.process_video_with_ragie(
                                video_id=doc["id"],
                                user_id=current_user.id,
                                temp_file_path=video_result.get("_temp_file_path"),
                                thumbnail_path=video_result.get("_thumbnail_path")
                            )

                            # Save to google_drive_files (with rollback on failure)
                            try:
                                gd_result = supabase.table("google_drive_files").insert({
                                    "sync_config_id": config["id"],
                                    "user_id": current_user.id,
                                    "gdrive_file_id": file_id,
                                    "gdrive_parent_folder_id": config["folder_id"],
                                    "ragie_document_id": doc["id"],
                                    "filename": file['name'],
                                    "mime_type": mime_type or "video/mp4",
                                    "file_size_bytes": file_size,
                                    "gdrive_modified_time": file.get('modifiedTime'),
                                    "md5_hash": file.get('md5Checksum'),
                                    "sync_status": "ready",
                                    "last_synced_at": datetime.now(timezone.utc).isoformat()
                                }).execute()

                                if not gd_result.data:
                                    # Rollback: delete ragie_documents
                                    logger.warning(f"google_drive_files insert failed, rolling back ragie_documents for video {file['name']}")
                                    supabase.table("ragie_documents").delete().eq("id", doc["id"]).execute()
                                    raise Exception("Failed to create google_drive_files record")

                                files_processed += 1
                                # Track monthly usage
                                add_to_user_monthly_throughput(supabase, current_user.id, file_size)
                                add_to_user_monthly_file_count(supabase, current_user.id)
                                logger.info(f"Successfully ingested video: {file['name']}")

                            except Exception as gd_error:
                                # Rollback: delete ragie_documents if it was created
                                logger.error(f"google_drive_files insert failed for video {file['name']}: {type(gd_error).__name__}")
                                supabase.table("ragie_documents").delete().eq("id", doc["id"]).execute()
                                raise gd_error

                        except Exception as video_error:
                            logger.error(f"Error processing video {file['name']}: {video_error}")
                            # Don't save to google_drive_files - let it retry on next sync

                    else:
                        # Handle regular files (documents, images)
                        try:
                            # Create UploadFile-like object
                            upload_file = UploadFile(
                                filename=file['name'],
                                file=file_buffer
                            )

                            ragie_response = await ragie_service.upload_document(
                                file=upload_file,
                                user_id=current_user.id,
                                group_id=config.get("group_id"),
                                metadata={
                                    "mime_type": mime_type,
                                    "source": "google_drive",
                                    "gdrive_file_id": file_id,
                                    "gdrive_folder_id": config["folder_id"]
                                }
                            )

                            # Save to ragie_documents
                            doc_record = supabase.table("ragie_documents").insert({
                                "user_id": current_user.id,
                                "group_id": config.get("group_id"),
                                "ragie_document_id": str(ragie_response.id),
                                "filename": file['name'],
                                "mime_type": mime_type,
                                "file_size_bytes": file_size,
                                "status": ragie_response.status,
                                "source": "google_drive",
                                "external_id": file_id,
                                "ragie_metadata": {
                                    "user_id": current_user.id,
                                    "group_id": config.get("group_id"),
                                    "mime_type": mime_type,
                                    "source": "google_drive"
                                }
                            }).execute()

                            if not doc_record.data:
                                raise Exception("Failed to create document record")

                            doc = doc_record.data[0]

                            # Generate thumbnail for images
                            if mime_type and mime_type.startswith('image/'):
                                try:
                                    file_buffer.seek(0)
                                    image_bytes = file_buffer.read()

                                    thumbnail_service = ThumbnailService(supabase)
                                    thumbnail_bytes = thumbnail_service._generate_thumbnail(image_bytes)

                                    if thumbnail_bytes:
                                        thumbnail_path = thumbnail_service.upload_thumbnail(
                                            doc["id"],
                                            thumbnail_bytes
                                        )

                                        if thumbnail_path:
                                            supabase.table("ragie_documents").update({
                                                "thumbnail_storage_path": thumbnail_path,
                                                "thumbnail_size_bytes": len(thumbnail_bytes),
                                                "has_thumbnail": True
                                            }).eq("id", doc["id"]).execute()

                                            logger.info(f"Thumbnail generated for {file['name']}")
                                except Exception as thumb_error:
                                    logger.warning(f"Failed to generate thumbnail for {file['name']}: {thumb_error}")

                            # Save to google_drive_files (with rollback on failure)
                            try:
                                gd_result = supabase.table("google_drive_files").insert({
                                    "sync_config_id": config["id"],
                                    "user_id": current_user.id,
                                    "gdrive_file_id": file_id,
                                    "gdrive_parent_folder_id": config["folder_id"],
                                    "ragie_document_id": doc["id"],
                                    "filename": file['name'],
                                    "mime_type": mime_type,
                                    "file_size_bytes": file_size,
                                    "gdrive_modified_time": file.get('modifiedTime'),
                                    "md5_hash": file.get('md5Checksum'),
                                    "sync_status": "ready",
                                    "last_synced_at": datetime.now(timezone.utc).isoformat()
                                }).execute()

                                if not gd_result.data:
                                    # Rollback: delete ragie_documents
                                    logger.warning(f"google_drive_files insert failed, rolling back ragie_documents for {file['name']}")
                                    supabase.table("ragie_documents").delete().eq("id", doc["id"]).execute()
                                    raise Exception("Failed to create google_drive_files record")

                                files_processed += 1
                                # Track monthly usage
                                add_to_user_monthly_throughput(supabase, current_user.id, file_size)
                                add_to_user_monthly_file_count(supabase, current_user.id)
                                logger.info(f"Successfully ingested file: {file['name']}")

                            except Exception as gd_error:
                                # Rollback: delete ragie_documents if it was created
                                logger.error(f"google_drive_files insert failed for {file['name']}: {type(gd_error).__name__}")
                                supabase.table("ragie_documents").delete().eq("id", doc["id"]).execute()
                                raise gd_error

                        except Exception as doc_error:
                            logger.error(f"Error processing file {file['name']}: {type(doc_error).__name__}")
                            files_failed += 1
                            failed_files_list.append({
                                "name": file.get('name', 'unknown'),
                                "error": str(doc_error)[:200]  # Truncate error message
                            })
                            # Don't save to google_drive_files - let it retry on next sync

                except Exception as file_error:
                    logger.error(f"Error processing file {file['name']}: {file_error}")
                    files_failed += 1
                    failed_files_list.append({
                        "name": file.get('name', 'unknown'),
                        "error": str(file_error)[:200]  # Truncate error message
                    })
                    # Don't save to google_drive_files - let it retry on next sync

        # Update sync config
        supabase.table("google_drive_sync_config").update({
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
            "last_sync_status": "success",
            "last_error": None
        }).eq("id", config["id"]).execute()

        return SyncResponse(
            status="success",
            files_processed=files_processed,
            files_failed=files_failed,
            total_files=total_files,
            failed_files=[FailedFile(**f) for f in failed_files_list]
        )

    except Exception as e:
        # Don't log raw exception which may contain tokens
        logger.error(f"Sync failed for user {current_user.id}: {type(e).__name__}")

        # Update error status
        if 'config' in locals():
            supabase.table("google_drive_sync_config").update({
                "last_sync_status": "error",
                "last_error": str(e)[:500]  # Truncate error message
            }).eq("user_id", current_user.id).execute()

        raise HTTPException(status_code=500, detail="Sync failed")
