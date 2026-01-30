from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str  # service role
    PINECONE_API_KEY: str | None = None  # Optional, will try PINECONE_KEY if not set
    EMBED_MODEL: str = "clip-ViT-B-32"
    EMBED_DIM: int = 512
    API_PREFIX: str = "/api/v1"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def pinecone_key(self) -> str:
        """Get Pinecone API key from either PINECONE_API_KEY or PINECONE_KEY."""
        import os
        return self.PINECONE_API_KEY or os.getenv("PINECONE_KEY") or ""

@lru_cache
def get_settings() -> Settings:
    return Settings()  # reads env_file + os.environ
