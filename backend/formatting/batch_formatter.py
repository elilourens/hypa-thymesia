"""
Batch chunk formatting service.
Handles formatting of document chunks with Pinecone metadata updates.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pinecone import Pinecone
from supabase import Client

from formatting.ollama_formatter import OllamaFormatter

logger = logging.getLogger(__name__)


class BatchChunkFormatter:
    """Formats document chunks in batches and updates Pinecone metadata."""

    def __init__(
        self,
        supabase: Client,
        pinecone_client: Pinecone,
        formatter: Optional[OllamaFormatter] = None
    ):
        """
        Initialize batch formatter.

        Args:
            supabase: Supabase client for database operations
            pinecone_client: Pinecone client for vector operations
            formatter: OllamaFormatter instance (creates new one if None)
        """
        self.supabase = supabase
        self.pc = pinecone_client
        self.formatter = formatter or OllamaFormatter()

        # Get Pinecone index for text chunks
        text_index_name = os.getenv("PINECONE_TEXT_INDEX_NAME")
        if not text_index_name:
            raise RuntimeError("PINECONE_TEXT_INDEX_NAME environment variable not set")
        self.text_index = self.pc.Index(text_index_name)

        logger.info("Initialized BatchChunkFormatter")

    async def format_document_chunks(
        self,
        doc_id: str,
        user_id: str,
        max_chunks: int = 100
    ) -> dict:
        """
        Format all text chunks for a document.

        Args:
            doc_id: Document ID
            user_id: User ID (for Pinecone namespace)
            max_chunks: Maximum chunks to format in this batch

        Returns:
            Dict with formatting results:
            {
                "doc_id": str,
                "total_chunks": int,
                "formatted": int,
                "failed": int,
                "skipped": int,
                "errors": list[str]
            }
        """
        logger.info(f"Starting batch formatting for doc_id={doc_id}, user_id={user_id}")

        results = {
            "doc_id": doc_id,
            "total_chunks": 0,
            "formatted": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }

        try:
            # 1. Get all text chunks for this document from database
            chunks_response = self.supabase.table("app_chunks").select(
                "chunk_id, chunk_index, modality, formatting_status"
            ).eq("doc_id", doc_id).eq("user_id", user_id).eq(
                "modality", "text"
            ).order("chunk_index").limit(max_chunks).execute()

            if not chunks_response.data:
                logger.warning(f"No text chunks found for doc_id={doc_id}")
                return results

            chunks = chunks_response.data
            results["total_chunks"] = len(chunks)

            logger.info(f"Found {len(chunks)} text chunks to process")

            # 2. Filter out already formatted chunks
            unformatted_chunks = [
                c for c in chunks
                if c.get("formatting_status") != "formatted"
            ]

            results["skipped"] = len(chunks) - len(unformatted_chunks)

            if not unformatted_chunks:
                logger.info("All chunks already formatted")
                return results

            logger.info(f"Processing {len(unformatted_chunks)} unformatted chunks")

            # 3. Fetch chunk text from Pinecone
            # Note: Pinecone vector IDs are stored as {chunk_id}:{embedding_version}
            # We need to construct the full vector IDs
            chunk_id_map = {c["chunk_id"]: c for c in unformatted_chunks}
            pinecone_data = self._fetch_chunks_from_pinecone(chunk_id_map, user_id)

            if not pinecone_data:
                results["errors"].append("Failed to fetch chunks from Pinecone")
                return results

            # 4. Mark chunks as "formatting" in database
            self._update_chunk_status(list(pinecone_data.keys()), "formatting")

            # 5. Format chunks using Ollama with concurrent processing
            # Default to OLLAMA_NUM_PARALLEL env var, or 10 as fallback
            # Higher concurrency is needed since we're doing 1 chunk per request for reliability
            max_concurrent = int(os.getenv("OLLAMA_NUM_PARALLEL", "10"))
            formatted_results = await self._format_chunks_with_ollama(pinecone_data, max_concurrent=max_concurrent)

            # 6. Batch update Pinecone metadata with formatted text
            if formatted_results["formatted"]:
                try:
                    formatted_chunk_ids = [cid for cid, _ in formatted_results["formatted"]]
                    formatted_texts = {cid: txt for cid, txt in formatted_results["formatted"]}

                    self._batch_update_pinecone_metadata(formatted_chunk_ids, user_id, formatted_texts)
                    self._batch_mark_chunks_formatted(formatted_chunk_ids)

                    results["formatted"] = len(formatted_chunk_ids)
                    logger.info(f"Successfully updated {len(formatted_chunk_ids)} chunks in Pinecone")
                except Exception as e:
                    logger.error(f"Failed to batch update Pinecone: {e}", exc_info=True)
                    # Fall back to individual updates if batch fails
                    for chunk_id, formatted_text in formatted_results["formatted"]:
                        try:
                            self._update_pinecone_metadata(chunk_id, user_id, formatted_text)
                            self._mark_chunk_formatted(chunk_id)
                            results["formatted"] += 1
                        except Exception as e:
                            logger.error(f"Failed to update chunk {chunk_id}: {e}")
                            results["failed"] += 1
                            results["errors"].append(f"Chunk {chunk_id}: {str(e)}")

            # 7. Batch mark failed chunks
            if formatted_results["failed"]:
                failed_chunk_data = {cid: err for cid, err in formatted_results["failed"]}
                self._batch_mark_chunks_failed(failed_chunk_data)
                results["failed"] = len(formatted_results["failed"])
                for chunk_id, error in formatted_results["failed"]:
                    results["errors"].append(f"Chunk {chunk_id}: {error}")

            logger.info(
                f"Batch formatting complete: {results['formatted']} formatted, "
                f"{results['failed']} failed, {results['skipped']} skipped"
            )

            return results

        except Exception as e:
            logger.error(f"Batch formatting failed: {e}", exc_info=True)
            results["errors"].append(f"Batch error: {str(e)}")
            return results

    def _get_value(self, obj, key: str, default=None):
        """Get value from dict or object attribute."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _fetch_chunks_from_pinecone(
        self,
        chunk_id_map: dict[str, dict],
        user_id: str
    ) -> dict[str, str]:
        """Fetch chunk text from Pinecone by chunk IDs. Returns dict of chunk_id -> text."""
        try:
            chunk_ids = list(chunk_id_map.keys())
            logger.info(f"Fetching {len(chunk_ids)} chunks from Pinecone")

            # Get vector IDs from registry (Pinecone uses {chunk_id}:{embedding_version} format)
            vectors_response = self.supabase.table("app_vector_registry").select(
                "chunk_id, vector_id"
            ).in_("chunk_id", chunk_ids).execute()

            if not vectors_response.data:
                return {}

            # Fetch from Pinecone
            vector_id_map = {v["chunk_id"]: v["vector_id"] for v in vectors_response.data}
            fetch_response = self.text_index.fetch(
                ids=list(vector_id_map.values()),
                namespace=user_id
            )

            vectors_dict = self._get_value(fetch_response, 'vectors', {})
            if not vectors_dict:
                return {}

            # Extract texts
            reverse_map = {v: k for k, v in vector_id_map.items()}
            chunk_data = {}

            for vector_id, vector_obj in vectors_dict.items():
                chunk_id = reverse_map.get(vector_id)
                if not chunk_id:
                    continue

                metadata = self._get_value(vector_obj, 'metadata', {})
                text = self._get_value(metadata, 'text', '')

                if text:
                    chunk_data[chunk_id] = text

            logger.info(f"Retrieved {len(chunk_data)}/{len(chunk_ids)} chunk texts")
            return chunk_data

        except Exception as e:
            logger.error(f"Failed to fetch chunks from Pinecone: {e}", exc_info=True)
            return {}

    async def _format_single_chunk(self, chunk_id: str, text: str) -> tuple[str, str | None, str | None]:
        """Format a single chunk. Returns (chunk_id, formatted_text or None, error or None)."""
        try:
            loop = asyncio.get_event_loop()
            formatted_text = await loop.run_in_executor(None, self.formatter.format_chunk, text)
            return (chunk_id, formatted_text, None if formatted_text else "Formatter returned None")
        except Exception as e:
            logger.error(f"Failed to format chunk {chunk_id}: {e}")
            return (chunk_id, None, str(e))

    async def _format_chunks_with_ollama(self, chunk_data: dict[str, str], max_concurrent: int = 10) -> dict:
        """Format chunks with concurrent processing. Returns dict with 'formatted' and 'failed' lists."""
        logger.info(f"Formatting {len(chunk_data)} chunks (max {max_concurrent} concurrent)")

        # Create bounded tasks
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_format(chunk_id, text):
            async with semaphore:
                return await self._format_single_chunk(chunk_id, text)

        # Execute all tasks
        results = await asyncio.gather(*[
            bounded_format(chunk_id, text)
            for chunk_id, text in chunk_data.items()
        ])

        # Separate successful and failed
        formatted = [(cid, txt) for cid, txt, err in results if txt]
        failed = [(cid, err or "Unknown error") for cid, txt, err in results if not txt]

        logger.info(f"Formatting complete: {len(formatted)} succeeded, {len(failed)} failed")

        return {"formatted": formatted, "failed": failed}

    def _batch_update_pinecone_metadata(
        self,
        chunk_ids: list[str],
        user_id: str,
        formatted_texts: dict[str, str]
    ):
        """Batch update Pinecone vector metadata with formatted text."""
        try:
            # Get vector_ids from registry
            vectors_response = self.supabase.table("app_vector_registry").select(
                "chunk_id, vector_id"
            ).in_("chunk_id", chunk_ids).execute()

            if not vectors_response.data:
                raise ValueError("No vector_ids found for chunks")

            vector_id_map = {v["chunk_id"]: v["vector_id"] for v in vectors_response.data}

            # Fetch all vectors at once
            vector_ids = list(vector_id_map.values())
            fetch_response = self.text_index.fetch(ids=vector_ids, namespace=user_id)
            vectors_dict = self._get_value(fetch_response, 'vectors', {})

            if not vectors_dict:
                raise ValueError("No vectors found in Pinecone")

            # Prepare batch update
            formatted_at = datetime.now(timezone.utc).isoformat()
            vectors_to_upsert = []

            for chunk_id in chunk_ids:
                vector_id = vector_id_map.get(chunk_id)
                if not vector_id:
                    logger.warning(f"No vector_id found for chunk {chunk_id}")
                    continue

                vector_obj = vectors_dict.get(vector_id)
                if not vector_obj:
                    logger.warning(f"Vector not found for vector_id {vector_id}")
                    continue

                current_metadata = self._get_value(vector_obj, "metadata", {})
                values = self._get_value(vector_obj, "values", [])

                updated_metadata = {
                    **current_metadata,
                    "formatted_text": formatted_texts[chunk_id],
                    "formatted_at": formatted_at
                }

                vectors_to_upsert.append({
                    "id": vector_id,
                    "values": values,
                    "metadata": updated_metadata
                })

            # Batch upsert to Pinecone (up to 1000 vectors per request)
            batch_size = 1000
            for i in range(0, len(vectors_to_upsert), batch_size):
                batch = vectors_to_upsert[i:i + batch_size]
                self.text_index.upsert(vectors=batch, namespace=user_id)
                logger.debug(f"Updated batch of {len(batch)} vectors in Pinecone")

            logger.info(f"Batch updated {len(vectors_to_upsert)} vectors in Pinecone")

        except Exception as e:
            logger.error(f"Failed to batch update Pinecone metadata: {e}", exc_info=True)
            raise

    def _update_pinecone_metadata(self, chunk_id: str, user_id: str, formatted_text: str):
        """Update Pinecone vector metadata with formatted text."""
        try:
            # Get vector_id from registry
            vector_response = self.supabase.table("app_vector_registry").select(
                "vector_id"
            ).eq("chunk_id", chunk_id).limit(1).execute()

            if not vector_response.data:
                raise ValueError(f"No vector_id found for chunk {chunk_id}")

            vector_id = vector_response.data[0]["vector_id"]

            # Fetch current vector
            fetch_response = self.text_index.fetch(ids=[vector_id], namespace=user_id)
            vectors_dict = self._get_value(fetch_response, 'vectors', {})
            vector_obj = vectors_dict.get(vector_id)

            if not vector_obj:
                raise ValueError(f"Vector not found for vector_id {vector_id}")

            # Update metadata
            current_metadata = self._get_value(vector_obj, "metadata", {})
            values = self._get_value(vector_obj, "values", [])

            updated_metadata = {
                **current_metadata,
                "formatted_text": formatted_text,
                "formatted_at": datetime.now(timezone.utc).isoformat()
            }

            # Upsert with updated metadata
            self.text_index.upsert(
                vectors=[{"id": vector_id, "values": values, "metadata": updated_metadata}],
                namespace=user_id
            )

            logger.debug(f"Updated metadata for chunk {chunk_id}")

        except Exception as e:
            logger.error(f"Failed to update Pinecone metadata for chunk {chunk_id}: {e}", exc_info=True)
            raise

    def _update_chunk_status(self, chunk_ids: list[str], status: str):
        """Update formatting status for multiple chunks."""
        try:
            # Batch update using Supabase's IN filter
            self.supabase.table("app_chunks").update({
                "formatting_status": status
            }).in_("chunk_id", chunk_ids).execute()
            logger.debug(f"Updated status to '{status}' for {len(chunk_ids)} chunks")
        except Exception as e:
            logger.error(f"Failed to update chunk status: {e}", exc_info=True)

    def _batch_mark_chunks_formatted(self, chunk_ids: list[str]):
        """Batch mark chunks as successfully formatted."""
        try:
            formatted_at = datetime.now(timezone.utc).isoformat()
            self.supabase.table("app_chunks").update({
                "formatting_status": "formatted",
                "formatted_at": formatted_at,
                "formatting_error": None
            }).in_("chunk_id", chunk_ids).execute()
            logger.debug(f"Marked {len(chunk_ids)} chunks as formatted")
        except Exception as e:
            logger.error(f"Failed to batch mark chunks as formatted: {e}", exc_info=True)
            # Fall back to individual updates
            for chunk_id in chunk_ids:
                self._mark_chunk_formatted(chunk_id)

    def _batch_mark_chunks_failed(self, failed_chunks: dict[str, str]):
        """Batch mark chunks as failed formatting.

        Args:
            failed_chunks: Dict mapping chunk_id to error message
        """
        try:
            # PostgreSQL/Supabase doesn't support different values per row in a simple update,
            # so we need to do individual updates for failed chunks (they have different errors)
            for chunk_id, error in failed_chunks.items():
                self._mark_chunk_failed(chunk_id, error)
            logger.debug(f"Marked {len(failed_chunks)} chunks as failed")
        except Exception as e:
            logger.error(f"Failed to batch mark chunks as failed: {e}", exc_info=True)

    def _mark_chunk_formatted(self, chunk_id: str):
        """Mark chunk as successfully formatted."""
        try:
            self.supabase.table("app_chunks").update({
                "formatting_status": "formatted",
                "formatted_at": datetime.now(timezone.utc).isoformat(),
                "formatting_error": None
            }).eq("chunk_id", chunk_id).execute()
        except Exception as e:
            logger.error(f"Failed to mark chunk {chunk_id} as formatted: {e}")

    def _mark_chunk_failed(self, chunk_id: str, error: str):
        """Mark chunk as failed formatting."""
        try:
            self.supabase.table("app_chunks").update({
                "formatting_status": "failed",
                "formatting_error": error[:500]
            }).eq("chunk_id", chunk_id).execute()
        except Exception as e:
            logger.error(f"Failed to mark chunk {chunk_id} as failed: {e}")
