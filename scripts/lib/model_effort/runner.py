"""Stage a fixture and run one `claude -p` trial against it.

Each trial runs in a fresh temp copy of the fixture, outside the repo, so the
project `CLAUDE.md` and hooks are not loaded and the agent cannot alter the
source fixture. The run record is raw process output: parsing the stream and
grading it happen elsewhere.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
# The only extra directory the agent may read. It must never contain answer files.
KNOWLEDGE_DIR = PLUGIN_ROOT / "knowledge"

DEFAULT_CLAUDE_BIN = "claude"
DEFAULT_TRIAL_TIMEOUT_SECONDS = 600
PLUGIN_ROOT_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
TEMP_DIR_PREFIX = "model-effort-ab-"


@dataclass(frozen=True)
class TrialConfig:
    """Everything that selects how the CLI runs, apart from the fixture."""

    model: str
    effort: str
    system_prompt: str
    enabled_tools: Sequence[str]
    claude_bin: str = DEFAULT_CLAUDE_BIN
    plugin_root: Path = PLUGIN_ROOT
    knowledge_dir: Path = KNOWLEDGE_DIR


@dataclass(frozen=True)
class RunRecord:
    """Raw outcome of one CLI process. `exit_code` is None when it timed out."""

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool


def build_user_prompt(staged_name: str) -> str:
    return (
        f"Review `{staged_name}` in the current working directory. "
        "Respond with only the JSON object defined by your output contract, "
        "with no other text."
    )


def build_argv(config: TrialConfig, user_prompt: str) -> list[str]:
    """Return the full CLI argv. `--restricted` keeps reads inside the cwd and `--add-dir`."""
    system_prompt = config.system_prompt.replace(
        PLUGIN_ROOT_PLACEHOLDER, str(config.plugin_root)
    )
    return [
        config.claude_bin,
        "-p",
        user_prompt,
        "--model",
        config.model,
        "--effort",
        config.effort,
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--tools",
        ",".join(config.enabled_tools),
        "--add-dir",
        str(config.knowledge_dir),
        "--restricted",
        "--system-prompt",
        system_prompt,
    ]


@contextmanager
def staged_fixture(fixture: Path) -> Iterator[Path]:
    """Copy a file or directory fixture into a fresh temp dir and yield that dir."""
    staging_dir = Path(tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX))
    try:
        target = staging_dir / fixture.name
        if fixture.is_dir():
            shutil.copytree(fixture, target)
        else:
            shutil.copy2(fixture, target)
        yield staging_dir
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def execute(argv: Sequence[str], cwd: Path, timeout: float) -> RunRecord:
    """Run `argv` in `cwd`; on timeout the child is killed and `timed_out` is set."""
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return RunRecord(
            exit_code=None,
            stdout=_as_text(expired.stdout),
            stderr=_as_text(expired.stderr),
            timed_out=True,
        )
    return RunRecord(
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )


def run_trial(
    fixture: Path,
    config: TrialConfig,
    trial_timeout: float = DEFAULT_TRIAL_TIMEOUT_SECONDS,
) -> RunRecord:
    """Run one trial of `config` against a fresh copy of `fixture`."""
    argv = build_argv(config, build_user_prompt(fixture.name))
    with staged_fixture(fixture) as staging_dir:
        return execute(argv, staging_dir, trial_timeout)


def _as_text(captured: str | bytes | None) -> str:
    # TimeoutExpired carries bytes even when the run requested text mode.
    if captured is None:
        return ""
    if isinstance(captured, bytes):
        return captured.decode("utf-8", errors="replace")
    return captured
