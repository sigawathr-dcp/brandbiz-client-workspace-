import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12  # 96-bit nonce — GCM recommended size
_TAG_BYTES = 16    # 128-bit authentication tag

_key: bytes | None = None


def _get_key() -> bytes:
    global _key
    if _key is None:
        raw = os.environ.get("ENCRYPTION_KEY", "")
        if not raw:
            raise RuntimeError("ENCRYPTION_KEY environment variable is not set")
        _key = base64.b64decode(raw)
    return _key


def encrypt(plaintext: str) -> tuple[bytes, bytes, bytes, int]:
    """Encrypt with AES-256-GCM. Returns (ciphertext, nonce, tag, key_version=1)."""
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ct_tag = AESGCM(_get_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return ct_tag[:-_TAG_BYTES], nonce, ct_tag[-_TAG_BYTES:], 1


def decrypt(ciphertext: bytes, nonce: bytes, tag: bytes, key_version: int) -> str:
    """Decrypt AES-256-GCM ciphertext.

    Raises cryptography.exceptions.InvalidTag if tampered.
    key_version is accepted for API compatibility but ignored (single-key demo).
    """
    plaintext_bytes = AESGCM(_get_key()).decrypt(nonce, ciphertext + tag, None)
    return plaintext_bytes.decode("utf-8")
