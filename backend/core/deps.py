from supabase import create_client, Client
from functools import lru_cache
from .config import get_settings

@lru_cache
def get_supabase() -> Client:
    s = get_settings()
    return create_client(s.SUPABASE_URL, s.SUPABASE_KEY)
