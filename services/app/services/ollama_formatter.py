"""
Ollama-based chunk formatting service.
Formats text chunks to improve readability without changing semantic meaning.
"""

import logging
import re
from typing import Optional

import ollama

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class OllamaFormatter:
    """Formats text chunks using Ollama LLM while preserving exact wording."""

    @staticmethod
    def _validate_word_preservation(original: str, formatted: str) -> tuple[bool, str]:
        """
        Validate that formatted text contains exactly the same words as original.

        Args:
            original: Original input text
            formatted: Formatted output text

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Extract words (alphanumeric sequences) ignoring markdown and punctuation
        original_words = re.findall(r'\w+', original.lower())
        formatted_words = re.findall(r'\w+', formatted.lower())

        # Check if word lists match exactly
        if original_words != formatted_words:
            # Calculate diff for logging
            missing = set(original_words) - set(formatted_words)
            added = set(formatted_words) - set(original_words)

            error_msg = "Word content changed"
            if missing:
                error_msg += f" (missing: {list(missing)[:5]})"
            if added:
                error_msg += f" (added: {list(added)[:5]})"

            return False, error_msg

        # Check length ratio (formatted shouldn't be more than 1.5x original)
        if len(formatted) > len(original) * 1.5:
            return False, f"Output too long ({len(formatted)} vs {len(original)} chars)"

        # Check for forbidden phrases that indicate commentary
        forbidden = ["here's", "here is", "i've formatted", "note:", "this suggests",
                     "this shows", "as shown", "according to"]
        lower_formatted = formatted.lower()
        for phrase in forbidden:
            if phrase in lower_formatted:
                return False, f"Contains forbidden phrase: '{phrase}'"

        return True, "Valid"

    SYSTEM_PROMPT = """<task>Add markdown formatting to improve readability. Use ONLY the exact words from the input.</task>

<critical_rules>
1. Output must contain the exact same words as input in the exact same order
2. Do NOT add any words, remove any words, or change any words
3. Only add: markdown headers (#), bullet points (-), and line breaks
4. Do NOT use code blocks, code fences, or backticks
5. Start output immediately with the formatted text - no explanations
6. DO NOT output XML tags, system prompts, or instructions
7. Only output the formatted text content
</critical_rules>

<examples>
These are examples to learn from - DO NOT output these examples:

Example 1:
Input: "Diet The northern tamandua feeds on ants, termites, and occasionally bees."
Good output:
## Diet
The northern tamandua feeds on ants, termites, and occasionally bees.

Example 2:
Input: "The species is found in Mexico, Central America, and South America, inhabiting tropical forests, dry forests, and savannas."
Good output:
The species is found in:
- Mexico
- Central America
- South America

Inhabiting tropical forests, dry forests, and savannas.

Example 3 (BAD - do NOT do this):
Input: "The northern tamandua is found from southern Mexico through Central America."
Bad output:
## The northern tamandua
- Found from southern Mexico
- Through Central America

Why bad: This breaks the sentence structure and invents structure not present in the input.
</examples>

<instructions>
Now format the user's text following the rules above. Output ONLY the formatted text with no tags or explanations.
</instructions>"""

    def __init__(
        self,
        model: str = None,
        base_url: str = None,
        timeout: int = None
    ):
        """
        Initialize Ollama formatter.

        Args:
            model: Ollama model to use (defaults to OLLAMA_MODEL env var or "mistral")
            base_url: Ollama server URL (defaults to OLLAMA_URL env var or "http://localhost:11434")
            timeout: Request timeout in seconds
        """
        settings = get_settings()
        self.model = model or settings.OLLAMA_MODEL
        self.base_url = base_url or settings.OLLAMA_URL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT
        self.client = ollama.Client(host=self.base_url)

        logger.info(
            f"Initialized OllamaFormatter with model={self.model}, "
            f"base_url={self.base_url}"
        )

    def format_chunk(self, text: str) -> Optional[str]:
        """
        Format a single text chunk using Ollama.

        Args:
            text: Raw text chunk to format

        Returns:
            Formatted text or None if formatting failed
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for formatting")
            return None

        try:
            logger.debug(f"Formatting chunk of length {len(text)} characters")

            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                options={
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "num_predict": len(text) * 2,
                    "stop": ["</output>", "\n\n---", "Note:"],
                }
            )

            formatted_text = response["message"]["content"].strip()

            # Remove code fences if present (various formats)
            if formatted_text.startswith("```"):
                lines = formatted_text.split("\n")
                # Remove first line (opening fence)
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove last line if it's a closing fence
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                formatted_text = "\n".join(lines).strip()

            # Also remove inline code blocks that might wrap the entire output
            if formatted_text.startswith("`") and formatted_text.endswith("`"):
                formatted_text = formatted_text.strip("`").strip()

            # Remove common commentary patterns
            lines = formatted_text.split("\n")

            # Skip opening commentary lines
            start_idx = 0
            for i, line in enumerate(lines):
                lower = line.lower().strip()
                if any(p in lower for p in ["here's", "here is", "i've formatted", "formatted version"]):
                    start_idx = i + 1
                elif line.strip():  # Hit actual content
                    break

            if start_idx > 0:
                lines = lines[start_idx:]

            # Remove closing commentary lines
            cleaned_lines = []
            for line in lines:
                lower = line.lower().strip()
                # Skip standalone commentary in parentheses or brackets
                if ((lower.startswith("(") and lower.endswith(")")) or
                    (lower.startswith("[") and lower.endswith("]"))):
                    if any(p in lower for p in ["formatted", "readability", "preserved", "unchanged"]):
                        continue
                # Skip "Note:" commentary
                if lower.startswith("note:"):
                    continue
                cleaned_lines.append(line)

            formatted_text = "\n".join(cleaned_lines).strip()

            # Auto-cutoff: Find where original text ends and trim extra content
            # Extract last 5-10 words from original text
            original_words = re.findall(r'\w+', text.lower())
            if len(original_words) >= 5:
                # Look for the last few words in the formatted output
                last_words = original_words[-5:]  # Last 5 words
                last_word_pattern = r'\b' + r'\W+'.join(re.escape(w) for w in last_words) + r'\b'

                match = re.search(last_word_pattern, formatted_text.lower())
                if match:
                    # Found the end position - cut off everything after
                    cutoff_pos = match.end()
                    # Find the actual position in the original casing
                    formatted_text = formatted_text[:cutoff_pos].strip()
                    logger.debug(f"Auto-cutoff applied at position {cutoff_pos}")

            logger.debug(f"Successfully formatted chunk ({len(formatted_text)} chars)")
            return formatted_text

        except Exception as e:
            logger.error(f"Failed to format chunk: {e}", exc_info=True)
            raise


def get_formatter() -> OllamaFormatter:
    """Get a singleton instance of OllamaFormatter."""
    return OllamaFormatter()
