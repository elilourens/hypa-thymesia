"""
Unified database interface that combines Pinecone vector storage with Supabase metadata storage.
Replaces ChromaDB with the same architecture as the main hypa-thymesia backend.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib

from . import pinecone_service as pc
from . import supabase_service as sb


def sha256_hash(content: bytes) -> str:
    """Generate SHA256 hash of content."""
    return hashlib.sha256(content).hexdigest()


class VideoFrameDatabase:
    """
    Manages video frame embeddings using Pinecone + Supabase.
    Compatible with existing VideoDatabase interface.
    """

    def __init__(self, user_id: str, embedding_model: str = "clip-ViT-B-32", embedding_version: int = 1):
        """
        Initialize database for video frames.

        Args:
            user_id: User ID for namespace isolation
            embedding_model: Name of embedding model used
            embedding_version: Version number for re-embedding support
        """
        self.user_id = user_id
        self.embedding_model = embedding_model
        self.embedding_version = embedding_version
        print("Initialized VideoFrameDatabase with Pinecone + Supabase")

    def add_frames(
        self,
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ):
        """
        Add frame embeddings to Pinecone.

        Args:
            embeddings: List of embedding vectors
            metadatas: List of metadata dictionaries (video_id, frame_index, timestamp, storage_path, bucket, scene_id)
            ids: List of unique IDs (format: "video_id:frame_index")
        """
        if not embeddings or not metadatas or not ids:
            return

        # Build vectors for Pinecone
        vectors = []
        for i, (embedding, metadata, vector_id) in enumerate(zip(embeddings, metadatas, ids)):
            # Enrich metadata with system fields
            full_metadata = {
                "user_id": self.user_id,
                "video_id": metadata["video_id"],
                "frame_index": metadata["frame_index"],
                "timestamp": metadata["timestamp"],
                "storage_path": metadata["storage_path"],
                "bucket": metadata["bucket"],
                "modality": "video_frame",
                "embedding_model": self.embedding_model,
                "embedding_version": self.embedding_version,
                "upload_date": datetime.utcnow().date().isoformat(),
            }

            # Add optional fields
            if "scene_id" in metadata:
                full_metadata["scene_id"] = metadata["scene_id"]
            if "video_filename" in metadata:
                full_metadata["video_filename"] = metadata["video_filename"]

            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": full_metadata,
            })

        # Upsert to Pinecone
        pc.upsert_vectors(
            vectors=vectors,
            modality="video_frame",
            namespace=self.user_id,
        )

        print(f"Added {len(vectors)} frame embeddings to Pinecone")

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
        diversify: bool = True,
        diversity_weight: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Query frame embeddings from Pinecone.

        Args:
            query_embedding: Query embedding vector
            n_results: Number of results to return
            where_filter: Optional metadata filter (Pinecone filter syntax)
            diversify: Whether to apply diversity (currently not implemented)
            diversity_weight: Weight for diversity vs relevance

        Returns:
            List of result dictionaries with id, metadata, similarity
        """
        # Fetch more results for diversity if enabled
        fetch_count = n_results * 3 if diversify else n_results

        # Query Pinecone
        results = pc.query_vectors(
            vector=query_embedding,
            modality="video_frame",
            top_k=fetch_count,
            namespace=self.user_id,
            metadata_filter=where_filter,
            include_metadata=True,
        )

        # Format results
        formatted_results = []
        for match in results.matches:
            formatted_results.append({
                "id": match.id,
                "metadata": match.metadata,
                "score": match.score,
                "similarity": match.score,  # Pinecone returns cosine similarity
            })

        # Apply diversity if enabled
        if diversify and len(formatted_results) > n_results:
            formatted_results = self._diversify_results(
                formatted_results, n_results, diversity_weight
            )
        else:
            formatted_results = formatted_results[:n_results]

        return formatted_results

    def _diversify_results(
        self,
        results: List[Dict[str, Any]],
        n_results: int,
        diversity_weight: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Re-rank results to maximize scene diversity while maintaining relevance.
        Same algorithm as ChromaDB version.
        """
        if len(results) <= n_results:
            return results

        selected = []
        remaining = results.copy()
        selected_scenes = set()

        # Always select the best match first
        first_result = remaining.pop(0)
        selected.append(first_result)
        if "scene_id" in first_result["metadata"]:
            selected_scenes.add(first_result["metadata"]["scene_id"])

        has_scene_ids = "scene_id" in first_result["metadata"]

        # Greedily select remaining results
        while len(selected) < n_results and remaining:
            best_score = -float("inf")
            best_idx = 0

            for idx, candidate in enumerate(remaining):
                if has_scene_ids:
                    # Scene-based diversity
                    candidate_scene = candidate["metadata"].get("scene_id")
                    diversity_score = 1.0 if candidate_scene not in selected_scenes else 0.0
                else:
                    # Fallback to time-based diversity
                    min_time_diff = float("inf")
                    candidate_time = candidate["metadata"]["timestamp"]

                    for selected_result in selected:
                        selected_time = selected_result["metadata"]["timestamp"]
                        time_diff = abs(candidate_time - selected_time)
                        min_time_diff = min(min_time_diff, time_diff)

                    # Normalize temporal diversity (10s = full diversity score)
                    diversity_score = min(min_time_diff / 10.0, 1.0)

                # Relevance score
                relevance_score = candidate["similarity"]

                # Combined score
                combined_score = (
                    1 - diversity_weight
                ) * relevance_score + diversity_weight * diversity_score

                if combined_score > best_score:
                    best_score = combined_score
                    best_idx = idx

            selected_result = remaining.pop(best_idx)
            selected.append(selected_result)

            # Track selected scene
            if has_scene_ids and "scene_id" in selected_result["metadata"]:
                selected_scenes.add(selected_result["metadata"]["scene_id"])

        return selected

    def clear_collection(self):
        """
        Clear all vectors for this user.
        Note: Use with caution - deletes all frames for the user.
        """
        # Delete all vectors for this user's namespace
        pc.delete_by_filter(
            filter_dict={"user_id": {"$eq": self.user_id}},
            modality="video_frame",
            namespace=self.user_id,
        )
        print(f"Cleared all frame embeddings for user {self.user_id}")

    def count(self) -> int:
        """Get total number of frames in the database for this user."""
        stats = pc.get_index_stats("video_frame")
        namespaces = stats.get("namespaces", {})
        user_stats = namespaces.get(self.user_id, {})
        return user_stats.get("vector_count", 0)


class TranscriptDatabase:
    """
    Manages transcript embeddings using Pinecone + Supabase.
    Compatible with existing TranscriptDatabase interface.
    """

    def __init__(
        self,
        user_id: str,
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_version: int = 1,
    ):
        """
        Initialize database for transcripts.

        Args:
            user_id: User ID for namespace isolation
            embedding_model: Name of embedding model used
            embedding_version: Version number for re-embedding support
        """
        self.user_id = user_id
        self.embedding_model = embedding_model
        self.embedding_version = embedding_version
        print("Initialized TranscriptDatabase with Pinecone + Supabase")

    def add_transcripts(
        self,
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ):
        """
        Add transcript embeddings to Pinecone.

        Args:
            embeddings: List of embedding vectors
            metadatas: List of metadata dictionaries (video_id, start_time, end_time, text)
            ids: List of unique IDs (format: "video_id:chunk_index")
        """
        if not embeddings or not metadatas or not ids:
            return

        # Build vectors for Pinecone
        vectors = []
        for embedding, metadata, vector_id in zip(embeddings, metadatas, ids):
            # Enrich metadata with system fields
            full_metadata = {
                "user_id": self.user_id,
                "video_id": metadata["video_id"],
                "start_time": metadata["start_time"],
                "end_time": metadata["end_time"],
                "text": metadata["text"],  # Store full text for keyword search
                "modality": "video_transcript",
                "embedding_model": self.embedding_model,
                "embedding_version": self.embedding_version,
                "content_sha256": sha256_hash(metadata["text"].encode("utf-8")),
                "upload_date": datetime.utcnow().date().isoformat(),
            }

            # Add optional fields
            if "video_filename" in metadata:
                full_metadata["video_filename"] = metadata["video_filename"]

            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": full_metadata,
            })

        # Upsert to Pinecone
        pc.upsert_vectors(
            vectors=vectors,
            modality="video_transcript",
            namespace=self.user_id,
        )

        print(f"Added {len(vectors)} transcript embeddings to Pinecone")

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
        diversify: bool = True,
        diversity_weight: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Query transcript embeddings from Pinecone.

        Args:
            query_embedding: Query embedding vector
            n_results: Number of results to return
            where_filter: Optional metadata filter (Pinecone filter syntax)
            diversify: Whether to apply temporal diversity
            diversity_weight: Weight for diversity vs relevance

        Returns:
            List of result dictionaries with id, metadata, similarity
        """
        # Fetch more results for diversity if enabled
        fetch_count = n_results * 3 if diversify else n_results

        # Query Pinecone
        results = pc.query_vectors(
            vector=query_embedding,
            modality="video_transcript",
            top_k=fetch_count,
            namespace=self.user_id,
            metadata_filter=where_filter,
            include_metadata=True,
        )

        # Format results
        formatted_results = []
        for match in results.matches:
            formatted_results.append({
                "id": match.id,
                "metadata": match.metadata,
                "score": match.score,
                "similarity": match.score,
            })

        # Apply diversity if enabled
        if diversify and len(formatted_results) > n_results:
            formatted_results = self._diversify_results(
                formatted_results, n_results, diversity_weight
            )
        else:
            formatted_results = formatted_results[:n_results]

        return formatted_results

    def _diversify_results(
        self,
        results: List[Dict[str, Any]],
        n_results: int,
        diversity_weight: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Re-rank results to maximize temporal diversity while maintaining relevance.
        Same algorithm as ChromaDB version.
        """
        if len(results) <= n_results:
            return results

        selected = []
        remaining = results.copy()

        # Always select the best match first
        selected.append(remaining.pop(0))

        # Greedily select remaining results
        while len(selected) < n_results and remaining:
            best_score = -float("inf")
            best_idx = 0

            for idx, candidate in enumerate(remaining):
                # Calculate temporal diversity
                min_time_diff = float("inf")
                candidate_start = float(candidate["metadata"]["start_time"])

                for selected_result in selected:
                    selected_start = float(selected_result["metadata"]["start_time"])
                    time_diff = abs(candidate_start - selected_start)
                    min_time_diff = min(min_time_diff, time_diff)

                # Normalize temporal diversity (20s = full diversity score)
                diversity_score = min(min_time_diff / 20.0, 1.0)

                # Relevance score
                relevance_score = candidate["similarity"]

                # Combined score
                combined_score = (
                    1 - diversity_weight
                ) * relevance_score + diversity_weight * diversity_score

                if combined_score > best_score:
                    best_score = combined_score
                    best_idx = idx

            selected.append(remaining.pop(best_idx))

        return selected

    def clear_collection(self):
        """
        Clear all transcript vectors for this user.
        Note: Use with caution - deletes all transcripts for the user.
        """
        # Delete all vectors for this user's namespace
        pc.delete_by_filter(
            filter_dict={"user_id": {"$eq": self.user_id}},
            modality="video_transcript",
            namespace=self.user_id,
        )
        print(f"Cleared all transcript embeddings for user {self.user_id}")

    def count(self) -> int:
        """Get total number of transcript chunks in the database for this user."""
        stats = pc.get_index_stats("video_transcript")
        namespaces = stats.get("namespaces", {})
        user_stats = namespaces.get(self.user_id, {})
        return user_stats.get("vector_count", 0)
