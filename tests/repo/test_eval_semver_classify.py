"""Tests for scripts/eval_semver_classify.sh — the eval-corpus-as-semver
classifier (issue #101). The pure functions are sourced and exercised
directly; the end-to-end git flow is exercised in a throwaway repo.

Hermetic per #546: git exports GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE/
GIT_PREFIX/GIT_REFLOG_ACTION into a pre-push hook's environment, and
nothing in the hook chain scrubs them. A fixture that runs `git init` /
`git commit` inherits those and can silently rewrite refs on the parent
repo. Every subprocess here scrubs the git env and cds into a per-test
tmp_path (pytest's own tempdir isolation plays the role of
tests/lib/hermetic.bash's mktemp -d + trap cleanup).

Ported from tests/repo/eval_semver_classify_tests.bats (issue #672).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "eval_semver_classify.sh"

GIT_SCRUB_ENV_VARS = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_REFLOG_ACTION",
)


def _hermetic_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in GIT_SCRUB_ENV_VARS}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env


def _source_and_call(
    call: str, cwd: Path, stdin: str = ""
) -> subprocess.CompletedProcess:
    """Run `source SCRIPT; <call>` in a scrubbed bash subshell."""
    return subprocess.run(
        ["bash", "-c", f"source '{SCRIPT}'; {call}"],
        cwd=str(cwd),
        input=stdin,
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


# --- classify_change_class --------------------------------------------------


def test_classify_no_expected_changes_none(tmp_path: Path) -> None:
    res = _source_and_call("classify_change_class", tmp_path, stdin="")
    assert res.stdout.strip() == "none"


def test_classify_only_added_expected_files_additive(tmp_path: Path) -> None:
    res = _source_and_call(
        "classify_change_class",
        tmp_path,
        stdin="A\tevals/expected/a.json\nA\tevals/expected/b.json\n",
    )
    assert res.stdout.strip() == "additive"


def test_classify_a_modified_expected_file_editing(tmp_path: Path) -> None:
    res = _source_and_call(
        "classify_change_class",
        tmp_path,
        stdin="A\tevals/expected/a.json\nM\tevals/expected/b.json\n",
    )
    assert res.stdout.strip() == "editing"


def test_classify_a_deleted_expected_file_editing(tmp_path: Path) -> None:
    res = _source_and_call(
        "classify_change_class", tmp_path, stdin="D\tevals/expected/b.json\n"
    )
    assert res.stdout.strip() == "editing"


def test_classify_a_renamed_expected_file_editing(tmp_path: Path) -> None:
    res = _source_and_call(
        "classify_change_class",
        tmp_path,
        stdin="R100\tevals/expected/a.json\tevals/expected/c.json\n",
    )
    assert res.stdout.strip() == "editing"


# --- class_to_min_bump -------------------------------------------------------


def test_min_bump_editing_major_additive_minor_none_patch(tmp_path: Path) -> None:
    for cls, expected in (
        ("editing", "major"),
        ("additive", "minor"),
        ("none", "patch"),
    ):
        res = _source_and_call(f"class_to_min_bump {cls}", tmp_path)
        assert res.stdout.strip() == expected


# --- detect_commit_bump ------------------------------------------------------


def test_detect_feat_minor(tmp_path: Path) -> None:
    res = _source_and_call("detect_commit_bump", tmp_path, stdin="feat: add agent\n")
    assert res.stdout.strip() == "minor"


def test_detect_feat_scope_bang_major(tmp_path: Path) -> None:
    res = _source_and_call(
        "detect_commit_bump", tmp_path, stdin="feat(agents)!: change contract\n"
    )
    assert res.stdout.strip() == "major"


def test_detect_breaking_change_footer_major(tmp_path: Path) -> None:
    res = _source_and_call(
        "detect_commit_bump",
        tmp_path,
        stdin="fix: tweak\n\nBREAKING CHANGE: alters expected\n",
    )
    assert res.stdout.strip() == "major"


def test_detect_fix_chore_only_patch(tmp_path: Path) -> None:
    res = _source_and_call(
        "detect_commit_bump", tmp_path, stdin="fix: typo\nchore: deps\n"
    )
    assert res.stdout.strip() == "patch"


def test_detect_strongest_wins_feat_then_breaking_major(tmp_path: Path) -> None:
    res = _source_and_call("detect_commit_bump", tmp_path, stdin="feat: a\nfeat!: b\n")
    assert res.stdout.strip() == "major"


# --- class_to_min_bump: threshold (#136) ------------------------------------


def test_min_bump_threshold_minor_136(tmp_path: Path) -> None:
    res = _source_and_call("class_to_min_bump threshold", tmp_path)
    assert res.stdout.strip() == "minor"


# --- classify_expected_edit (#136) ------------------------------------------


def test_edit_only_a_tolerance_changed_threshold(tmp_path: Path) -> None:
    base = (
        '{"applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":1}}}}'
    )
    head = (
        '{"applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}'
    )
    res = _source_and_call(f"classify_expected_edit '{base}' '{head}'", tmp_path)
    assert res.stdout.strip() == "threshold"


def test_edit_a_flipped_expectedstatus_flip(tmp_path: Path) -> None:
    base = '{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass"}}}'
    head = '{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"fail"}}}'
    res = _source_and_call(f"classify_expected_edit '{base}' '{head}'", tmp_path)
    assert res.stdout.strip() == "flip"


def test_edit_an_added_applicable_agent_flip(tmp_path: Path) -> None:
    base = '{"applicableAgents":["a"],"agents":{"a":{"expectedStatus":"pass"}}}'
    head = (
        '{"applicableAgents":["a","b"],'
        '"agents":{"a":{"expectedStatus":"pass"},"b":{"expectedStatus":"pass"}}}'
    )
    res = _source_and_call(f"classify_expected_edit '{base}' '{head}'", tmp_path)
    assert res.stdout.strip() == "flip"


def test_edit_a_prose_only_description_change_threshold(tmp_path: Path) -> None:
    base = (
        '{"applicableAgents":["a"],"description":"old",'
        '"agents":{"a":{"expectedStatus":"pass"}}}'
    )
    head = (
        '{"applicableAgents":["a"],"description":"new wording",'
        '"agents":{"a":{"expectedStatus":"pass"}}}'
    )
    res = _source_and_call(f"classify_expected_edit '{base}' '{head}'", tmp_path)
    assert res.stdout.strip() == "threshold"


# --- end-to-end via a throwaway git repo ------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


def _run_script(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "tag.gpgsign", "false")
    (tmp_path / "evals" / "expected").mkdir(parents=True)
    (tmp_path / "evals" / "expected" / "x.json").write_text(
        '{"fixture":"x.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"fail"}}}\n'
    )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "chore: seed corpus")
    return tmp_path


@pytest.fixture
def repo_threshold(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "tag.gpgsign", "false")
    (tmp_path / "evals" / "expected").mkdir(parents=True)
    (tmp_path / "evals" / "expected" / "x.json").write_text(
        '{"fixture":"x.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":1}}}}\n'
    )
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "chore: seed corpus")
    return tmp_path


def _base_ref(cwd: Path) -> str:
    res = _git(cwd, "rev-parse", "HEAD")
    return res.stdout.strip()


def test_e2e_editing_an_expected_value_without_feat_fails(repo: Path) -> None:
    base = _base_ref(repo)
    (repo / "evals" / "expected" / "x.json").write_text(
        '{"fixture":"x.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass"}}}\n'
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix: tweak expectation")
    res = _run_script(repo, base, "HEAD")
    assert res.returncode == 1
    assert "requires a 'major' bump" in res.stdout + res.stderr


def test_e2e_editing_an_expected_value_with_feat_bang_passes(repo: Path) -> None:
    base = _base_ref(repo)
    (repo / "evals" / "expected" / "x.json").write_text(
        '{"fixture":"x.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass"}}}\n'
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat!: change a's expected status")
    res = _run_script(repo, base, "HEAD")
    assert res.returncode == 0
    assert "OK:" in res.stdout + res.stderr


def test_e2e_adding_a_new_expected_file_with_feat_passes(repo: Path) -> None:
    base = _base_ref(repo)
    (repo / "evals" / "expected" / "y.json").write_text(
        '{"fixture":"y.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"fail"}}}\n'
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: add fixture y")
    res = _run_script(repo, base, "HEAD")
    assert res.returncode == 0


def test_e2e_adding_a_new_expected_file_with_only_fix_fails_needs_minor(
    repo: Path,
) -> None:
    base = _base_ref(repo)
    (repo / "evals" / "expected" / "y.json").write_text(
        '{"fixture":"y.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"fail"}}}\n'
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix: add fixture y")
    res = _run_script(repo, base, "HEAD")
    assert res.returncode == 1
    assert "requires a 'minor' bump" in res.stdout + res.stderr


def test_e2e_no_corpus_change_with_chore_passes_patch(repo: Path) -> None:
    base = _base_ref(repo)
    (repo / "README.md").write_text("unrelated\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: docs")
    res = _run_script(repo, base, "HEAD")
    assert res.returncode == 0


# --- #136: threshold-only edits classify as minor, not major ---------------


def test_e2e_a_threshold_only_edit_needs_only_a_minor_bump_feat_passes(
    repo_threshold: Path,
) -> None:
    base = _base_ref(repo_threshold)
    (repo_threshold / "evals" / "expected" / "x.json").write_text(
        '{"fixture":"x.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}\n'
    )
    _git(repo_threshold, "add", "-A")
    _git(repo_threshold, "commit", "-q", "-m", "feat: widen x tolerance")
    res = _run_script(repo_threshold, base, "HEAD")
    assert res.returncode == 0
    assert "corpus change:     threshold" in res.stdout + res.stderr


def test_e2e_a_threshold_only_edit_with_only_fix_fails_needs_minor_not_major(
    repo_threshold: Path,
) -> None:
    base = _base_ref(repo_threshold)
    (repo_threshold / "evals" / "expected" / "x.json").write_text(
        '{"fixture":"x.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}\n'
    )
    _git(repo_threshold, "add", "-A")
    _git(repo_threshold, "commit", "-q", "-m", "fix: widen x tolerance")
    res = _run_script(repo_threshold, base, "HEAD")
    assert res.returncode == 1
    assert "requires a 'minor' bump" in res.stdout + res.stderr


def test_e2e_a_threshold_only_edit_does_not_demand_a_major_bump(
    repo_threshold: Path,
) -> None:
    base = _base_ref(repo_threshold)
    (repo_threshold / "evals" / "expected" / "x.json").write_text(
        '{"fixture":"x.ts","applicableAgents":["a"],'
        '"agents":{"a":{"expectedStatus":"pass","issueCount":{"min":0,"max":3}}}}\n'
    )
    _git(repo_threshold, "add", "-A")
    _git(repo_threshold, "commit", "-q", "-m", "feat: widen x tolerance")
    res = _run_script(repo_threshold, base, "HEAD")
    assert "requires a 'major' bump" not in res.stdout + res.stderr


# --- #136: new review agent without a fixture is flagged --------------------


def test_e2e_a_new_review_agent_with_no_fixture_fails(repo: Path) -> None:
    base = _base_ref(repo)
    agents_dir = repo / "plugins" / "dev-team" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "foo-review.md").write_text(
        "---\nname: foo-review\nmodel: haiku\n---\n# Foo Review\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: add foo-review agent")
    res = _run_script(repo, base, "HEAD")
    assert res.returncode == 1
    assert "without any eval fixture: foo-review" in res.stdout + res.stderr


def test_e2e_a_new_review_agent_with_a_covering_fixture_passes(repo: Path) -> None:
    base = _base_ref(repo)
    agents_dir = repo / "plugins" / "dev-team" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "foo-review.md").write_text(
        "---\nname: foo-review\nmodel: haiku\n---\n# Foo Review\n"
    )
    (repo / "evals" / "expected" / "f.json").write_text(
        '{"fixture":"f.ts","applicableAgents":["foo-review"],'
        '"agents":{"foo-review":{"expectedStatus":"fail"}}}\n'
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: add foo-review agent + fixture")
    res = _run_script(repo, base, "HEAD")
    assert res.returncode == 0
