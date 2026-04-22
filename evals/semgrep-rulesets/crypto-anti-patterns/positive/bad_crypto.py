"""Positive fixture for crypto-anti-patterns rules."""
import hashlib
import requests
from Crypto.Cipher import AES, DES


def fetch_untrusted(url):
    # Expected match: crypto-anti-patterns.python-verify-false (ERROR)
    return requests.get(url, verify=False)


def hash_for_integrity(data):
    # Expected match: crypto-anti-patterns.md5-for-integrity (WARNING)
    return hashlib.md5(data).hexdigest()


def encrypt_bad_cbc(key, iv, data):
    # Expected match: crypto-anti-patterns.non-aead-cipher (ERROR)
    cipher = AES.new(key, AES.MODE_CBC)
    return cipher.encrypt(data)


def encrypt_bad_des(key, data):
    # Expected match: crypto-anti-patterns.non-aead-cipher (ERROR)
    cipher = DES.new(key)
    return cipher.encrypt(data)
