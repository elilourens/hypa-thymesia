"""
OWL-ViT object detection service for verifying CLIP label candidates.
Uses open-vocabulary object detection to locate objects in images.
"""

import io
from typing import List, Dict
from PIL import Image
from transformers import OwlViTProcessor, OwlViTForObjectDetection
import torch
import numpy as np


# Initialize OWL-ViT model and processor
_processor = OwlViTProcessor.from_pretrained("google/owlvit-base-patch32")
_model = OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32")

# Use GPU if available
_device = "cuda" if torch.cuda.is_available() else "cpu"
_model.to(_device)
_model.eval()


def verify_labels_in_image(
    image_bytes: bytes,
    candidate_labels: List[str],
    min_confidence: float = 0.7,
    max_detections_per_label: int = 3
) -> List[Dict[str, any]]:
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
    import logging
    logger = logging.getLogger(__name__)

    if not candidate_labels:
        return []

    logger.info(f"OWL-ViT received: image_bytes type={type(image_bytes)}, size={len(image_bytes) if isinstance(image_bytes, bytes) else 'unknown'}")

    # Load image
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_width, img_height = image.size
        logger.info(f"Loaded image successfully: {img_width}x{img_height}")
    except Exception as e:
        logger.error(f"Failed to load image from bytes: {e}")
        return []

    # Prepare text queries (OWL-ViT expects phrases)
    text_queries = [[label] for label in candidate_labels]

    # Process inputs
    inputs = _processor(
        text=text_queries,
        images=image,
        return_tensors="pt"
    ).to(_device)

    # Run inference
    with torch.no_grad():
        outputs = _model(**inputs)

    # Get raw logits before post-processing
    logits = outputs.logits[0]  # Shape: [num_queries, num_labels]
    pred_boxes = outputs.pred_boxes[0]  # Shape: [num_queries, 4]

    # Get max score per query across all labels
    max_scores = logits.sigmoid().max(dim=-1)[0]
    logger.info(f"Raw OWL-ViT logits - max score: {max_scores.max():.4f}, min: {max_scores.min():.4f}, mean: {max_scores.mean():.4f}")

    # Log top 5 raw scores
    top_5_scores, top_5_query_indices = torch.topk(max_scores, k=min(5, len(max_scores)))
    logger.info(f"Top 5 raw query scores: {[f'{s:.4f}' for s in top_5_scores.cpu().numpy()]}")

    # Post-process results with threshold
    target_sizes = torch.Tensor([[img_height, img_width]]).to(_device)
    results = _processor.post_process_object_detection(
        outputs=outputs,
        target_sizes=target_sizes,
        threshold=min_confidence
    )[0]

    verified_detections = []
    label_counts = {}

    # Log all detections (even below threshold) for debugging
    all_scores = results["scores"].cpu().numpy() if len(results["scores"]) > 0 else []
    if len(all_scores) > 0:
        logger.info(f"After post-processing - scores count: {len(all_scores)}, max: {all_scores.max():.4f}, min: {all_scores.min():.4f}")
        # Log top 5 detections regardless of threshold
        top_5_indices = np.argsort(all_scores)[::-1][:5]
        top_5 = [(candidate_labels[results["labels"][i]], all_scores[i]) for i in top_5_indices if i < len(all_scores)]
        logger.info(f"Top 5 OWL-ViT detections (threshold={min_confidence}): {top_5}")
    else:
        logger.info(f"Post-processing returned 0 detections with threshold={min_confidence}")

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


def batch_verify_labels(
    image_bytes_list: List[bytes],
    candidate_labels_list: List[List[str]],
    min_confidence: float = 0.7,
    max_detections_per_label: int = 3
) -> List[List[Dict[str, any]]]:
    """
    Verify labels for multiple images in batch.

    Args:
        image_bytes_list: List of image bytes
        candidate_labels_list: List of label lists (one per image)
        min_confidence: Minimum detection confidence
        max_detections_per_label: Max detections per label

    Returns:
        List of verification results (one per image)
    """
    results = []

    for image_bytes, candidate_labels in zip(image_bytes_list, candidate_labels_list):
        detections = verify_labels_in_image(
            image_bytes=image_bytes,
            candidate_labels=candidate_labels,
            min_confidence=min_confidence,
            max_detections_per_label=max_detections_per_label
        )
        results.append(detections)

    return results


def get_unique_verified_labels(detections: List[Dict[str, any]]) -> List[Dict[str, any]]:
    """
    Get unique labels from detections, keeping the highest confidence for each.

    Args:
        detections: List of detection dicts

    Returns:
        List of unique labels with highest confidence and first bbox
    """
    label_map = {}

    for detection in detections:
        label = detection["label"]
        confidence = detection["confidence"]

        if label not in label_map or confidence > label_map[label]["confidence"]:
            label_map[label] = detection

    return list(label_map.values())
