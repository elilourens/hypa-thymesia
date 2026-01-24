"""Supabase service for database operations."""

import logging
from typing import Optional
from uuid import UUID
from supabase import Client

logger = logging.getLogger(__name__)


class SupabaseService:
    """Service for Supabase database operations."""

    def __init__(self, client: Client):
        """Initialize with Supabase client."""
        self.client = client

    async def create_document_record(
        self,
        user_id: str,
        ragie_document_id: UUID,
        filename: str,
        mime_type: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
        group_id: Optional[str] = None,
        ragie_metadata: Optional[dict] = None,
    ) -> dict:
        """
        Create a document record in ragie_documents table.

        Args:
            user_id: User ID
            ragie_document_id: Ragie document ID
            filename: Document filename
            mime_type: MIME type
            file_size_bytes: File size in bytes
            group_id: Optional group ID
            ragie_metadata: Metadata sent to Ragie

        Returns:
            Created document record
        """
        try:
            response = self.client.table("ragie_documents").insert({
                "user_id": user_id,
                "ragie_document_id": str(ragie_document_id),
                "filename": filename,
                "mime_type": mime_type,
                "file_size_bytes": file_size_bytes,
                "group_id": group_id,
                "status": "pending",
                "ragie_metadata": ragie_metadata or {}
            }).execute()

            if response.data:
                logger.info(f"Created document record {response.data[0]['id']}")
                return response.data[0]
            else:
                raise Exception("No data returned from insert")

        except Exception as e:
            logger.error(f"Error creating document record: {e}")
            raise

    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        chunk_count: Optional[int] = None,
        page_count: Optional[int] = None,
    ) -> dict:
        """
        Update document status in database.

        Args:
            doc_id: Document ID in our database
            status: Processing status from Ragie
            chunk_count: Number of chunks
            page_count: Number of pages

        Returns:
            Updated document record
        """
        try:
            update_data = {
                "status": status,
                "updated_at": "NOW()"
            }

            if chunk_count is not None:
                update_data["chunk_count"] = chunk_count

            if page_count is not None:
                update_data["page_count"] = page_count

            response = self.client.table("ragie_documents").update(
                update_data
            ).eq("id", doc_id).execute()

            if response.data:
                logger.info(f"Updated document {doc_id} status to {status}")
                return response.data[0]
            else:
                raise Exception("No data returned from update")

        except Exception as e:
            logger.error(f"Error updating document status: {e}")
            raise

    async def get_document(self, doc_id: str, user_id: str) -> Optional[dict]:
        """
        Get document from database (with user isolation).

        Args:
            doc_id: Document ID
            user_id: User ID for verification

        Returns:
            Document record or None
        """
        try:
            response = self.client.table("ragie_documents").select(
                "*"
            ).eq("id", doc_id).eq("user_id", user_id).single().execute()

            return response.data if response.data else None

        except Exception as e:
            logger.debug(f"Error getting document: {e}")
            return None

    async def delete_document(self, doc_id: str, user_id: str) -> bool:
        """
        Delete document record from database (with user isolation).

        Args:
            doc_id: Document ID
            user_id: User ID for verification

        Returns:
            True if deleted, False otherwise
        """
        try:
            response = self.client.table("ragie_documents").delete().eq(
                "id", doc_id
            ).eq("user_id", user_id).execute()

            logger.info(f"Deleted document {doc_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            raise

    async def list_documents(
        self,
        user_id: str,
        group_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        """
        List documents for a user.

        Args:
            user_id: User ID
            group_id: Optional group filter
            limit: Result limit
            offset: Result offset

        Returns:
            List of documents
        """
        try:
            query = self.client.table("ragie_documents").select(
                "*"
            ).eq("user_id", user_id).order("created_at", desc=True).range(
                offset, offset + limit - 1
            )

            if group_id:
                query = query.eq("group_id", group_id)

            response = query.execute()

            return response.data if response.data else []

        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            return []

    async def get_document_by_ragie_id(
        self,
        ragie_document_id: str,
        user_id: str
    ) -> Optional[dict]:
        """
        Get document by Ragie ID.

        Args:
            ragie_document_id: Ragie document ID
            user_id: User ID for verification

        Returns:
            Document record or None
        """
        try:
            response = self.client.table("ragie_documents").select(
                "*"
            ).eq("ragie_document_id", str(ragie_document_id)).eq(
                "user_id", user_id
            ).single().execute()

            return response.data if response.data else None

        except Exception as e:
            logger.debug(f"Error getting document by ragie_id: {e}")
            return None

    async def create_group(
        self,
        user_id: str,
        name: str,
        sort_index: int = 0
    ) -> dict:
        """
        Create a document group.

        Args:
            user_id: User ID
            name: Group name
            sort_index: Sort order

        Returns:
            Created group record
        """
        try:
            response = self.client.table("app_groups").insert({
                "user_id": user_id,
                "name": name,
                "sort_index": sort_index
            }).execute()

            if response.data:
                logger.info(f"Created group {response.data[0]['group_id']}")
                return response.data[0]
            else:
                raise Exception("No data returned from insert")

        except Exception as e:
            logger.error(f"Error creating group: {e}")
            raise

    async def get_group(self, group_id: str, user_id: str) -> Optional[dict]:
        """Get group with user isolation."""
        try:
            response = self.client.table("app_groups").select(
                "*"
            ).eq("group_id", group_id).eq("user_id", user_id).single().execute()

            return response.data if response.data else None

        except Exception as e:
            logger.debug(f"Error getting group: {e}")
            return None

    async def list_groups(self, user_id: str) -> list:
        """List groups for a user."""
        try:
            response = self.client.table("app_groups").select(
                "*"
            ).eq("user_id", user_id).order("sort_index").execute()

            return response.data if response.data else []

        except Exception as e:
            logger.error(f"Error listing groups: {e}")
            return []

    async def update_group(
        self,
        group_id: str,
        user_id: str,
        name: Optional[str] = None,
        sort_index: Optional[int] = None
    ) -> dict:
        """Update a group with user isolation."""
        try:
            update_data = {}
            if name is not None:
                update_data["name"] = name
            if sort_index is not None:
                update_data["sort_index"] = sort_index
            update_data["updated_at"] = "NOW()"

            response = self.client.table("app_groups").update(
                update_data
            ).eq("group_id", group_id).eq("user_id", user_id).execute()

            if response.data:
                logger.info(f"Updated group {group_id}")
                return response.data[0]
            else:
                raise Exception("No data returned from update")

        except Exception as e:
            logger.error(f"Error updating group: {e}")
            raise

    async def delete_group(self, group_id: str, user_id: str) -> bool:
        """Delete a group with user isolation."""
        try:
            self.client.table("app_groups").delete().eq(
                "group_id", group_id
            ).eq("user_id", user_id).execute()

            logger.info(f"Deleted group {group_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting group: {e}")
            raise
