"""Token encryption utilities for storing OAuth credentials."""

from cryptography.fernet import Fernet
from core.config import settings


class TokenEncryption:
    """Encrypt/decrypt sensitive tokens using Fernet symmetric encryption."""

    def __init__(self):
        # Use encryption key from environment
        self.cipher = Fernet(settings.token_encryption_key.encode())

    def encrypt(self, token: str) -> str:
        """Encrypt a token string."""
        if not token:
            raise ValueError("Token cannot be empty")
        return self.cipher.encrypt(token.encode()).decode()

    def decrypt(self, encrypted_token: str) -> str:
        """Decrypt an encrypted token."""
        if not encrypted_token:
            raise ValueError("Encrypted token cannot be empty")
        return self.cipher.decrypt(encrypted_token.encode()).decode()


# Global instance
token_encryptor = TokenEncryption()
