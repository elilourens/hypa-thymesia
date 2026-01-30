"""
Auto-tagging module for object detection in uploaded images.
Uses CLIP + OWL-ViT two-stage pipeline.
"""

from .tag_pipeline import (
    tag_image,
    get_tags_for_chunk,
    search_chunks_by_tags,
    get_popular_tags,
    delete_tags_for_chunk,
    delete_tags_for_document,
)

__all__ = [
    "tag_image",
    "get_tags_for_chunk",
    "search_chunks_by_tags",
    "get_popular_tags",
    "delete_tags_for_chunk",
    "delete_tags_for_document",
]
