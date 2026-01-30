"""
CLIP-based label embedding service for object tagging.
Pre-computes and caches embeddings for object labels.
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from functools import lru_cache
from sentence_transformers import SentenceTransformer

# Use the same CLIP model as image embeddings for consistency
_model = SentenceTransformer("clip-ViT-B-32")


def load_object_labels() -> List[str]:
    """Load all object labels from the configuration file."""
    config_path = Path(__file__).parent.parent / "config" / "object_labels.json"

    with open(config_path, "r") as f:
        config = json.load(f)

    # Flatten all labels from all categories
    all_labels = []
    for category_data in config["categories"].values():
        all_labels.extend(category_data["labels"])

    return all_labels


@lru_cache(maxsize=1)
def get_label_embeddings() -> Tuple[List[str], np.ndarray]:
    """
    Get pre-computed embeddings for all object labels.
    Cached to avoid recomputing on every call.

    Returns:
        Tuple of (labels list, embeddings array)
    """
    labels = load_object_labels()

    # Compute embeddings for all labels using CLIP text encoder
    embeddings = _model.encode(
        labels,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True  # Normalize for cosine similarity
    )

    return labels, embeddings


def get_top_label_candidates(
    image_embedding: List[float],
    top_k: int = 15,
    min_confidence: float = 0.3
) -> List[Dict[str, any]]:
    """
    Compare image embedding against all label embeddings to find top candidates.

    Args:
        image_embedding: CLIP embedding of the image (512D)
        top_k: Number of top candidates to return
        min_confidence: Minimum cosine similarity threshold

    Returns:
        List of dicts with 'label' and 'confidence' keys
    """
    import logging
    logger = logging.getLogger(__name__)

    labels, label_embeddings = get_label_embeddings()

    # Convert image embedding to numpy array
    image_vec = np.array(image_embedding)

    logger.info(f"Image embedding shape: {image_vec.shape}, norm: {np.linalg.norm(image_vec):.4f}")

    # Normalize image embedding
    image_vec = image_vec / np.linalg.norm(image_vec)

    # Compute cosine similarities (dot product since both are normalized)
    similarities = np.dot(label_embeddings, image_vec)

    logger.info(f"Similarities - max: {similarities.max():.4f}, min: {similarities.min():.4f}, mean: {similarities.mean():.4f}")

    # Get top k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]

    # Log top candidates before filtering
    top_before_filter = [(labels[idx], float(similarities[idx])) for idx in top_indices[:5]]
    logger.info(f"Top 5 before filtering (threshold={min_confidence}): {top_before_filter}")

    # Filter by minimum confidence and format results
    candidates = []
    for idx in top_indices:
        confidence = float(similarities[idx])
        if confidence >= min_confidence:
            candidates.append({
                "label": labels[idx],
                "confidence": confidence
            })

    return candidates


def embed_labels(labels: List[str]) -> np.ndarray:
    """
    Embed a custom list of labels (for testing or custom labels).

    Args:
        labels: List of label strings

    Returns:
        Numpy array of embeddings (N x 512)
    """
    embeddings = _model.encode(
        labels,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True
    )

    return embeddings


# Warm up the cache on module import
get_label_embeddings()
