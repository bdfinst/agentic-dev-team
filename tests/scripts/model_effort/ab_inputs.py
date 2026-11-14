"""Build the A/B harness's inputs in temp dirs: agent files, expected entries, fixtures, paths and trial configs.

Unit tests build their own agents, expected entries and fixtures in temp dirs. Each
shipped asset (an agent file, an expected entry, the recorded transcripts) has one
named smoke test; the transcripts are the harness's parser fixtures.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import ab_harness_path  # noqa: F401  (puts the harness on sys.path first)
from ab_constants import ENABLED
from ab_stub_claude import StubClaude
from model_effort import (
    invocation,
    paths,
    tools,
)
from model_effort.arm import CANDIDATE_LABEL, Arm


def write_agent_file(
    agents_dir: Path,
    name: str,
    tools_line: str | None = None,
    *,
    model: str | None = None,
    effort: str | None = None,
    body: str = "Body.",
) -> None:
    lines = ["---", f"name: {name}"]
    for key, value in (("tools", tools_line), ("model", model), ("effort", effort)):
        if value is not None:
            lines.append(f"{key}: {value}")
    lines += ["---", "", body, ""]
    (agents_dir / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")


def write_expected(expected_dir: Path, stem: str, agent: str, status: str) -> None:
    entry = {
        "fixture": stem,
        "applicableAgents": [agent],
        "agents": {agent: {"expectedStatus": status}},
    }
    (expected_dir / f"{stem}.json").write_text(json.dumps(entry), encoding="utf-8")


def make_file_fixture(
    root: Path, name: str = "form.html", content: str = "<form></form>"
) -> Path:
    fixture = root / name
    fixture.write_text(content, encoding="utf-8")
    return fixture


def make_directory_fixture(root: Path) -> Path:
    fixture = root / "service"
    (fixture / "src" / "deep").mkdir(parents=True)
    (fixture / "README.md").write_text("readme", encoding="utf-8")
    (fixture / "src" / "app.py").write_text("print('app')", encoding="utf-8")
    (fixture / "src" / "deep" / "util.py").write_text("print('util')", encoding="utf-8")
    return fixture


def read_tree(path: Path) -> dict[str, str]:
    files = (
        [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    )
    return {str(p): p.read_text(encoding="utf-8") for p in files}


def eval_paths_with(**overrides: Path) -> paths.EvalPaths:
    """The shipped paths, with the named directories redirected."""
    return dataclasses.replace(paths.EvalPaths.default(), **overrides)


def snapshot_paths_with(**overrides: Path) -> paths.SnapshotPaths:
    """The shipped expected, fixtures and plugin directories, with the named ones redirected."""
    shipped = paths.EvalPaths.default()
    return dataclasses.replace(
        paths.SnapshotPaths(
            expected_dir=shipped.expected_dir,
            fixtures_dir=shipped.fixtures_dir,
            plugin_root=shipped.plugin_root,
        ),
        **overrides,
    )


def trial_config(
    stub: StubClaude | None = None,
    *,
    model: str = "haiku",
    effort: str = "low",
    enabled_tools: tuple[str, ...] = ENABLED,
    system_prompt: str = "You are a reviewer.",
    claude_bin: str | None = None,
    snapshot_paths: paths.SnapshotPaths | None = None,
) -> invocation.TrialConfig:
    profile = tools.ToolProfile(
        enabled_tools=tuple(enabled_tools), withheld_tools=(), refused_tools=()
    )
    return invocation.TrialConfig(
        arm=Arm(label=CANDIDATE_LABEL, model=model, effort=effort),
        system_prompt=system_prompt,
        profile=profile,
        snapshot_paths=snapshot_paths or snapshot_paths_with(),
        claude_bin=claude_bin if claude_bin is not None else str(stub.path),
    )


class FixedRng:
    """Stands in for `random.Random`: always returns the same bits."""

    def getrandbits(self, bits: int) -> int:
        assert bits == 16
        return 0x0AB3
