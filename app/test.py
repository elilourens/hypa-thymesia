from db import ChromaDB

def main():
    db = ChromaDB(
        collection_metadata={"project": "alpha"},
    )

    db.add_texts(
        ids=["doc1", "doc2"],
        documents=[
            "Here’s the first text.",
            "And here’s the second."
        ],
        metadatas=[
            {"source": "notion"},
            {"source": "google-docs"}
        ],
    )

    print("Chroma heartbeat:", db.client.heartbeat())
    print("Total items in collection:", db.count())
    print("Query result:", db.query("return the second bit of text"))

if __name__ == "__main__":
    main()
