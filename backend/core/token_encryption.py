# core/token_encryption.py

import os
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Global cipher instance (initialized once)
_cipher: Optional[Fernet] = None


def _get_cipher() -> Fernet:
    """
    Get or initialize the Fernet cipher for token encryption.
    Uses OAUTH_ENCRYPTION_KEY from environment.
    """
    global _cipher
    if _cipher is None:
        key = os.getenv("OAUTH_ENCRYPTION_KEY")
        if not key:
            raise ValueError(
                "OAUTH_ENCRYPTION_KEY environment variable must be set. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        try:
            _cipher = Fernet(key.encode())
        except Exception as e:
            raise ValueError(f"Invalid OAUTH_ENCRYPTION_KEY format: {e}")
    return _cipher


def encrypt_token(token: str) -> str:
    """
    Encrypt an OAuth token before storing in database.

    Args:
        token: Plaintext OAuth token (access_token or refresh_token)

    Returns:
        Encrypted token as base64 string

    Raises:
        ValueError: If encryption key is not configured
        Exception: If encryption fails
    """
    if not token:
        return ""

    try:
        cipher = _get_cipher()
        encrypted = cipher.encrypt(token.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Failed to encrypt token: {e}")
        raise Exception(f"Token encryption failed: {e}")


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt an OAuth token after retrieving from database.

    Args:
        encrypted_token: Encrypted token as base64 string

    Returns:
        Plaintext OAuth token

    Raises:
        ValueError: If encryption key is not configured
        InvalidToken: If token cannot be decrypted (wrong key or corrupted)
        Exception: If decryption fails
    """
    if not encrypted_token:
        return ""

    try:
        cipher = _get_cipher()
        decrypted = cipher.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except InvalidToken:
        logger.error("Failed to decrypt token: Invalid token or wrong encryption key")
        raise InvalidToken("Cannot decrypt token - may have been encrypted with different key")
    except Exception as e:
        logger.error(f"Failed to decrypt token: {e}")
        raise Exception(f"Token decryption failed: {e}")


def is_token_encrypted(token: str) -> bool:
    """
    Check if a token appears to be encrypted (for migration purposes).

    Encrypted tokens are base64-encoded and start with 'gAAAAA' (Fernet format).
    This is a heuristic check and may have false positives/negatives.

    Args:
        token: Token string to check

    Returns:
        True if token appears to be encrypted, False otherwise
    """
    if not token:
        return False

    # Fernet tokens are base64 and typically start with 'gAAAAA'
    # This is a heuristic - not 100% reliable but good enough for migration
    return token.startswith("gAAAAA") and len(token) > 50


def generate_key() -> str:
    """
    Generate a new encryption key for OAUTH_ENCRYPTION_KEY.

    Returns:
        Base64-encoded encryption key
    """
    return Fernet.generate_key().decode()


if __name__ == "__main__":
    # Utility to generate a new encryption key
    print("Generated encryption key for OAUTH_ENCRYPTION_KEY:")
    print(generate_key())
    print("\nAdd this to your .env file:")
    print(f"OAUTH_ENCRYPTION_KEY={generate_key()}")
