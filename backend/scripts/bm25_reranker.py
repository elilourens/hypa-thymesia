# scripts/bm25_reranker.py

from typing import List
from schemas.ingest import QueryMatch

try:
    from rank_bm25 import BM25Okapi
    from nltk.tokenize import word_tokenize
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False


def rerank_with_bm25(
    query_text: str,
    matches: List[QueryMatch],
    bm25_weight: float = 0.3,
) -> List[QueryMatch]:
    """
    Re-rank Pinecone matches by blending embedding similarity with BM25 scores.

    Args:
        query_text (str): The query string provided by the user.
        matches (List[QueryMatch]): List of Pinecone matches (already scored by embeddings).
        bm25_weight (float): Blend factor between 0 and 1.
                             0 = embeddings only, 1 = BM25 only.

    Returns:
        List[QueryMatch]: Matches re-scored and sorted.
    """
    if not query_text or not matches or not _BM25_AVAILABLE:
        # BM25 not available or query empty → return matches unchanged
        return matches

    try:
        query_tokens = word_tokenize(query_text.lower())
        corpus = [word_tokenize(m.metadata.get("text", "").lower()) for m in matches]

        bm25 = BM25Okapi(corpus)
        bm25_scores = bm25.get_scores(query_tokens)

        # Normalize BM25 scores into [0,1]
        if bm25_scores.max() > 0:
            bm25_scores = bm25_scores / bm25_scores.max()

        # Blend scores
        for i, m in enumerate(matches):
            dense_score = m.score or 0.0
            bm25_score = float(bm25_scores[i])
            blended = (1 - bm25_weight) * dense_score + bm25_weight * bm25_score
            m.score = blended
            """
            print(
                f"[BM25] Dense={dense_score:.4f}, "
                f"BM25={bm25_score:.4f}, "
                f"Blended={blended:.4f}, "
                f"Text={m.metadata.get('text', '')[:50]}"
            )
            """
        # Sort by blended score
        matches.sort(key=lambda x: x.score, reverse=True)

    except Exception as e:
        print(f"[BM25] Failed to rerank: {e}")

    return matches
