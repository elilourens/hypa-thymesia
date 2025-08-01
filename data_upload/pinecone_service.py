import pinecone
from dotenv import load_dotenv
import os
from typing import List, Dict, Any

load_dotenv()

# Initialize Pinecone
pinecone.init(
    api_key=os.getenv("PINECONE_API_KEY"),
    environment=os.getenv("PINECONE_ENVIRONMENT")
)


index_name = os.getenv("PINECONE_INDEX_NAME")
index = pinecone.Index(index_name)


MAX_BATCH = "100"


def upload_to_pinecone(
    file_type: str,
    user_id: str,
    record_id: str,
    vectors: List[List[float]],
    upload_date: str,
) -> bool:
    """
    Upserts vectors into Pinecone with metadata.
    If you have fewer than MAX_BATCH items, they'll all go in one call;
    otherwise we split into chunks of MAX_BATCH.
    """
    try:
        # Build the (id, vector, metadata) tuples
        items = []
        for idx, vec in enumerate(vectors):
            item_id = f"{user_id}:{record_id}:{idx}"
            metadata: Dict[str, Any] = {
                "file_type":   file_type,
                "user_id":     user_id,
                "record_id":   record_id,
                "upload_date": upload_date,
                "chunk_index": idx,
            }
            items.append((item_id, vec, metadata))

        
        batch_size = min(len(items), MAX_BATCH)

        
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            index.upsert(vectors=batch)

        return True

    except Exception as e:
        # Optionally log e here
        return False
