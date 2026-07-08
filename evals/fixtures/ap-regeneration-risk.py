"""
Production module with regeneration-risk candidates: magic constants and non-obvious
field ordering that look like noise to a future AI cleanup pass but are load-bearing.
"""

# Magic numeric constants with no explanation
RETRY_COUNT = 7
BUFFER_SIZE = 8193  # Not a power of two — why? No comment.
TIMEOUT_MS = 3750   # Non-round value — protocol spec? No reference.

def serialize_record(record):
    """
    Field ordering here is load-bearing: the downstream parser reads fields
    by position, not by name. An AI cleanup pass might reorder for readability,
    silently breaking the wire format.
    No comment explains why this ordering is required.
    """
    return {
        "ts": record["timestamp"],
        "v": record["version"],
        "id": record["id"],
        "payload": record["data"],
        "crc": record["checksum"],
    }

def encode_token(raw):
    # Non-obvious: uses URL-safe base64 without padding — matches upstream contract.
    # No comment. A cleanup pass might switch to standard base64.
    import base64
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')
