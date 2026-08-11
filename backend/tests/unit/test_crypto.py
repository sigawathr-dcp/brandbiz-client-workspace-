import base64
import secrets

import pytest
from cryptography.exceptions import InvalidTag

import app.crypto as crypto_module
from app.crypto import PURGED_PLACEHOLDER, decrypt, decrypt_message, encrypt

_KEY_V1 = base64.b64encode(secrets.token_bytes(32)).decode()
_KEY_V2 = base64.b64encode(secrets.token_bytes(32)).decode()


@pytest.fixture(autouse=True)
def reset_key_store(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", _KEY_V1)
    monkeypatch.setenv("ENCRYPTION_KEY_VERSION", "1")
    crypto_module._key_store = None
    yield
    crypto_module._key_store = None


def test_round_trip():
    plaintext = "Hello, World! สวัสดีชาวโลก"
    ct, nonce, tag, ver = encrypt(plaintext)
    assert decrypt(ct, nonce, tag, ver) == plaintext


def test_round_trip_empty_string():
    ct, nonce, tag, ver = encrypt("")
    assert decrypt(ct, nonce, tag, ver) == ""


def test_tampered_ciphertext_raises():
    ct, nonce, tag, ver = encrypt("sensitive data")
    tampered = bytes([ct[0] ^ 0xFF]) + ct[1:]
    with pytest.raises(InvalidTag):
        decrypt(tampered, nonce, tag, ver)


def test_tampered_tag_raises():
    ct, nonce, tag, ver = encrypt("sensitive data")
    tampered_tag = bytes([tag[0] ^ 0xFF]) + tag[1:]
    with pytest.raises(InvalidTag):
        decrypt(ct, nonce, tampered_tag, ver)


def test_different_nonces_produce_different_ciphertexts():
    ct1, nonce1, _, _ = encrypt("same message")
    ct2, nonce2, _, _ = encrypt("same message")
    assert nonce1 != nonce2
    assert ct1 != ct2


def test_key_rotation(monkeypatch):
    ct, nonce, tag, ver = encrypt("original message")
    assert ver == 1

    # Rotate to v2: archive old key as ENCRYPTION_KEY_1, set new key as primary
    monkeypatch.setenv("ENCRYPTION_KEY_1", _KEY_V1)
    monkeypatch.setenv("ENCRYPTION_KEY", _KEY_V2)
    monkeypatch.setenv("ENCRYPTION_KEY_VERSION", "2")
    crypto_module._key_store = None

    ct2, nonce2, tag2, ver2 = encrypt("new message")
    assert ver2 == 2

    # Old ciphertext still decryptable with v1 key
    assert decrypt(ct, nonce, tag, 1) == "original message"
    # New ciphertext decryptable with v2 key
    assert decrypt(ct2, nonce2, tag2, 2) == "new message"


def test_wrong_key_version_raises():
    ct, nonce, tag, _ = encrypt("data")
    with pytest.raises(KeyError):
        decrypt(ct, nonce, tag, 99)


def test_decrypt_message_round_trips_like_decrypt():
    ct, nonce, tag, ver = encrypt("still here")
    assert decrypt_message(ct, nonce, tag, ver) == "still here"


def test_decrypt_message_returns_placeholder_when_content_purged():
    """D14 nulls out content_ciphertext/nonce/tag on a Message row after 30
    days (app/services/retention.py) — decrypt_message must not raise."""
    assert decrypt_message(None, None, None, 1) == PURGED_PLACEHOLDER
