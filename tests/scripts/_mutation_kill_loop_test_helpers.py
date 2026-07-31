"""Shared fixture helpers for ``test_mutation_kill_loop*.py`` (issue #1564).

``test_mutation_kill_loop.py`` grew past the project's 500-line guideline and
was split into four scenario-focused files: config/run mechanics (kept in
``test_mutation_kill_loop.py``), insertion/verification orchestration
(``test_mutation_kill_loop_orchestration.py``), verify/commit subprocess
wiring (``test_mutation_kill_loop_verify.py``), and CLI dispatch
(``test_mutation_kill_loop_cli.py``). ``_loop_fixture``
(and the small ``_write_config``/``_mutant``/``_write_report`` builders it
depends on) is used across many tests in more than one of those files, so it
is centralized here rather than duplicated.

Named with a leading underscore (not ``conftest``) to match this directory's
existing convention for cross-file test helpers — see
``_mutation_test_helpers.py``'s own docstring for the rationale (avoiding
ambiguity with pytest's own conftest.py fixture-collection mechanism when
multiple test directories each have their own conftest.py). This module is a
plain importable module, not a pytest plugin.

Kept separate from ``_mutation_test_helpers.py`` (which holds generic,
cross-mutation-suite constants like ``SCRIPTS_DIR``/``FORBIDDEN_LITERALS``)
because these helpers are specific to the kill-loop test family and need
``mutation_kill_loop`` importable, a dependency the generic helpers module
does not otherwise require.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from _mutation_test_helpers import SCRIPTS_DIR

# Ensure the module's dir is on the path so we can import it directly.
sys.path.insert(0, str(SCRIPTS_DIR))

import mutation_kill_loop as loop


def _write_config(
    repo_root: Path,
    *,
    project: str = "src/Widget.WebApi/Widget.WebApi.csproj",
    test_projects=("test/Widget.WebApi.Tests/Widget.WebApi.Tests.csproj",),
    solution: str = "App.sln",
    wrapper_shape: bool = True,
) -> Path:
    inner = {
        "solution": solution,
        "project": project,
        "test-projects": list(test_projects),
        "mutate": ["**/*.cs"],
    }
    payload = {"stryker-config": inner} if wrapper_shape else inner
    path = repo_root / "stryker-config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _mutant(status: str, mutator: str = "ArithmeticOperator", line: int = 1) -> dict:
    return {
        "id": f"{mutator}-{status}-{line}",
        "mutatorName": mutator,
        "status": status,
        "location": {"start": {"line": line}},
        "replacement": "<replacement>",
    }


def _write_report(repo_root: Path, source_key: str, mutants) -> Path:
    report = repo_root / "reports" / "mutation-report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps({"files": {source_key: {"mutants": list(mutants)}}}),
        encoding="utf-8",
    )
    return report


def _loop_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutants=None,
    *,
    report_override: dict | None = None,
    log=lambda m: None,
):
    """Wire a run_for_file invocation with a fixed initial report and a
    generator that records its calls. Returns (source_file, ctx, kwargs, events).

    By default the initial report is the single-file shape ``_write_report``
    builds from ``mutants``. Pass ``report_override`` (a full report payload,
    e.g. a multi-file ``{"files": {...}}`` shape) instead when a caller needs
    a custom report; ``mutants`` is ignored in that case. Pass ``log`` to
    capture round log lines (it lives on ``RunContext``, not the caller's
    kwargs).
    """
    config = loop.load_loop_config(_write_config(tmp_path))
    test_file = tmp_path / "PaymentServiceTests.cs"
    test_file.write_text(
        (
            "namespace Widget.Tests\n"
            "{\n"
            "    public class PaymentServiceTests\n"
            "    {\n"
            "        [Test]\n"
            "        public async Task Existing_Case_Works()\n"
            "        {\n"
            "        }\n"
            "    }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    source_path = tmp_path / "PaymentService.cs"
    source_path.write_text("public class PaymentService {}\n", encoding="utf-8")
    if report_override is not None:
        report = tmp_path / "reports" / "mutation-report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(report_override), encoding="utf-8")
    else:
        report = _write_report(tmp_path, "src/Widget.WebApi/PaymentService.cs", mutants)

    events: list = []

    new_method = (
        "        [Test]\n"
        "        public async Task New_Case_KillsMutant()\n"
        "        {\n"
        "        }\n"
    )

    def generator(src, survivors, src_text, test_text):
        events.append(("generate", len(survivors)))
        return new_method

    monkeypatch.setattr(
        loop, "git_revert", lambda tf, **k: events.append(("revert", str(tf))) or True
    )
    # git_reset_and_revert is what the commit-failure path actually calls
    # (#1598/#1584 review) — tagged "revert" too so the existing
    # kinds.count("revert") assertions keep meaning "a revert happened",
    # regardless of which of the two functions performed it.
    monkeypatch.setattr(
        loop,
        "git_reset_and_revert",
        lambda tf, **k: events.append(("revert", str(tf))) or True,
    )
    monkeypatch.setattr(
        loop, "git_commit", lambda msg, tf, **k: events.append(("commit", msg)) or True
    )

    ctx = loop.RunContext(
        config=config,
        test_file=test_file,
        source_path=source_path,
        output_dir=tmp_path / "out",
        log=log,
        initial_report_path=report,
    )
    kwargs = {
        "generate": generator,
        "max_rounds": 3,
    }
    return "PaymentService.cs", ctx, kwargs, events
