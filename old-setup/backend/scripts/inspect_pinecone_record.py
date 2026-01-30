"""
Script to inspect a specific Pinecone record's metadata.
Usage: python scripts/inspect_pinecone_record.py <vector_id> <namespace>
"""

import os
import sys
import json
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

def main():
    # Default test values - change these or pass as arguments
    vector_id = sys.argv[1] if len(sys.argv) > 1 else "dee345d0-2a1f-4b63-ba71-d80c6c485a3a:1"
    namespace = sys.argv[2] if len(sys.argv) > 2 else None

    if not namespace:
        print("Usage: python scripts/inspect_pinecone_record.py <vector_id> <namespace>")
        print("Example: python scripts/inspect_pinecone_record.py 'dee345d0-2a1f-4b63-ba71-d80c6c485a3a:1' 'your-user-id'")
        print("\nUsing default vector_id for demo...")

    # Initialize Pinecone
    api_key = os.getenv("PINECONE_API_KEY") or os.getenv("PINECONE_KEY")
    if not api_key:
        print("ERROR: PINECONE_API_KEY not set")
        sys.exit(1)

    pc = Pinecone(api_key=api_key)

    index_name = os.getenv("PINECONE_TEXT_INDEX_NAME")
    if not index_name:
        print("ERROR: PINECONE_TEXT_INDEX_NAME not set")
        sys.exit(1)

    print(f"Connecting to index: {index_name}")
    index = pc.Index(index_name)

    # Fetch the vector
    print(f"Fetching vector: {vector_id}")
    print(f"Namespace: {namespace or '(default)'}")

    result = index.fetch(ids=[vector_id], namespace=namespace)

    # Handle both dict and object responses (Pinecone SDK versions differ)
    if hasattr(result, 'vectors'):
        vectors = result.vectors
    else:
        vectors = result.get('vectors', {})

    if not vectors:
        print(f"\nNo vector found with ID: {vector_id}")
        print("Make sure the namespace is correct.")
        sys.exit(1)

    vector_data = vectors.get(vector_id) or vectors[vector_id] if vector_id in vectors else {}

    # Handle object or dict for vector_data
    if hasattr(vector_data, 'metadata'):
        metadata = vector_data.metadata or {}
    else:
        metadata = vector_data.get('metadata', {}) if isinstance(vector_data, dict) else {}

    print("\n" + "="*60)
    print("METADATA FIELDS:")
    print("="*60)

    for key, value in sorted(metadata.items()):
        if key in ('text', 'formatted_text', 'original_text'):
            # Truncate long text fields for display
            display_val = str(value)[:200] + "..." if len(str(value)) > 200 else value
            print(f"\n{key}:")
            print(f"  Length: {len(str(value))} chars")
            print(f"  Preview: {display_val}")
        else:
            print(f"\n{key}: {value}")

    print("\n" + "="*60)
    print("KEY CHECKS:")
    print("="*60)
    print(f"Has 'text' field: {'text' in metadata}")
    print(f"Has 'formatted_text' field: {'formatted_text' in metadata}")
    print(f"Has 'formatted_at' field: {'formatted_at' in metadata}")

    if 'text' in metadata:
        print(f"'text' length: {len(metadata['text'])} chars")
    if 'formatted_text' in metadata:
        print(f"'formatted_text' length: {len(metadata['formatted_text'])} chars")

    # Calculate total metadata size
    metadata_json = json.dumps(metadata)
    print(f"\nTotal metadata size: {len(metadata_json)} bytes")
    print(f"Pinecone limit: 40,960 bytes")

    if len(metadata_json) > 40960:
        print("WARNING: Metadata exceeds Pinecone limit!")

if __name__ == "__main__":
    main()
