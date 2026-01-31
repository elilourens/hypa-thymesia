"""Environment configuration for the Ragie backend."""

from pydantic import field_validator
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
    stripe_pro_price_id: str
    stripe_max_price_id: str

    # JWT Configuration
    jwt_algorithm: str = "HS256"
    jwt_secret_key: str

    # App Configuration
    api_prefix: str = "/api/v1"
    debug: bool = False

    @field_validator("stripe_webhook_secret")
    @classmethod
    def validate_webhook_secret(cls, v: str) -> str:
        """Validate that Stripe webhook secret is not empty or whitespace-only.

        SECURITY: This is critical for webhook signature verification.
        Without this secret, the application cannot validate webhook authenticity.
        """
        if not v or not v.strip():
            raise ValueError(
                "STRIPE_WEBHOOK_SECRET must be set and non-empty. "
                "Webhook signature verification requires this secret."
            )
        return v.strip()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
