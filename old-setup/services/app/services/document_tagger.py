"""
LLM-based document tagging service using Ollama.

This module provides document classification and tagging using Ollama LLM
to generate semantic tags across multiple categories.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import ollama

from app.core.config import get_settings

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
    LLM-based document tagger using Ollama.

    Uses a two-stage approach:
    1. Text analysis: LLM reads document preview and identifies relevant tags
    2. Category filtering: Ensures tags come from predefined label sets
    """

    def __init__(
        self,
        model: str = None,
        base_url: str = None,
        max_preview_chars: int = 15000,
        max_tags_per_category: int = 5,
        use_smart_sampling: bool = True
    ):
        """
        Initialize the document tagger.

        Args:
            model: Ollama model name
            base_url: Ollama server URL
            max_preview_chars: Maximum characters to analyze from document
            max_tags_per_category: Maximum tags to extract per category
            use_smart_sampling: If True, sample from beginning, middle, and end
        """
        settings = get_settings()
        self.model = model or settings.OLLAMA_MODEL
        self.base_url = base_url or settings.OLLAMA_URL
        self.max_preview_chars = max_preview_chars
        self.max_tags_per_category = max_tags_per_category
        self.use_smart_sampling = use_smart_sampling
        self.client = ollama.Client(host=self.base_url)

        # Load document labels
        config_path = Path(__file__).parent.parent / "config" / "document_labels.json"
        with open(config_path, "r", encoding="utf-8") as f:
            self.label_config = json.load(f)

        self.categories = self.label_config["categories"]

        logger.info(
            f"Initialized DocumentTagger with model={self.model}, "
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
            f"Smart sampled document: {len(text_content)} chars -> {len(sampled_text)} chars"
        )

        return sampled_text

    def _build_tagging_prompt(self, text_preview: str, filename: str = "") -> str:
        """Build the LLM prompt for document tagging."""
        # Build category descriptions
        category_descriptions = []
        for cat_key, cat_data in self.categories.items():
            label = cat_data.get("label", cat_key)
            desc = cat_data.get("description", "")
            tags = cat_data.get("tags", [])
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

    def _validate_and_normalize_tags(self, llm_output: Dict[str, Any]) -> List[DocumentTag]:
        """Validate LLM output and normalize tags."""
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

    def tag_document(
        self,
        text_content: str,
        filename: str = "",
        min_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Tag a document using LLM analysis (synchronous).

        Args:
            text_content: Full text content of the document
            filename: Original filename (for context)
            min_confidence: Minimum confidence threshold for tags

        Returns:
            Dictionary containing tags and metadata
        """
        start_time = time.time()

        # Sample text from document
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

            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                format="json",
                options={
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_predict": 2000
                }
            )

            # Parse the generated response
            generated_text = response["message"]["content"].strip()

            try:
                llm_output = json.loads(generated_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {generated_text[:500]}")
                raise Exception(f"Invalid JSON response from LLM: {e}")

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


# Singleton instance
_document_tagger: Optional[DocumentTagger] = None


def get_document_tagger() -> DocumentTagger:
    """Get or create the singleton DocumentTagger instance."""
    global _document_tagger

    if _document_tagger is None:
        _document_tagger = DocumentTagger()

    return _document_tagger
