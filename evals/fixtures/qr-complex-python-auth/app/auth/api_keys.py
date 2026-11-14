import hashlib
import hmac


def verify_api_key(presented: str, stored_sha256_hex: str) -> bool:
    """True when the presented key hashes to the stored digest."""
    digest = hashlib.sha256(presented.encode()).hexdigest()
    return hmac.compare_digest(digest, stored_sha256_hex)
