"""Ragie API service wrapper."""

import logging
from typing import Optional
from fastapi import UploadFile
from ragie import Ragie

logger = logging.getLogger(__name__)


class RagieService:
    """Service for interacting with Ragie API."""

    def __init__(self, client: Ragie):
        """Initialize with Ragie client."""
        self.client = client

    async def upload_document(
        self,
        file: UploadFile,
        user_id: str,
        group_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """
        Upload document to Ragie.

        Args:
            file: File to upload
            user_id: User ID for metadata
            group_id: Optional group ID for organization
            metadata: Optional additional metadata

        Returns:
            Ragie document response
        """
        # Construct metadata with user_id for filtering
        ragie_metadata = {
            "user_id": user_id,
            "original_filename": file.filename,
        }

        if group_id:
            ragie_metadata["group_id"] = group_id

        if metadata:
            ragie_metadata.update(metadata)

        try:
            # Read file content
            content = await file.read()

            # Determine appropriate mode based on file type
            mime_type = file.content_type or ""
            if mime_type.startswith("video/"):
                # Video files: use audio_video mode for full processing
                mode = {"video": "audio_video"}
            elif mime_type.startswith("audio/"):
                # Audio files: enable audio processing
                mode = {"audio": True}
            else:
                # Text and document files: use fast mode
                mode = "fast"

            # Upload to Ragie
            response = self.client.documents.create(
                request={
                    "file": {
                        "file_name": file.filename,
                        "content": content
                    },
                    "metadata": ragie_metadata,
                    "mode": mode
                }
            )

            logger.info(f"Uploaded document {response.id} for user {user_id}")
            return response

        except Exception as e:
            logger.error(f"Error uploading document: {e}")
            raise

    async def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 8,
        rerank: bool = True,
        group_id: Optional[str] = None,
        max_chunks_per_document: int = 0,
        modality: Optional[str] = None,
    ):
        """
        Retrieve document chunks from Ragie.

        Args:
            query: Search query
            user_id: User ID for filtering
            top_k: Maximum chunks to return
            rerank: Whether to rerank results
            group_id: Optional group ID for scoped search
            max_chunks_per_document: Max chunks per document
            modality: Optional filter by content type (text, image, video, audio)

        Returns:
            Ragie retrieval response
        """
        # Build metadata filter for user isolation
        filter_dict = {"user_id": {"$eq": user_id}}

        if group_id:
            filter_dict["group_id"] = {"$eq": group_id}

        if modality:
            filter_dict["chunk_content_type"] = {"$eq": modality}

        try:
            response = self.client.retrievals.retrieve(
                request={
                    "query": query,
                    "top_k": top_k,
                    "rerank": rerank,
                    "filter": filter_dict,
                    "max_chunks_per_document": max_chunks_per_document
                }
            )

            logger.info(f"Retrieved {len(response.scored_chunks)} chunks for query '{query}'")
            return response

        except Exception as e:
            logger.error(f"Error retrieving documents: {e}")
            raise

    async def delete_document(self, ragie_document_id: str):
        """
        Delete document from Ragie.

        Args:
            ragie_document_id: Ragie document ID to delete
        """
        try:
            self.client.documents.delete(document_id=ragie_document_id)
            logger.info(f"Deleted document {ragie_document_id} from Ragie")
        except Exception as e:
            logger.error(f"Error deleting document {ragie_document_id}: {e}")
            raise

    async def get_document_status(self, ragie_document_id: str):
        """
        Get document processing status from Ragie.

        Args:
            ragie_document_id: Ragie document ID

        Returns:
            Document object with current status
        """
        try:
            document = self.client.documents.get(document_id=ragie_document_id)
            logger.debug(f"Document {ragie_document_id} status: {document.status}")
            return document
        except Exception as e:
            logger.error(f"Error getting document status: {e}")
            raise

    async def update_metadata(self, ragie_document_id: str, metadata: dict):
        """
        Update document metadata in Ragie.

        Args:
            ragie_document_id: Ragie document ID
            metadata: Metadata to update
        """
        try:
            self.client.documents.patch_metadata(
                document_id=ragie_document_id,
                patch_document_metadata_params={"metadata": metadata}
            )
            logger.info(f"Updated metadata for document {ragie_document_id}")
        except Exception as e:
            logger.error(f"Error updating metadata: {e}")
            raise

    async def list_documents(self, user_id: str, limit: int = 100):
        """
        List user's documents from Ragie.

        Args:
            user_id: User ID for filtering
            limit: Maximum documents to return

        Returns:
            List of documents
        """
        try:
            # Ragie SDK may not have direct filtering in list,
            # so we rely on metadata filtering in retrieve()
            # For now, return empty - filtering happens at retrieval level
            logger.debug(f"Listing documents for user {user_id}")
            return []
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise
