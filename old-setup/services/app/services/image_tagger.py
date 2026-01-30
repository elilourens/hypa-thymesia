"""
Two-stage image tagging service: CLIP filtering + OWL-ViT verification.

Uses CLIP to quickly identify candidate labels from pre-computed embeddings,
then verifies with OWL-ViT open-vocabulary object detection.
"""

import io
import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from functools import lru_cache
from dataclasses import dataclass

import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import OwlViTProcessor, OwlViTForObjectDetection
import torch

logger = logging.getLogger(__name__)


# ============================================================================
# CLIP Label Embedder
# ============================================================================

# Initialize CLIP model (same as used for image embeddings)
_clip_model: Optional[SentenceTransformer] = None


def get_clip_model() -> SentenceTransformer:
    """Get or initialize the CLIP model."""
    global _clip_model
    if _clip_model is None:
        logger.info("Loading CLIP model: clip-ViT-B-32")
        _clip_model = SentenceTransformer("clip-ViT-B-32")
        logger.info("CLIP model loaded successfully")
    return _clip_model


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
    model = get_clip_model()

    # Compute embeddings for all labels using CLIP text encoder
    embeddings = model.encode(
        labels,
        convert_to_numpy=True,
        show_progress_bar=False,
        normalize_embeddings=True
    )

    logger.info(f"Computed embeddings for {len(labels)} object labels")
    return labels, embeddings


def get_top_label_candidates(
    image_embedding: List[float],
    top_k: int = 15,
    min_confidence: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Compare image embedding against all label embeddings to find top candidates.

    Args:
        image_embedding: CLIP embedding of the image (512D)
        top_k: Number of top candidates to return
        min_confidence: Minimum cosine similarity threshold

    Returns:
        List of dicts with 'label' and 'confidence' keys
    """
    labels, label_embeddings = get_label_embeddings()

    # Convert image embedding to numpy array
    image_vec = np.array(image_embedding)

    # Normalize image embedding
    image_vec = image_vec / np.linalg.norm(image_vec)

    # Compute cosine similarities (dot product since both are normalized)
    similarities = np.dot(label_embeddings, image_vec)

    # Get top k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]

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


# ============================================================================
# OWL-ViT Object Detector
# ============================================================================

# Initialize OWL-ViT model and processor
_owlvit_processor: Optional[OwlViTProcessor] = None
_owlvit_model: Optional[OwlViTForObjectDetection] = None
_owlvit_device: str = "cpu"


def get_owlvit_model() -> Tuple[OwlViTProcessor, OwlViTForObjectDetection, str]:
    """Get or initialize the OWL-ViT model."""
    global _owlvit_processor, _owlvit_model, _owlvit_device

    if _owlvit_processor is None:
        logger.info("Loading OWL-ViT model: google/owlvit-base-patch32")

        _owlvit_processor = OwlViTProcessor.from_pretrained("google/owlvit-base-patch32")
        _owlvit_model = OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32")

        # Use GPU if available
        _owlvit_device = "cuda" if torch.cuda.is_available() else "cpu"
        _owlvit_model.to(_owlvit_device)
        _owlvit_model.eval()

        logger.info(f"OWL-ViT model loaded successfully on {_owlvit_device}")

    return _owlvit_processor, _owlvit_model, _owlvit_device


def verify_labels_in_image(
    image_bytes: bytes,
    candidate_labels: List[str],
    min_confidence: float = 0.7,
    max_detections_per_label: int = 3
) -> List[Dict[str, Any]]:
    """
    Verify which candidate labels actually appear in the image using OWL-ViT.

    Args:
        image_bytes: Raw image bytes
        candidate_labels: List of label strings to search for
        min_confidence: Minimum detection confidence threshold (0.0-1.0)
        max_detections_per_label: Maximum number of detections per label

    Returns:
        List of verified detections with format:
        [
            {
                "label": str,
                "confidence": float,
                "bbox": {"x": int, "y": int, "width": int, "height": int}
            },
            ...
        ]
    """
    if not candidate_labels:
        return []

    processor, model, device = get_owlvit_model()

    # Load image
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_width, img_height = image.size
    except Exception as e:
        logger.error(f"Failed to load image from bytes: {e}")
        return []

    # Prepare text queries (OWL-ViT expects phrases)
    text_queries = [[label] for label in candidate_labels]

    # Process inputs
    inputs = processor(
        text=text_queries,
        images=image,
        return_tensors="pt"
    ).to(device)

    # Run inference
    with torch.no_grad():
        outputs = model(**inputs)

    # Post-process results with threshold
    target_sizes = torch.Tensor([[img_height, img_width]]).to(device)
    results = processor.post_process_object_detection(
        outputs=outputs,
        target_sizes=target_sizes,
        threshold=min_confidence
    )[0]

    verified_detections = []
    label_counts = {}

    for box, score, label_idx in zip(
        results["boxes"],
        results["scores"],
        results["labels"]
    ):
        label = candidate_labels[label_idx]

        # Limit detections per label
        if label_counts.get(label, 0) >= max_detections_per_label:
            continue

        # Convert box from [y1, x1, y2, x2] to [x, y, width, height]
        y1, x1, y2, x2 = box.cpu().numpy()

        bbox = {
            "x": int(x1),
            "y": int(y1),
            "width": int(x2 - x1),
            "height": int(y2 - y1)
        }

        verified_detections.append({
            "label": label,
            "confidence": float(score.cpu().numpy()),
            "bbox": bbox
        })

        label_counts[label] = label_counts.get(label, 0) + 1

    return verified_detections


def get_unique_verified_labels(detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Get unique labels from detections, keeping the highest confidence for each.
    """
    label_map = {}

    for detection in detections:
        label = detection["label"]
        confidence = detection["confidence"]

        if label not in label_map or confidence > label_map[label]["confidence"]:
            label_map[label] = detection

    return list(label_map.values())


# ============================================================================
# Combined Tagging Pipeline
# ============================================================================

@dataclass
class ImageTagResult:
    """Result from image tagging pipeline."""
    verified_tags: List[Dict[str, Any]]
    candidate_tags: List[Dict[str, Any]]
    processing_time_ms: float


def tag_image(
    image_embedding: List[float],
    image_bytes: bytes,
    clip_top_k: int = 15,
    clip_min_confidence: float = 0.15,
    owlvit_min_confidence: float = 0.15
) -> ImageTagResult:
    """
    Run the complete two-stage tagging pipeline for an image.

    Args:
        image_embedding: Pre-computed CLIP image embedding (512D)
        image_bytes: Raw image bytes
        clip_top_k: Number of CLIP candidates to generate
        clip_min_confidence: Minimum CLIP confidence threshold
        owlvit_min_confidence: Minimum OWL-ViT confidence threshold

    Returns:
        ImageTagResult with verified and candidate tags
    """
    start_time = time.time()

    # Stage 1: CLIP filtering (fast)
    clip_candidates = get_top_label_candidates(
        image_embedding,
        clip_top_k,
        clip_min_confidence
    )

    logger.info(f"CLIP generated {len(clip_candidates)} candidates")
    if clip_candidates:
        top_5 = [(c['label'], f"{c['confidence']:.2f}") for c in clip_candidates[:5]]
        logger.debug(f"Top 5 CLIP candidates: {top_5}")

    if not clip_candidates:
        logger.warning("No CLIP candidates found")
        return ImageTagResult(
            verified_tags=[],
            candidate_tags=[],
            processing_time_ms=(time.time() - start_time) * 1000
        )

    # Extract label strings for OWL-ViT
    candidate_labels = [c["label"] for c in clip_candidates]

    # Stage 2: OWL-ViT verification (slower but precise)
    detections = verify_labels_in_image(
        image_bytes,
        candidate_labels,
        owlvit_min_confidence
    )

    logger.info(f"OWL-ViT returned {len(detections)} detections")

    # Get unique verified labels
    unique_detections = get_unique_verified_labels(detections)

    processing_time = (time.time() - start_time) * 1000

    return ImageTagResult(
        verified_tags=unique_detections,
        candidate_tags=clip_candidates,
        processing_time_ms=processing_time
    )


def warmup_models():
    """Pre-load models on startup to avoid cold start latency."""
    logger.info("Warming up image tagging models...")

    # Warm up CLIP
    get_label_embeddings()

    # Warm up OWL-ViT
    get_owlvit_model()

    logger.info("Image tagging models warmed up successfully")
