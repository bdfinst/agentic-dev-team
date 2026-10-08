"""Load existing repo scripts by file path, so the harness reuses them without sys.path edits.

Path loading avoids a name collision: `scripts/validate_agent_contract.py` is a
shim that shadows the real module of the same name.

The two wrappers at the end are the only place that reaches those scripts' private
helpers, so an upstream rename breaks one function here.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from types import ModuleType

from . import paths


@cache
def _load_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_model_effort_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agent_contract_validator() -> ModuleType:
    """`plugins/marketplace-dev/scripts/validate_agent_contract.py`."""
    return _load_module(paths.AGENT_CONTRACT_VALIDATOR)


def isolated_dispatch() -> ModuleType:
    """`plugins/dev-team/skills/headless-run/scripts/isolated_dispatch.py`."""
    return _load_module(paths.ISOLATED_DISPATCH)


def should_scrub_env_var(name: str) -> bool:
    """True when `isolated_dispatch` removes the environment variable `name` from a child."""
    return isolated_dispatch()._should_scrub(name)


def model_is_valid(value: str, enum: Sequence[str]) -> bool:
    """True when `value` is in the agent contract's model `enum` or is a full model ID."""
    return agent_contract_validator()._model_is_valid(value, enum)
