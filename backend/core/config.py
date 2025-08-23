from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_KEY: str  # service role
    EMBED_MODEL: str = "clip-ViT-B-32"
    EMBED_DIM: int = 512
    API_PREFIX: str = "/api/v1"

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache
def get_settings() -> Settings:
    return Settings()  # reads env_file + os.environ
