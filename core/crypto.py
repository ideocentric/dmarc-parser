"""
Symmetric encryption for sensitive values stored in the database (e.g. IMAP passwords).
Uses Fernet (AES-128-CBC + HMAC-SHA256).

Key management:
  - Set ENCRYPTION_KEY in .env (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  - The application will refuse to start if ENCRYPTION_KEY is not set.
"""
from cryptography.fernet import Fernet
from core.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    _fernet = Fernet(settings.encryption_key.strip().encode())
    return _fernet


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except Exception as exc:
        raise ValueError("Failed to decrypt credential — wrong key or corrupted data") from exc