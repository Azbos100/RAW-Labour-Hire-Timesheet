"""
PII encryption-at-rest helpers (TFN, bank details).

Uses Fernet (AES-128-CBC + HMAC) with a key derived from the PII_ENCRYPTION_KEY
environment variable. The helpers are:

- null/empty safe   -> None / "" pass straight through
- idempotent        -> encrypting an already-encrypted value is a no-op
- backward tolerant -> decrypting a legacy plaintext value returns it unchanged

If PII_ENCRYPTION_KEY is not set the helpers become no-ops (values are stored as
plaintext) so the app still boots; set the key in production to enable encryption.
"""

import os
import base64
import hashlib
from typing import Optional

_fernet = None
_initialised = False


def _get_fernet():
    """Lazily build a Fernet instance from PII_ENCRYPTION_KEY (cached)."""
    global _fernet, _initialised
    if _initialised:
        return _fernet
    _initialised = True
    secret = os.getenv("PII_ENCRYPTION_KEY")
    if not secret:
        _fernet = None
        return None
    try:
        from cryptography.fernet import Fernet
        # Derive a valid 32-byte urlsafe-base64 Fernet key from any passphrase.
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        _fernet = Fernet(key)
    except Exception:
        _fernet = None
    return _fernet


def is_configured() -> bool:
    return _get_fernet() is not None


def encrypt_pii(value: Optional[str]) -> Optional[str]:
    """Encrypt a value for storage. No-op if not configured, empty, or already encrypted."""
    if value is None or value == "":
        return value
    f = _get_fernet()
    if f is None:
        return value
    # Already encrypted? (idempotent) — try to decrypt; if it works, leave as-is.
    from cryptography.fernet import InvalidToken
    try:
        f.decrypt(value.encode())
        return value
    except (InvalidToken, Exception):
        pass
    return f.encrypt(value.encode()).decode()


def decrypt_pii(value: Optional[str]) -> Optional[str]:
    """Decrypt a stored value. Returns legacy plaintext unchanged on failure."""
    if value is None or value == "":
        return value
    f = _get_fernet()
    if f is None:
        return value
    from cryptography.fernet import InvalidToken
    try:
        return f.decrypt(value.encode()).decode()
    except (InvalidToken, Exception):
        return value  # legacy plaintext (pre-migration) or unreadable
