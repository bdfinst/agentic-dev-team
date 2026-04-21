"""Positive fixture for ml-patterns.insecure-pickle-load + torch-load-untrusted."""
import pickle
import joblib
import torch


def load_bad_pickle(fname):
    # Expected match: ml-patterns.insecure-pickle-load (ERROR)
    return pickle.load(fname)


def load_bad_joblib(fname):
    # Expected match: ml-patterns.insecure-pickle-load (ERROR)
    return joblib.load(fname)


def load_bad_torch(fname):
    # Expected match: ml-patterns.torch-load-untrusted (ERROR)
    # No weights_only=True → executes pickle arbitrarily
    return torch.load(fname)
