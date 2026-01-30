"""Environment configuration for the Ragie backend."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Supabase Configuration
    supabase_url: str
    supabase_key: str  # Service role key for admin operations
    supabase_anon_key: str  # Anon/publishable key for user operations with RLS

    # Ragie Configuration
    ragie_api_key: str

    # Stripe Configuration
    stripe_secret_key: str
    stripe_publishable_key: str
    stripe_webhook_secret: str
    stripe_price_id: str

    # JWT Configuration
    jwt_algorithm: str = "HS256"
    jwt_secret_key: str

    # App Configuration
    api_prefix: str = "/api/v1"
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
