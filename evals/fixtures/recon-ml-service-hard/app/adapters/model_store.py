import hashlib
import os
import pickle

MODEL_PATH = os.environ.get("MODEL_PATH", "models/risk.pkl")
EXPECTED_SHA256 = os.environ.get("MODEL_SHA256")


def load_model():
    with open(MODEL_PATH, "rb") as fh:
        blob = fh.read()
    if EXPECTED_SHA256 and hashlib.sha256(blob).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("model checksum mismatch")
    return pickle.loads(blob)
