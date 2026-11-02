"""
Fernet symmetric encryption for sensitive stored data (Gmail tokens, etc.).
"""

import os
import base64
from cryptography.fernet import Fernet


def get_fernet() -> Fernet:
    """Return a Fernet instance using the key from environment."""
    key = os.getenv("FERNET_KEY", "")
    if not key:
        # Generate a temporary key for development (not persistent across restarts)
        key = Fernet.generate_key().decode()
        os.environ["FERNET_KEY"] = key
    # Accept both bytes and str keys
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_data(plaintext: str) -> str:
    """Encrypt a string and return the ciphertext as a string."""
    if not plaintext:
        return ""
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_data(ciphertext: str) -> str:
    """Decrypt a previously encrypted string."""
    if not ciphertext:
        return ""
    f = get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
