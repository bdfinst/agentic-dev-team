"""Shared fixtures for the benefit-evaluation tests: the sandbox, the CLI loader, the argv builder and
the pre-registration block reader."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

from _repo_root import REPO_ROOT

# Both import roots are added here so no import relies on a side effect of another.
sys.path.insert(0, str(REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))

from benefit_eval import streams

REAL_PREREG = REPO_ROOT / "docs" / "benefit-eval" / "preregistration.md"

#: A real 36-character session id (8-4-4-4-12 hex groups).
LONG_ID = str(uuid.UUID("0123abcd-4567-89ab-cdef-0123456789ab"))

_FENCE_OPEN = "```json prereg\n"


def load_cli(name: str):
    """``scripts/benefit_eval_cli.py`` loaded by file path under a module name of the caller's choosing."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / "benefit_eval_cli.py")
    module = importlib.util.module_from_spec(spec)
    # Python 3.10's dataclass looks its module up in sys.modules, so the CLI must be registered first.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prereg_block_span(text: str) -> tuple[int, int]:
    """Offsets of the JSON inside the pre-registration's fenced block."""
    start = text.index(_FENCE_OPEN) + len(_FENCE_OPEN)
    return start, text.index("\n```", start)


def real_prereg_document() -> dict:
    text = REAL_PREREG.read_text()
    start, end = prereg_block_span(text)
    return json.loads(text[start:end])


def real_entries() -> dict[str, dict]:
    return {entry["id"]: entry for entry in real_prereg_document()["metrics"]}


def cli_argv(command: str, world: World, prereg_path: Path | str, *extra: str) -> list[str]:
    """Arguments that point a CLI command at the sandbox and nothing under the real home directory."""
    return [
        command,
        "--prereg", str(prereg_path),
        "--project-root", str(world.project),
        "--home-metrics", str(world.home),
        "--projects-root", str(world.projects),
        *extra,
    ]  # fmt: skip


class World:
    """A project root, a home metrics dir and a transcript tree under tmp_path."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.project = tmp_path / "project"
        self.home = tmp_path / "home-metrics"
        self.projects = tmp_path / "projects"
        for directory in (self.project / ".claude" / "metrics", self.home, self.projects / "proj-a"):
            directory.mkdir(parents=True)
        self.sources = streams.Sources((self.project,), self.home, self.projects)

    def add_project(self, name: str) -> Path:
        """A second project root; its metrics are read alongside the first's."""
        root = self.project.parent / name
        (root / ".claude" / "metrics").mkdir(parents=True)
        self.sources = streams.Sources((*self.sources.project_roots, root), self.home, self.projects)
        return root

    def metrics_file(self, name: str) -> Path:
        return self.project / ".claude" / "metrics" / name

    def stream(self, name: str, rows: list[dict]) -> Path:
        path = self.metrics_file(f"{name}.jsonl")
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def session(self, session_id: str, content: str = '{"type":"user"}\n') -> None:
        """A real session: a main transcript that parses."""
        (self.projects / "proj-a" / f"{session_id}.jsonl").write_text(content)

    def subagent(self, session_id: str, agent_id: str, records: list[dict]) -> Path:
        directory = self.projects / "proj-a" / session_id / "subagents"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"agent-{agent_id}.jsonl"
        path.write_text("".join(json.dumps(record) + "\n" for record in records))
        return path

    def real_sessions(self, name: str, count: int, extra_rows: int = 10) -> None:
        """One row per session, plus extra rows from the first session."""
        ids = [f"sess{i:04d}-aaaa" for i in range(count)]
        rows = [{"ts": "2026-01-01T00:00:00Z", "session_id": sid} for sid in ids]
        if ids:
            rows += [{"ts": "2026-01-01T00:00:01Z", "session_id": ids[0]}] * extra_rows
        for sid in ids:
            self.session(sid)
        self.stream(name, rows)

    def snapshot(self) -> dict[str, bytes | None]:
        return {
            str(p.relative_to(self.root)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(self.root.rglob("*"))
        }
