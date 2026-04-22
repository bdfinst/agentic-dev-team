"""Crypto helpers — SEEDS scan-07 findings."""
from __future__ import annotations

import hashlib
import httpx
from Crypto.Cipher import AES


def integrity_hash(data: bytes) -> str:
    # SEED: F016 (scan-07 crypto) — MD5 used for integrity
    return hashlib.md5(data).hexdigest()


def fetch_remote_signature(url: str) -> bytes:
    # SEED: F017 (scan-07 crypto) — verify=False disables TLS validation
    resp = httpx.get(url, verify=False)
    return resp.content


def encrypt_payload(key: bytes, data: bytes) -> bytes:
    # SEED: F018 (scan-07 crypto) — AES-CBC without HMAC (non-AEAD cipher)
    cipher = AES.new(key, AES.MODE_CBC)
    return cipher.encrypt(data)
