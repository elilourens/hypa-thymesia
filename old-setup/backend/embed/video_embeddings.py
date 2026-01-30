"""
Video embedding utilities using CLIP and sentence-transformers.
These are used for querying video content (frames and transcripts).
"""
import torch
import numpy as np
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from sentence_transformers import SentenceTransformer


class CLIPEmbedder:
    """CLIP embedder for video frame queries using text."""

    _instance = None

    def __new__(cls):
        """Singleton pattern to avoid loading model multiple times."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name="openai/clip-vit-base-patch32"):
        """Initialize CLIP model (only once due to singleton)."""
        if self._initialized:
            return

        print("Loading CLIP model for video queries...")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self._initialized = True
        print(f"CLIP model loaded on {self.device}")

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for text query.

        Args:
            text: Query text

        Returns:
            Normalized embedding as numpy array
        """
        inputs = self.processor(text=[text], return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            features = self.model.get_text_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.cpu().numpy().flatten()


class TranscriptEmbedder:
    """Sentence transformer embedder for video transcript queries."""

    _instance = None

    def __new__(cls):
        """Singleton pattern to avoid loading model multiple times."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """Initialize transcript embedder (only once due to singleton)."""
        if self._initialized:
            return

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading transcript embedder for video queries on {self.device}...")
        self.model = SentenceTransformer(model_name, device=self.device)
        self._initialized = True
        print(f"Transcript embedder loaded: {model_name}")

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate embedding for transcript query.

        Args:
            text: Query text

        Returns:
            Normalized embedding as numpy array
        """
        embedding = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return embedding.flatten()


# Global instances (lazy loaded)
_clip_embedder = None
_transcript_embedder = None


def get_clip_embedder() -> CLIPEmbedder:
    """Get or initialize CLIP embedder singleton."""
    global _clip_embedder
    if _clip_embedder is None:
        _clip_embedder = CLIPEmbedder()
    return _clip_embedder


def get_transcript_embedder() -> TranscriptEmbedder:
    """Get or initialize transcript embedder singleton."""
    global _transcript_embedder
    if _transcript_embedder is None:
        _transcript_embedder = TranscriptEmbedder()
    return _transcript_embedder
