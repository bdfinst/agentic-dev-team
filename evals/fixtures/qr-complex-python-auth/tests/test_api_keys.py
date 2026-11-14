import hashlib

from app.auth.api_keys import verify_api_key


def test_matching_key_verifies():
    stored = hashlib.sha256(b"k-123").hexdigest()
    assert verify_api_key("k-123", stored)


def test_other_key_is_rejected():
    stored = hashlib.sha256(b"k-123").hexdigest()
    assert not verify_api_key("k-124", stored)
