"""
LLM-based document tagging using Ollama/Mistral.

This module provides document classification and tagging using a local LLM
to generate semantic tags across multiple categories (document type, domain,
topic, content characteristics, intent, audience, time relevance, industry).
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import os

import httpx

from core.config import get_settings
from core.deps import get_supabase


logger = logging.getLogger(__name__)


@dataclass
class DocumentTag:
    """Represents a single document tag with metadata."""
    tag_name: str
    category: str
    confidence: float
    reasoning: Optional[str] = None


class DocumentTagger:
    """
    LLM-based document tagger using Ollama/Mistral.

    Uses a two-stage approach:
    1. Text analysis: LLM reads document preview and identifies relevant tags
    2. Category filtering: Ensures tags come from predefined label sets
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model_name: str = "mistral",
        max_preview_chars: int = 15000,
        max_tags_per_category: int = 5,
        use_smart_sampling: bool = True
    ):
        """
        Initialize the document tagger.

        Args:
            ollama_url: Base URL for Ollama API
            model_name: Name of the Ollama model to use
            max_preview_chars: Maximum characters to analyze from document
            max_tags_per_category: Maximum tags to extract per category
            use_smart_sampling: If True, sample from beginning, middle, and end
        """
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.max_preview_chars = max_preview_chars
        self.max_tags_per_category = max_tags_per_category
        self.use_smart_sampling = use_smart_sampling

        # Load document labels
        config_path = Path(__file__).parent.parent / "config" / "document_labels.json"
        with open(config_path, "r", encoding="utf-8") as f:
            self.label_config = json.load(f)

        self.categories = self.label_config["categories"]

        logger.info(
            f"Initialized DocumentTagger with model={model_name}, "
            f"max_chars={max_preview_chars}, smart_sampling={use_smart_sampling}, "
            f"{len(self.categories)} categories"
        )

    def _sample_document_text(self, text_content: str) -> str:
        """
        Sample text from the document using smart sampling strategy.

        If smart sampling is enabled and document is longer than max_preview_chars:
        - Takes 50% from beginning
        - Takes 25% from middle
        - Takes 25% from end

        Otherwise, just truncates to max_preview_chars.

        Args:
            text_content: Full document text

        Returns:
            Sampled text string
        """
        if len(text_content) <= self.max_preview_chars:
            return text_content

        if not self.use_smart_sampling:
            return text_content[:self.max_preview_chars]

        # Smart sampling: beginning (50%), middle (25%), end (25%)
        beginning_chars = int(self.max_preview_chars * 0.5)
        middle_chars = int(self.max_preview_chars * 0.25)
        end_chars = self.max_preview_chars - beginning_chars - middle_chars

        # Extract sections
        beginning = text_content[:beginning_chars]

        middle_start = (len(text_content) - middle_chars) // 2
        middle = text_content[middle_start:middle_start + middle_chars]

        end = text_content[-end_chars:]

        # Combine with markers
        sampled_text = f"{beginning}\n\n[... middle section ...]\n\n{middle}\n\n[... end section ...]\n\n{end}"

        logger.debug(
            f"Smart sampled document: {len(text_content)} chars -> {len(sampled_text)} chars "
            f"(beginning: {beginning_chars}, middle: {middle_chars}, end: {end_chars})"
        )

        return sampled_text

    def _build_tagging_prompt(self, text_preview: str, filename: str = "") -> str:
        """
        Build the LLM prompt for document tagging.

        Args:
            text_preview: Preview of document content
            filename: Original filename (for context)

        Returns:
            Formatted prompt string
        """
        # Build category descriptions
        category_descriptions = []
        for cat_key, cat_data in self.categories.items():
            label = cat_data.get("label", cat_key)
            desc = cat_data.get("description", "")
            tags = cat_data.get("tags", [])

            # Show ALL tags (no truncation)
            all_tags = ", ".join(tags)

            category_descriptions.append(
                f"- **{label}** ({cat_key}): {desc}\n  Available tags ({len(tags)}): {all_tags}"
            )

        categories_text = "\n".join(category_descriptions)

        content_note = ""
        if "[... middle section ...]" in text_preview or "[... end section ...]" in text_preview:
            content_note = "\nNOTE: This is a sampled representation showing the beginning, middle, and end sections of a longer document."

        prompt = f"""You are a document classification expert. Analyze the following document and assign relevant tags from predefined categories.

DOCUMENT FILENAME: {filename or "Unknown"}

DOCUMENT CONTENT:{content_note}
---
{text_preview}
---

AVAILABLE TAG CATEGORIES:
{categories_text}

TASK:
READ THE DOCUMENT CONTENT CAREFULLY, then assign up to {self.max_tags_per_category} relevant tags for each applicable category.

CRITICAL INSTRUCTIONS:
1. **READ THE ACTUAL CONTENT FIRST** - Base your tags on what the document actually discusses, not assumptions from the filename
2. Only use tags from the predefined lists shown above (no custom tags)
3. Choose tags that ACCURATELY reflect the document's actual subject matter and content
4. If the document is about biology, animals, or natural sciences, DO NOT use computer science/AI/ML tags
5. If the document is about computer science or programming, DO NOT use biology/natural science tags
6. Be selective - only assign tags you're highly confident about based on the content
7. Some categories may not apply - skip them entirely if no tags fit

OUTPUT FORMAT (JSON):
{{
  "document_type": [
    {{"tag": "research_paper", "confidence": 0.9}},
    {{"tag": "technical_documentation", "confidence": 0.7}}
  ],
  "subject_domain": [
    {{"tag": "machine_learning", "confidence": 0.95}}
  ],
  "content_characteristics": [
    {{"tag": "code_examples", "confidence": 0.85}},
    {{"tag": "technical", "confidence": 0.9}}
  ]
}}

Respond ONLY with valid JSON. Do not include any text before or after the JSON object."""

        return prompt

    async def _call_ollama(self, prompt: str) -> Dict[str, Any]:
        """
        Call Ollama API to generate document tags.

        Args:
            prompt: The tagging prompt

        Returns:
            Parsed JSON response from LLM

        Raises:
            Exception: If API call fails or response is invalid
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",  # Request JSON output
                    "options": {
                        "temperature": 0.3,  # Lower temperature for more consistent tagging
                        "top_p": 0.9,
                        "num_predict": 2000  # Limit output length
                    }
                }
            )

            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

            result = response.json()

            # Parse the generated response
            generated_text = result.get("response", "").strip()

            # Try to parse as JSON
            try:
                return json.loads(generated_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {generated_text[:500]}")
                raise Exception(f"Invalid JSON response from LLM: {e}")

    def _validate_and_normalize_tags(self, llm_output: Dict[str, Any]) -> List[DocumentTag]:
        """
        Validate LLM output and normalize tags.

        Args:
            llm_output: Raw output from LLM

        Returns:
            List of validated DocumentTag objects
        """
        validated_tags = []

        for category_key, tag_list in llm_output.items():
            # Check if category exists
            if category_key not in self.categories:
                logger.warning(f"Unknown category from LLM: {category_key}")
                continue

            # Get valid tags for this category
            valid_tags = set(self.categories[category_key].get("tags", []))

            # Process each tag
            if not isinstance(tag_list, list):
                logger.warning(f"Invalid tag list for category {category_key}: {tag_list}")
                continue

            for tag_entry in tag_list[:self.max_tags_per_category]:
                if not isinstance(tag_entry, dict):
                    continue

                tag_name = tag_entry.get("tag", "").lower().strip()
                confidence = tag_entry.get("confidence", 0.5)
                reasoning = tag_entry.get("reasoning", "")

                # Validate tag exists in predefined set
                if tag_name not in valid_tags:
                    logger.debug(f"Tag '{tag_name}' not in valid set for {category_key}")
                    continue

                # Ensure confidence is in valid range
                confidence = max(0.0, min(1.0, float(confidence)))

                validated_tags.append(DocumentTag(
                    tag_name=tag_name,
                    category=category_key,
                    confidence=confidence,
                    reasoning=reasoning
                ))

        return validated_tags

    async def tag_document(
        self,
        text_content: str,
        filename: str = "",
        min_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Tag a document using LLM analysis.

        Args:
            text_content: Full text content of the document
            filename: Original filename (for context)
            min_confidence: Minimum confidence threshold for tags

        Returns:
            Dictionary containing:
                - tags: List of DocumentTag objects
                - processing_time_ms: Time taken for tagging
                - preview_chars: Number of characters analyzed
                - total_chars: Total document size
        """
        start_time = time.time()

        # Sample text from document (smart sampling or simple truncation)
        text_preview = self._sample_document_text(text_content)
        preview_chars = len(text_preview)
        total_chars = len(text_content)

        logger.info(
            f"Tagging document '{filename}' "
            f"({total_chars} total chars, {preview_chars} analyzed chars)"
        )

        try:
            # Build prompt and call LLM
            prompt = self._build_tagging_prompt(text_preview, filename)
            llm_output = await self._call_ollama(prompt)

            # Validate and normalize tags
            all_tags = self._validate_and_normalize_tags(llm_output)

            # Filter by confidence
            filtered_tags = [
                tag for tag in all_tags
                if tag.confidence >= min_confidence
            ]

            processing_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Tagged document '{filename}': {len(filtered_tags)} tags "
                f"in {processing_time_ms:.0f}ms"
            )

            return {
                "tags": filtered_tags,
                "processing_time_ms": processing_time_ms,
                "preview_chars": preview_chars,
                "total_chars": total_chars,
                "total_tags": len(all_tags),
                "filtered_tags": len(filtered_tags)
            }

        except Exception as e:
            processing_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Error tagging document '{filename}': {e}", exc_info=True)

            return {
                "tags": [],
                "processing_time_ms": processing_time_ms,
                "preview_chars": preview_chars,
                "total_chars": total_chars,
                "error": str(e)
            }

    async def store_document_tags(
        self,
        doc_id: str,
        user_id: str,
        tags: List[DocumentTag]
    ) -> int:
        """
        Store document-level tags in the database.

        Args:
            doc_id: Document ID (tags are stored at document level, not chunk level)
            user_id: User ID
            tags: List of DocumentTag objects to store

        Returns:
            Number of tags stored
        """
        if not tags:
            logger.info(f"No tags to store for doc_id={doc_id}")
            return 0

        supabase = get_supabase()

        # Prepare tag records - document tags have chunk_id = NULL
        tag_records = []
        for tag in tags:
            tag_records.append({
                "chunk_id": None,  # NULL for document-level tags
                "doc_id": doc_id,
                "user_id": user_id,
                "tag_name": tag.tag_name,
                "confidence": tag.confidence,
                "verified": True,  # LLM tags are considered verified
                "bbox": None,  # No bounding boxes for document tags
                "tag_type": "document",  # Distinguish from image tags
                "category": tag.category,  # Store category for filtering
                "reasoning": tag.reasoning  # Store reasoning for debugging
            })

        try:
            result = supabase.table("app_image_tags").insert(tag_records).execute()

            stored_count = len(result.data) if result.data else 0
            logger.info(f"Stored {stored_count} document tags for doc_id={doc_id}")

            return stored_count

        except Exception as e:
            logger.error(f"Failed to store document tags: {e}", exc_info=True)
            return 0


# Singleton instance
_document_tagger: Optional[DocumentTagger] = None


def get_document_tagger() -> DocumentTagger:
    """
    Get or create the singleton DocumentTagger instance.

    Environment variables:
        OLLAMA_URL: Ollama API URL (default: http://localhost:11434)
        OLLAMA_MODEL: Model name (default: mistral)
        DOC_TAGGER_MAX_CHARS: Max characters to analyze (default: 15000)
        DOC_TAGGER_SMART_SAMPLING: Enable smart sampling (default: true)

    Returns:
        DocumentTagger instance
    """
    global _document_tagger

    if _document_tagger is None:
        # Get Ollama settings from environment
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "mistral")

        # Document tagger specific settings
        max_chars = int(os.getenv("DOC_TAGGER_MAX_CHARS", "15000"))
        smart_sampling = os.getenv("DOC_TAGGER_SMART_SAMPLING", "true").lower() == "true"

        _document_tagger = DocumentTagger(
            ollama_url=ollama_url,
            model_name=ollama_model,
            max_preview_chars=max_chars,
            use_smart_sampling=smart_sampling
        )

    return _document_tagger
