"""Negative fixture — should produce zero matches."""
import torch
import hashlib


def load_safe_torch(fname):
    # Safe: weights_only=True prevents arbitrary code execution
    return torch.load(fname, weights_only=True)


def load_safe_safetensors(fname):
    from safetensors.torch import load_file
    return load_file(fname)


def load_verified_onnx(fname, expected_hash):
    with open(fname, "rb") as f:
        computed = hashlib.sha256(f.read()).hexdigest()
    if computed == expected_hash:
        import onnx
        return onnx.load(fname)
    raise ValueError("model hash mismatch")
