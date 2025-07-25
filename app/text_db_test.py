# text_db_test.py

from text_db import text_ChromaDB
from image_db import image_chroma
from pathlib import Path

def main():
    # — Text collection demo —
    text_db = text_ChromaDB(
        collection_metadata={"project": "alpha"},
    )

    text_db.add_texts(
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

    print("Chroma heartbeat:", text_db.client.heartbeat())
    print("Total items in collection:", text_db.count())

    text_db.delete_record("1")
    print("Total items in collection:", text_db.count())
    text_db.wipe()
    print("Total items in collection after wipe:", text_db.count())
    print("Chroma heartbeat:", text_db.client.heartbeat())
    print("Image DB:")

    # — Image collection demo —
    image_db = image_chroma(
        host="localhost",
        port=8001,
        ssl=False,
        tenant="default_tenant",
        database="default_database",
        collection_name="my_images",
        collection_metadata={"project": "hypa-thymesia"},
    )

    BASE = Path(__file__).parent
    images_dir = BASE / "images"

    #count = image_db.add_folder(str(images_dir), batch_size=16)
    #print(f"✅ Ingested {count} images into collection '{image_db.collection.name}'")
    print("Total records in image DB:", image_db.count())

    #Example query (uncomment to test):
    res = image_db.query_by_text("hound", n_results=1)
    print(res["uris"][0]) 

if __name__ == "__main__":
    main()
