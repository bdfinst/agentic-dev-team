"""Load existing repo scripts by file path, so the harness reuses them without sys.path edits.

Every script the harness reuses comes through here, so the package imports with
only its own directory on `sys.path`. Path loading also avoids a name collision:
`scripts/validate_agent_contract.py` is a shim that shadows the real module of
the same name. `eval_grade` puts its own directory on `sys.path` when it loads,
to find the grader registry beside it.

The wrappers at the end are the only place that reaches those scripts' contract
data and private helpers, so an upstream rename breaks one function here.
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


def minimal_yaml() -> ModuleType:
    """`plugins/dev-team/hooks/lib/minimal_yaml.py`."""
    return _load_module(paths.MINIMAL_YAML)


def pricing() -> ModuleType:
    """`plugins/dev-team/hooks/lib/pricing.py`."""
    return _load_module(paths.PRICING_MODULE)


def eval_grade() -> ModuleType:
    """`scripts/eval_grade.py`, the deterministic grader the CI agent-eval gate uses."""
    return _load_module(paths.EVAL_GRADE)


def should_scrub_env_var(name: str) -> bool:
    """True when `isolated_dispatch` removes the environment variable `name` from a child."""
    return isolated_dispatch()._should_scrub(name)


def contract_enums() -> tuple[Sequence[str], Sequence[str]] | None:
    """The agent contract's allowed `model` and `effort` values, or None when it cannot be read."""
    contract = agent_contract_validator().load_contract()
    if contract is None:
        return None
    fields = contract["fields"]
    return fields["model"]["enum"], fields["effort"]["enum"]


def model_is_valid(value: str, enum: Sequence[str]) -> bool:
    """True when `value` is in the agent contract's model `enum` or is a full model ID."""
    return agent_contract_validator()._model_is_valid(value, enum)
