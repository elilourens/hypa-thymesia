from embed.text_embedder import embed as embed_text
from embed.image_embedder import embed as embed_image
from backend.ingestion.text.extract_text import extract_pdf_text_metadata
from typing import List


def test_pdf_embedding():
    result = extract_pdf_text_metadata(
        "db/texts/Des_van_Jaarsveldt.pdf",
        "123",
        800
    )
    # extract only the raw text strings
    chunks = [item["chunk_text"] for item in result["text_chunks"]]

    embeddings = embed_text(chunks)
    print(embeddings)

def test_image_embedding():
    with open("db/images/cat.jpg", "rb") as f:
        img_bytes = f.read()

    # Now call your embedder with a list of bytes
    embs = embed_image([img_bytes])

    print(embs)

def main():
    test_pdf_embedding()
    #test_image_embedding()

if __name__ == "__main__":
    main()