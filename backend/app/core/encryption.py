"""Fernet symmetric encryption helpers for sensitive data at rest."""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from app.core.logging import get_logger

logger = get_logger(__name__)

_ENCRYPTION_KEY_ENV = "GATEWAY_ENCRYPTION_KEY"


def _derive_key() -> bytes:
    """Derive a Fernet key from GATEWAY_ENCRYPTION_KEY env var or DATABASE_URL as fallback."""
    raw = os.environ.get(_ENCRYPTION_KEY_ENV, "")
    if not raw:
        raw = os.environ.get("DATABASE_URL", "mission-control-default-key")
        logger.warning("encryption.key.fallback using DATABASE_URL derivative; set %s", _ENCRYPTION_KEY_ENV)
    digest = hashlib.sha256(raw.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_derive_key())
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value, returning a base64-encoded ciphertext."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted value back to plaintext."""
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("encryption.decrypt.failed invalid token or key mismatch")
        raise
