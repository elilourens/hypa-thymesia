from db import ChromaDB

def main():
    db = ChromaDB(
        collection_metadata={"project": "alpha"},
    )

    db.add_texts(
        ids=["1", "2"],
        documents=[
            "Their favourite food is apples.",
            "They absolutely hate their job."
        ],
        metadatas=[
            {"person": "dave"},
            {"person": "joe"}
        ],
    )

    print("Chroma heartbeat:", db.client.heartbeat())
    print("Total items in collection:", db.count())
    #print("Query result:", db.query("jpmorgan"))
    db.delete_record(
        "1"
    )
    print("Total items in collection:", db.count())

if __name__ == "__main__":
    main()
