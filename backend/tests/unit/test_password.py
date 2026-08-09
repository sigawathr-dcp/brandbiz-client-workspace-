"""Unit tests for app/services/password.py (mock username/password login)."""
from app.services.password import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    h = hash_password("Passw0rd!")
    assert verify_password("Passw0rd!", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("Passw0rd!")
    assert verify_password("wrong", h) is False


def test_hash_is_not_plaintext():
    h = hash_password("Passw0rd!")
    assert h != "Passw0rd!"


def test_verify_rejects_malformed_hash():
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False
