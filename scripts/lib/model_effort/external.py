"""Load existing repo scripts by file path, so the harness reuses them without sys.path edits.

Every script the harness reuses comes through here, so the package imports with
only its own directory on `sys.path`. Path loading also avoids a name collision:
`scripts/validate_agent_contract.py` is a shim that shadows the real module of
the same name. `eval_grade` puts its own directory on `sys.path` when it loads,
to find the grader registry beside it.

The wrappers at the end are the only place that reaches those scripts' contract
data and private helpers, so an upstream rename breaks one function here. A
wrapper that calls into an upstream script checks the call shape and the return
shape itself and raises `ExternalContractError` when they have drifted, so that
drift is a harness fault and never reads as an agent's answer failing.
"""

from __future__ import annotations

import importlib.util
import inspect
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from types import ModuleType

from . import paths

# What `grade_against_expected` passes to `run_grading`, as keyword names.
_RUN_GRADING_KEYWORDS = ("expected_dir", "actuals", "baseline", "only")


class ExternalContractError(ImportError):
    """A script the harness reuses no longer has the interface the harness relies on."""


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


def load_for_run() -> None:
    """Load, and check the interface of, each script a trial reaches only after approval.

    Call it while the run is planned. The scripts a trial uses are then the ones
    in place when the operator approved: a later edit changes nothing, and a
    script that no longer fits fails before any trial is paid for.

    Raises:
        ExternalContractError: a script has a different interface.
        ImportError, OSError, SyntaxError: a script cannot be read or loaded.
    """
    _checked_run_grading()
    _checked_should_scrub()


def _checked_should_scrub():
    should_scrub = getattr(isolated_dispatch(), "_should_scrub", None)
    if not callable(should_scrub):
        raise ExternalContractError(
            "skills/headless-run/scripts/isolated_dispatch.py no longer defines _should_scrub"
        )
    return should_scrub


def _checked_run_grading():
    run_grading = getattr(eval_grade(), "run_grading", None)
    if run_grading is None:
        raise ExternalContractError(
            "scripts/eval_grade.py no longer defines run_grading"
        )
    try:
        inspect.signature(run_grading).bind(**dict.fromkeys(_RUN_GRADING_KEYWORDS))
    except TypeError as error:
        raise ExternalContractError(
            f"scripts/eval_grade.py run_grading no longer accepts the keywords "
            f"{', '.join(_RUN_GRADING_KEYWORDS)}: {error}"
        ) from error
    return run_grading


def grade_against_expected(
    expected_dir: Path, stem: str, agent: str, parsed: dict
) -> list[tuple[str, bool, list[str]]]:
    """Grade `parsed` for `agent` on fixture `stem` against the entries in `expected_dir`.

    Returns one `(pair, passed, failure messages)` row per graded entry; none when
    `expected_dir` has no entry for `agent`. An error the grader raises because of
    the shape of `parsed` propagates unchanged.

    Raises:
        ExternalContractError: the grader no longer takes this call or returns
            another shape.
    """
    returned = _checked_run_grading()(
        expected_dir=expected_dir,
        actuals={stem: {"agents": {agent: parsed}}},
        baseline=None,
        only={agent},
    )
    return _grading_rows(returned)


def _grading_rows(returned) -> list[tuple[str, bool, list[str]]]:
    drifted = ExternalContractError(
        "scripts/eval_grade.py run_grading no longer returns (rows, baseline) "
        "with (pair, passed, failure messages) rows"
    )
    if not isinstance(returned, tuple) or len(returned) != 2:
        raise drifted
    rows = returned[0]
    if not isinstance(rows, list) or not all(
        isinstance(row, tuple) and len(row) == 3 and isinstance(row[2], list)
        for row in rows
    ):
        raise drifted
    return rows


def should_scrub_env_var(name: str) -> bool:
    """True when `isolated_dispatch` removes the environment variable `name` from a child."""
    return _checked_should_scrub()(name)


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
