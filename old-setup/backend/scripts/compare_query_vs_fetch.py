"""
Compare what Pinecone query returns vs fetch for the same vector.
This helps debug why formatted_text might be missing from search results.
"""

import os
import sys
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

def main():
    vector_id = "dee345d0-2a1f-4b63-ba71-d80c6c485a3a:1"
    namespace = "2ffa9aed-449c-4112-8d15-753a390f1f50"

    api_key = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE_KEY")
    pc = Pinecone(api_key=api_key)
    index_name = os.getenv("PINECONE_TEXT_INDEX_NAME")
    index = pc.Index(index_name)

    print("="*60)
    print("1. FETCH BY ID (direct lookup)")
    print("="*60)

    fetch_result = index.fetch(ids=[vector_id], namespace=namespace)
    fetch_vectors = fetch_result.vectors if hasattr(fetch_result, 'vectors') else fetch_result.get('vectors', {})
    fetch_data = fetch_vectors.get(vector_id)
    fetch_metadata = fetch_data.metadata if hasattr(fetch_data, 'metadata') else fetch_data.get('metadata', {})

    print(f"Metadata keys: {list(fetch_metadata.keys())}")
    print(f"Has formatted_text: {'formatted_text' in fetch_metadata}")
    if 'formatted_text' in fetch_metadata:
        print(f"formatted_text length: {len(fetch_metadata['formatted_text'])}")

    # Get the vector values for query
    vector_values = fetch_data.values if hasattr(fetch_data, 'values') else fetch_data.get('values', [])

    print("\n" + "="*60)
    print("2. QUERY WITH SAME VECTOR (similarity search)")
    print("="*60)

    query_result = index.query(
        vector=vector_values,
        top_k=1,
        namespace=namespace,
        include_metadata=True
    )

    query_matches = query_result.matches if hasattr(query_result, 'matches') else query_result.get('matches', [])

    if query_matches:
        match = query_matches[0]
        query_metadata = match.metadata if hasattr(match, 'metadata') else match.get('metadata', {})

        print(f"Metadata keys: {list(query_metadata.keys())}")
        print(f"Has formatted_text: {'formatted_text' in query_metadata}")
        if 'formatted_text' in query_metadata:
            print(f"formatted_text length: {len(query_metadata['formatted_text'])}")
        else:
            print("\n*** formatted_text is MISSING from query results! ***")

        # Compare keys
        fetch_keys = set(fetch_metadata.keys())
        query_keys = set(query_metadata.keys())
        missing_keys = fetch_keys - query_keys
        if missing_keys:
            print(f"\nKeys in FETCH but not in QUERY: {missing_keys}")
    else:
        print("No matches returned from query!")

if __name__ == "__main__":
    main()
