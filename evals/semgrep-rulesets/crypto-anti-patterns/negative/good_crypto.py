"""Negative fixture — should produce zero matches."""
import hashlib
import requests
from Crypto.Cipher import AES


def fetch_trusted(url):
    # verify=True (default) — TLS enforced
    return requests.get(url)


def hash_for_integrity(data):
    # SHA-256 — secure
    return hashlib.sha256(data).hexdigest()


def encrypt_good_gcm(key, nonce, data):
    # AES-GCM — AEAD cipher
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(data)
    return ciphertext, tag
