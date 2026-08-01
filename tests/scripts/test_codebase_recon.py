"""Slice 5: codebase_recon.py harness — deterministic steps, schema
validation, atomic write, inventory error handling, and step ordering.

Ported from tests/scripts/codebase_recon_tests.bats (issue #676). pytest's
tmp_path fixture replaces the bash hermetic helper's mktemp -d + rm -rf.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "codebase_recon.py"


def _hermetic_git_env(home: Path) -> dict:
    """Mirrors tests/repo/conftest.py's hermetic_env (issue #546): scrub the
    GIT_DIR/GIT_INDEX_FILE/etc vars git can leak into a subprocess's
    environment, and redirect global/system git config to /dev/null so the
    real user's ~/.gitconfig (hooks, aliases, safe.directory rules) can never
    influence this test's throwaway repo. The original bash->pytest port
    (issue #676) kept tmp_path isolation but dropped this env scrub, which
    tests/lib/hermetic.bash's mktemp -d + rm -rf helper had also done --
    restoring it here (test-improve issue-1354 Story 6) after an
    intermittent `fatal: failed to write commit object` under full-suite
    parallel load."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "GIT_DIR",
            "GIT_INDEX_FILE",
            "GIT_WORK_TREE",
            "GIT_PREFIX",
            "GIT_REFLOG_ACTION",
        )
    }
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["HOME"] = str(home)
    return env


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    env = _hermetic_git_env(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True, env=env)
    (tmp_path / "README.md").touch()
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True, env=env)
    return tmp_path


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _find_json(out_dir: Path) -> Path | None:
    matches = list(out_dir.glob("*.json"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# 5.1 — jsonschema importable; harness runs without ImportError
# ---------------------------------------------------------------------------


def test_5_1a_jsonschema_is_importable() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import jsonschema"], capture_output=True, check=False
    )
    assert result.returncode == 0


def test_5_1b_harness_runs_with_skip_llm_on_a_minimal_git_repo(repo: Path) -> None:
    result = _run(repo, "--skip-llm", "--output-dir", str(repo / "out"))
    # Must NOT crash (ImportError, SyntaxError, etc.); exit 0 = pass, 1 = errors found
    assert result.returncode in (0, 1)


def test_5_1c_harness_does_not_hang_and_produces_output_with_skip_llm(
    repo: Path,
) -> None:
    result = subprocess.run(
        [
            "timeout",
            "30",
            sys.executable,
            str(SCRIPT),
            str(repo),
            "--skip-llm",
            "--output-dir",
            str(repo / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 124  # 124 = timeout killed


def test_5_1d_missing_jsonschema_degrades_to_a_warning_not_a_crash(repo: Path) -> None:
    """`python3 -S` skips site-packages initialization, so a site-installed
    package like jsonschema is unimportable while stdlib and the script's own
    sys.path.insert()-based sibling imports are unaffected — a real absent-
    dependency environment, not a mock."""
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(SCRIPT),
            str(repo),
            "--skip-llm",
            "--output-dir",
            str(repo / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "warn"
    assert any(
        "jsonschema is not installed" in issue["message"] for issue in payload["issues"]
    )
    artifacts = list((repo / "out").glob("recon-*.json"))
    assert artifacts, "artifact should still be written"
    written = json.loads(artifacts[0].read_text())
    assert written["schema_version"] == "1.0"


# ---------------------------------------------------------------------------
# 5.2 — Deterministic steps 1/2/6 produce non-empty data; inventory error
# ---------------------------------------------------------------------------


def test_5_2a_skip_llm_writes_a_json_file_to_the_output_dir(repo: Path) -> None:
    out_dir = repo / "out"
    result = _run(repo, "--skip-llm", "--output-dir", str(out_dir))
    assert result.returncode in (0, 1)
    if result.returncode == 0:
        assert len(list(out_dir.glob("*.json"))) >= 1


def test_5_2b_fake_recon_inventory_that_exits_1_causes_harness_to_exit_1(
    repo: Path,
) -> None:
    fake_scripts = repo / "fake-scripts"
    fake_scripts.mkdir()
    fake_inventory = fake_scripts / "recon_inventory.py"
    fake_inventory.write_text(
        '#!/usr/bin/env bash\necho "inventory failed" >&2\nexit 1\n'
    )
    fake_inventory.chmod(0o755)

    result = _run(
        repo,
        "--skip-llm",
        "--output-dir",
        str(repo / "out"),
        "--inventory-script",
        str(fake_inventory),
    )
    assert result.returncode == 1


def test_5_2c_fake_recon_inventory_failure_leaves_no_artifact_in_output_dir(
    repo: Path,
) -> None:
    fake_scripts = repo / "fake-scripts"
    fake_scripts.mkdir()
    fake_inventory = fake_scripts / "recon_inventory.py"
    fake_inventory.write_text(
        '#!/usr/bin/env bash\necho "inventory failed" >&2\nexit 1\n'
    )
    fake_inventory.chmod(0o755)

    out_dir = repo / "out"
    _run(
        repo,
        "--skip-llm",
        "--output-dir",
        str(out_dir),
        "--inventory-script",
        str(fake_inventory),
    )

    assert len(list(out_dir.glob("*.json"))) == 0 if out_dir.exists() else True


# ---------------------------------------------------------------------------
# 5.3 — Schema validation and atomic artifact write
# ---------------------------------------------------------------------------


def test_5_3a_valid_skip_llm_run_writes_a_json_file_that_parses(repo: Path) -> None:
    out_dir = repo / "out"
    result = _run(repo, "--skip-llm", "--output-dir", str(out_dir))
    assert result.returncode == 0
    f = _find_json(out_dir)
    assert f is not None
    json.loads(f.read_text())  # must parse


def test_5_3b_emitted_artifact_contains_required_schema_top_level_keys(
    repo: Path,
) -> None:
    out_dir = repo / "out"
    result = _run(repo, "--skip-llm", "--output-dir", str(out_dir))
    assert result.returncode == 0
    f = _find_json(out_dir)
    assert f is not None
    data = json.loads(f.read_text())
    required = [
        "schema_version",
        "generated_at",
        "repo",
        "entry_points",
        "languages",
        "dependencies",
        "architecture",
        "security_surface",
        "git_history",
    ]
    missing = [k for k in required if k not in data]
    assert not missing, missing


def test_5_3c_artifact_is_written_atomically_no_tmp_leftover(repo: Path) -> None:
    out_dir = repo / "out"
    result = _run(repo, "--skip-llm", "--output-dir", str(out_dir))
    assert result.returncode == 0
    f = _find_json(out_dir)
    assert f is not None
    assert len(list(out_dir.glob("*.tmp"))) == 0


def test_5_3d_step_ordering_meta_used_in_steps_2_and_6(repo: Path) -> None:
    out_dir = repo / "out"
    result = _run(repo, "--skip-llm", "--output-dir", str(out_dir))
    assert result.returncode == 0
    f = _find_json(out_dir)
    assert f is not None
    data = json.loads(f.read_text())
    expected_name = repo.resolve().name
    assert data["repo"]["name"] == expected_name


def test_5_3e_schema_version_in_emitted_artifact_is_1_0(repo: Path) -> None:
    out_dir = repo / "out"
    result = _run(repo, "--skip-llm", "--output-dir", str(out_dir))
    assert result.returncode == 0
    f = _find_json(out_dir)
    assert f is not None
    data = json.loads(f.read_text())
    assert data.get("schema_version") == "1.0"


# ---------------------------------------------------------------------------
# 5.4 — main()'s default-output-dir slug must reuse _derive_slug, not
# duplicate its regex logic inline.
# ---------------------------------------------------------------------------


def _main_function_source() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("\ndef main(")
    # main() is the last top-level def in the file; slice to the __main__ guard.
    end = text.index('\nif __name__ == "__main__":', start)
    return text[start:end]


def test_main_reuses_derive_slug_helper_instead_of_duplicating_the_regex() -> None:
    main_src = _main_function_source()
    assert "_derive_slug(" in main_src, (
        "main() should call _derive_slug(root) for its default output-dir "
        "slug instead of re-deriving it inline"
    )
    # The duplicated regex substitution (the tell-tale sign of the inline
    # copy) must not appear a second time inside main().
    assert "[^a-z0-9._-]" not in main_src, (
        "main() still duplicates _derive_slug's regex inline"
    )


def test_default_output_dir_uses_derived_slug_for_a_name_needing_slugification(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "My Weird Repo!!"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").touch()
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo_dir, check=True)

    workdir = tmp_path / "workdir"
    workdir.mkdir()

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(repo_dir), "--skip-llm"],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    expected_out_dir = workdir / "memory" / "recon-my-weird-repo"
    assert expected_out_dir.is_dir(), sorted(
        p.name for p in (workdir / "memory").glob("*")
    )
    assert len(list(expected_out_dir.glob("*.json"))) == 1


# --- #1651: the git-history probe must not degrade silently -----------------


def _deterministic_recon_module():
    """Import deterministic_recon.py as a module, mirroring how the shipped
    scripts import their siblings (sys.path insert, not a package)."""
    import importlib.util

    path = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib" / "deterministic_recon.py"
    spec = importlib.util.spec_from_file_location("deterministic_recon_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "exc, expected",
    [
        (subprocess.TimeoutExpired(cmd=["git"], timeout=30), "timed out"),
        (subprocess.SubprocessError("boom"), "failed"),
    ],
)
def test_git_history_probe_records_a_degrade_note(tmp_path, monkeypatch, exc, expected):
    """An empty `sensitive_file_history` must be distinguishable from a scan
    that never completed. Before #1651 the probe swallowed both timeout and
    subprocess errors with a bare `pass`, so a git-history scan that died on a
    large repo reported exactly what a clean repo reports."""
    module = _deterministic_recon_module()
    (tmp_path / ".git").mkdir()

    def boom(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr(module.subprocess, "run", boom)

    notes: list = []
    result = module.probe_git_history(tmp_path, notes)

    assert result["sensitive_file_history"] == []
    assert len(notes) == 1, "a degraded probe must say so exactly once"
    assert notes[0].startswith("DEGRADED:")
    assert expected in notes[0]
    # The note must warn against the specific misreading, not just say "error".
    assert "does NOT mean none was found" in notes[0]


def test_git_history_probe_stays_silent_when_it_succeeds(tmp_path):
    """The degrade note must be absent on the happy path, or it is noise that
    trains readers to ignore it."""
    module = _deterministic_recon_module()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    notes: list = []
    module.probe_git_history(tmp_path, notes)

    assert notes == []


def test_build_recon_surfaces_the_degrade_note_in_the_envelope(tmp_path, monkeypatch):
    """The note has to reach the emitted envelope's `notes` array — the schema
    pins `git_history` to additionalProperties:false, so `notes` is the only
    channel a degrade signal can travel through."""
    module = _deterministic_recon_module()
    (tmp_path / ".git").mkdir()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    real_run = module.subprocess.run

    def boom(argv, *args, **kwargs):
        if isinstance(argv, list) and "log" in argv and "--all" in argv:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=30)
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", boom)

    envelope = module.build_recon(tmp_path)

    assert any(n.startswith("DEGRADED:") for n in envelope["notes"])
