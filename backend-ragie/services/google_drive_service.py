"""Google Drive API integration and sync logic."""

import logging
import io
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseDownload
from supabase import Client

from core.config import settings
from core.encryption import token_encryptor

logger = logging.getLogger(__name__)


class GoogleDriveService:
    """Service for Google Drive API operations and file syncing."""

    def __init__(self, supabase: Client):
        self.supabase = supabase

    def build_credentials(self, sync_config: dict) -> Credentials:
        """Build Google credentials from encrypted tokens in sync config."""
        access_token = token_encryptor.decrypt(sync_config["access_token_encrypted"])
        refresh_token = token_encryptor.decrypt(sync_config["refresh_token_encrypted"])

        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/drive.metadata.readonly"
            ]
        )

        # Parse token_expires_at from database (it's a string in ISO format)
        token_expires_at = datetime.fromisoformat(sync_config["token_expires_at"].replace('Z', '+00:00'))

        # Refresh if expired (use timezone-aware datetime for comparison)
        if datetime.now(timezone.utc) >= token_expires_at:
            logger.info("Refreshing expired Google token")
            try:
                credentials.refresh(Request())

                # Read actual expiry from credentials (don't hardcode 1 hour)
                # If expiry is not available, default to 1 hour
                if credentials.expiry:
                    new_expiry = credentials.expiry
                else:
                    new_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

                # Update database with new access token
                self.supabase.table("google_drive_sync_config").update({
                    "access_token_encrypted": token_encryptor.encrypt(credentials.token),
                    "token_expires_at": new_expiry.isoformat()
                }).eq("id", sync_config["id"]).execute()

            except Exception as e:
                logger.error(f"Token refresh failed: {type(e).__name__}")
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=401,
                    detail="Google token refresh failed. Please reconnect your Google Drive."
                )

        return credentials

    def get_changes_since_token(
        self,
        service,
        page_token: str,
        folder_id: str
    ) -> Tuple[List[dict], str]:
        """
        Get all changes since the given page token, filtered by folder.

        Returns:
            Tuple of (list of changes, new_page_token)
        """
        changes = []
        next_page_token = page_token

        while next_page_token:
            response = service.changes().list(
                pageToken=next_page_token,
                spaces='drive',
                fields='nextPageToken,newStartPageToken,changes(fileId,file(id,name,mimeType,parents,trashed,modifiedTime,size,md5Checksum))',
                includeRemoved=True,
                restrictToMyDrive=True,
                pageSize=100
            ).execute()

            for change in response.get('changes', []):
                file = change.get('file')
                if file:
                    # Only include files in the watched folder
                    if folder_id in file.get('parents', []):
                        changes.append(change)

            next_page_token = response.get('nextPageToken')

            if not next_page_token:
                new_start_token = response.get('newStartPageToken')
                return changes, new_start_token

        return changes, page_token

    def list_all_files_in_folder(self, service, folder_id: str, max_files: int = 1000) -> List[dict]:
        """
        List all files currently in a folder using the Files API.

        Returns a list of change-like objects for compatibility with sync logic.

        Args:
            service: Google Drive service instance
            folder_id: ID of the folder to list files from
            max_files: Maximum number of files to return (default: 1000)
        """
        files_list = []
        next_page_token = None
        iterations = 0
        max_iterations = 50  # Prevent infinite loops

        while iterations < max_iterations:
            iterations += 1

            response = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='nextPageToken,files(id,name,mimeType,parents,trashed,modifiedTime,size,md5Checksum)',
                pageSize=100,
                pageToken=next_page_token
            ).execute()

            for file in response.get('files', []):
                # Convert to change-like format for compatibility
                change = {
                    'fileId': file['id'],
                    'file': file
                }
                files_list.append(change)

                # Check file count limit
                if len(files_list) >= max_files:
                    logger.warning(f"Reached max_files limit ({max_files}), truncating file list")
                    return files_list[:max_files]

            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break

        if iterations >= max_iterations:
            logger.warning(f"Reached max_iterations limit ({max_iterations}), may have missed some files")

        logger.info(f"Listed {len(files_list)} files in folder {folder_id}")
        return files_list

    def download_file(self, service, file_id: str, filename: str) -> io.BytesIO:
        """Download file content from Google Drive."""
        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()
            logger.info(f"Download {filename}: {int(status.progress() * 100)}%")

        file_buffer.seek(0)
        return file_buffer

    def get_initial_page_token(self, service) -> str:
        """Get initial page token for Changes API."""
        response = service.changes().getStartPageToken().execute()
        return response['startPageToken']
