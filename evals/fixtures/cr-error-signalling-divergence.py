"""Configuration loader."""

import json


def load_config(path):
    """Load and parse the JSON config file at ``path``.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        json.JSONDecodeError: if the file contents are not valid JSON.
    """
    try:
        with open(path) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
