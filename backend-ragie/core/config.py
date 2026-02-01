"""Environment configuration for the Ragie backend."""

from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    app_env: str = "development"  # "development" or "production"

    # Supabase Configuration
    supabase_url: str
    supabase_key: str  # Service role key for admin operations
    supabase_anon_key: str  # Anon/publishable key for user operations with RLS

    # Ragie Configuration
    ragie_api_key: str
    ragie_webhook_secret: Optional[str] = None  # Optional: Ragie webhook secret (if not set, polling is used locally)

    # Stripe Configuration
    stripe_secret_key: str
    stripe_publishable_key: str
    stripe_webhook_secret: str
    stripe_pro_price_id: str
    stripe_max_price_id: str

    # JWT Configuration
    jwt_algorithm: str = "HS256"
    jwt_secret_key: str

    # CORS Configuration (optional - will auto-configure based on app_env if not provided)
    cors_origins: Optional[str] = None

    # Rate Limiting Configuration (optional - uses in-memory if not set)
    rate_limit_redis_url: Optional[str] = None

    # App Configuration
    api_prefix: str = "/api/v1"
    debug: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def set_cors_origins(cls, v: Optional[str], info) -> str:
        """Auto-configure CORS origins based on environment if not provided."""
        if v:
            return v

        app_env = info.data.get("app_env", "development")
        if app_env == "production":
            return "https://smartquery.app,https://www.smartquery.app"
        else:
            return "http://localhost:3000,http://127.0.0.1:3000"

    @field_validator("stripe_webhook_secret")
    @classmethod
    def validate_stripe_webhook_secret(cls, v: str) -> str:
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

    @field_validator("ragie_webhook_secret", mode="before")
    @classmethod
    def validate_ragie_webhook_secret(cls, v: Optional[str]) -> Optional[str]:
        """Validate that Ragie webhook secret is not empty if provided.

        For local development without webhooks, this can be None.
        For production with webhooks, this must be set.
        """
        if v and not v.strip():
            raise ValueError("RAGIE_WEBHOOK_SECRET must be non-empty if provided.")
        return v.strip() if v else None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
