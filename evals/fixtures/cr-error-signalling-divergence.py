"""Configuration loading for the report service.

Settings come from three layers, lowest precedence first: the base config
file, an optional overrides file, and ``REPORT_*`` environment variables.
"""

import json
import os
from collections.abc import Mapping

ENV_PREFIX = "REPORT_"


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


def load_optional_overrides(path):
    """Load the overrides file at ``path``, or ``{}`` when it does not exist.

    Overrides are optional, so a missing file is not an error.

    Raises:
        json.JSONDecodeError: if the file exists but is not valid JSON.
    """
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def env_overrides(environ: Mapping[str, str]) -> dict:
    """Return the ``REPORT_*`` variables as lower-case keys without the prefix.

    ``REPORT_PAGE_SIZE=50`` becomes ``{"page_size": "50"}``. Values stay
    strings; ``coerce_like`` converts them against the base config.
    """
    return {
        name[len(ENV_PREFIX):].lower(): value
        for name, value in environ.items()
        if name.startswith(ENV_PREFIX) and len(name) > len(ENV_PREFIX)
    }


def coerce_like(template, raw: str):
    """Convert ``raw`` to the type of ``template``.

    Raises:
        ValueError: if ``raw`` cannot be read as that type.
    """
    if isinstance(template, bool):
        lowered = raw.strip().lower()
        if lowered in ("1", "true", "yes"):
            return True
        if lowered in ("0", "false", "no"):
            return False
        raise ValueError(f"not a boolean: {raw!r}")
    if isinstance(template, int):
        return int(raw)
    if isinstance(template, float):
        return float(raw)
    return raw


def merge(*layers: Mapping) -> dict:
    """Merge ``layers`` left to right; a later layer's key wins.

    Nested mappings merge key by key instead of being replaced.
    """
    merged: dict = {}
    for layer in layers:
        for key, value in layer.items():
            if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
                merged[key] = merge(merged[key], value)
            else:
                merged[key] = value
    return merged


def resolve_settings(base_path, overrides_path, environ=None):
    """Return the effective settings from all three layers.

    Raises:
        FileNotFoundError: if the base config file does not exist.
        json.JSONDecodeError: if either file is not valid JSON.
        ValueError: if an environment value does not match its base type.
    """
    base = load_config(base_path)
    overrides = load_optional_overrides(overrides_path)
    from_env = env_overrides(os.environ if environ is None else environ)
    typed_env = {
        key: coerce_like(base[key], value) if key in base else value
        for key, value in from_env.items()
    }
    return merge(base, overrides, typed_env)
