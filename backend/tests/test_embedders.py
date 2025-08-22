# tests/run_embedding_tests.py

from __future__ import annotations
from pathlib import Path
import sys

# --- Ensure project root is on sys.path so "embed" and "ingestion" import cleanly ---
ROOT = Path(__file__).resolve().parents[1]  # adjust if you place this file elsewhere
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Require these packages to be proper packages: embed/, ingestion/, ingestion/text/
# each should contain an __init__.py
from embed.text_embedder import embed as embed_text
from embed.image_embedder import embed as embed_image
from ingestion.text.extract_text import extract_text_metadata


def test_pdf_embedding(pdf_rel: str = "data/texts/Des_van_Jaarsveldt.pdf") -> None:
    pdf_path = (ROOT / pdf_rel).resolve()
    assert pdf_path.exists(), f"PDF not found: {pdf_path}"

    result = extract_text_metadata(
        file_path=str(pdf_path),
        user_id="123",
        max_chunk_size=800,
        chunk_overlap=20,
    )

    chunks = [item["chunk_text"] for item in result.get("text_chunks", [])]
    assert chunks, "No text chunks returned from extractor"

    embs = embed_text(chunks)
    print(f"[text] embeddings type={type(embs)} len={getattr(embs, '__len__', lambda: 'n/a')()}")
    if hasattr(embs, "shape"):
        print(f"[text] shape={embs.shape}")
    # show one vector (truncated) to prove it worked
    first = embs[0]
    try:
        print("[text] first vector (first 8 vals):", list(first)[:8])
    except Exception:
        print("[text] first embedding:", first)


def test_image_embedding(img_rel: str = "db/images/cat.jpg") -> None:
    img_path = (ROOT / img_rel).resolve()
    if not img_path.exists():
        print(f"[image] Skipping: file not found: {img_path}")
        return

    with open(img_path, "rb") as f:
        img_bytes = f.read()

    embs = embed_image([img_bytes])  # your embedder expects List[bytes]
    print(f"[image] embeddings type={type(embs)} len={getattr(embs, '__len__', lambda: 'n/a')()}")
    if hasattr(embs, "shape"):
        print(f"[image] shape={embs.shape}")
    first = embs[0]
    try:
        print("[image] first vector (first 8 vals):", list(first)[:8])
    except Exception:
        print("[image] first embedding:", first)


def main() -> None:
    test_pdf_embedding()
    # Uncomment if you want to run the image path too:
    # test_image_embedding()


if __name__ == "__main__":
    main()
