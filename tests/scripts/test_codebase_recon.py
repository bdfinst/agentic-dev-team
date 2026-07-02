"""Slice 5: codebase_recon.py harness — deterministic steps, schema
validation, atomic write, inventory error handling, and step ordering.

Ported from tests/scripts/codebase_recon_tests.bats (issue #676). pytest's
tmp_path fixture replaces the bash hermetic helper's mktemp -d + rm -rf.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "codebase_recon.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").touch()
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
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
