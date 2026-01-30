from supabase import create_client, Client
from functools import lru_cache
from pinecone import Pinecone
from .config import get_settings

@lru_cache
def get_supabase() -> Client:
    s = get_settings()
    return create_client(s.SUPABASE_URL, s.SUPABASE_KEY)

@lru_cache
def get_pinecone() -> Pinecone:
    """Get a cached Pinecone client instance."""
    import os
    s = get_settings()
    # Try PINECONE_API_KEY first, fall back to PINECONE_KEY
    api_key = s.PINECONE_API_KEY or os.getenv("PINECONE_KEY")
    if not api_key:
        raise RuntimeError("Missing PINECONE_API_KEY or PINECONE_KEY environment variable")

    return Pinecone(
        api_key=api_key,
        environment=os.getenv("PINECONE_ENVIRONMENT")
    )
