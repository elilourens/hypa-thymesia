"""
Configuration settings for the Formatting Microservice.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Microservice configuration settings."""

    # Ollama settings
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral"
    OLLAMA_TIMEOUT: int = 30
    OLLAMA_NUM_PARALLEL: int = 6

    # Service settings
    SERVICE_NAME: str = "formatting-microservice"
    SERVICE_PORT: int = 8002
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
