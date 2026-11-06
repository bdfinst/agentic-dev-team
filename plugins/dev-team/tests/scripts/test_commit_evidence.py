"""Unit tests for scripts/lib/commit_evidence.py (#2275).

The leaf owns the git evidence rule the progress guardian and the feature
record share. Every git case runs against a real temporary repository.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
_LIB = _SCRIPTS / "lib"
sys.path.insert(0, str(_LIB))
# importlib import mode does not put this directory on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import commit_evidence
from git_fixtures import commit as _commit
from git_fixtures import git as _git
from git_fixtures import init as _init
from git_fixtures import isolate_git, remove_loose_object


@pytest.fixture(autouse=True)
def _hermetic_git(monkeypatch, tmp_path):
    """`run_git` inherits the process environment; keep it away from the host's
    git config, from any GIT_DIR the test runner was started under, and from
    any repository above the temporary directory."""
    isolate_git(monkeypatch, [tmp_path.parent])


def _repo_on(root: Path, trunk: str) -> Path:
    """`trunk` holds one seed commit; HEAD is on `feature` at the same commit."""
    root.mkdir(parents=True, exist_ok=True)
    _init(root, branch=trunk)
    _commit(root, "seed.txt", "chore: seed")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _repo_on(tmp_path / "repo", "main")


# ---------------------------------------------------------------------------
# run_git
# ---------------------------------------------------------------------------


def test_run_git_returns_stdout(repo):
    assert (
        commit_evidence.run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], str(repo)
        ).strip()
        == "feature"
    )


def test_run_git_returns_empty_text_when_git_fails(tmp_path):
    assert commit_evidence.run_git(["not-a-git-command"], str(tmp_path)) == ""


def test_run_git_returns_empty_text_when_the_directory_does_not_exist(tmp_path):
    assert commit_evidence.run_git(["status"], str(tmp_path / "missing")) == ""


def test_run_git_returns_empty_text_when_git_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert commit_evidence.run_git(["status"], str(tmp_path)) == ""


# ---------------------------------------------------------------------------
# branch_base_sha: None whenever no trunk ref diverges from HEAD
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trunk", ["main", "master"])
def test_the_base_is_the_commit_the_branch_left_trunk_at(trunk, tmp_path):
    root = _repo_on(tmp_path / "repo", trunk)
    seed = _git(root, "rev-parse", trunk)
    _commit(root, "a.py", "feat: work")
    assert commit_evidence.branch_base_sha(str(root)) == seed


def test_the_base_is_none_on_trunk_itself(repo):
    _git(repo, "checkout", "-q", "main")
    assert commit_evidence.branch_base_sha(str(repo)) is None


def test_the_base_is_none_on_a_branch_with_no_commits_past_trunk(repo):
    assert commit_evidence.branch_base_sha(str(repo)) is None


def test_the_base_is_none_when_no_trunk_ref_exists(tmp_path):
    _init(tmp_path, branch="dev")
    _commit(tmp_path, "a.py", "feat: root")
    _commit(tmp_path, "b.py", "feat: next")
    assert commit_evidence.branch_base_sha(str(tmp_path)) is None


def test_the_base_is_none_on_a_detached_head_with_no_trunk_ref(tmp_path):
    _init(tmp_path, branch="dev")
    _commit(tmp_path, "a.py", "feat: root")
    _commit(tmp_path, "b.py", "feat: next")
    _git(tmp_path, "checkout", "-q", "--detach")
    assert commit_evidence.branch_base_sha(str(tmp_path)) is None


def test_the_base_is_none_in_an_empty_repository(tmp_path):
    _init(tmp_path)
    assert commit_evidence.branch_base_sha(str(tmp_path)) is None


def test_the_base_is_none_outside_a_repository(tmp_path):
    assert commit_evidence.branch_base_sha(str(tmp_path)) is None


def test_the_base_is_none_when_git_reports_an_error(repo):
    _commit(repo, "a.py", "feat: work")
    (repo / ".git" / "HEAD").write_text("garbage\n")
    assert commit_evidence.branch_base_sha(str(repo)) is None


def test_the_base_is_none_when_git_is_not_installed(repo, monkeypatch):
    _commit(repo, "a.py", "feat: work")
    monkeypatch.setenv("PATH", str(repo / "no-bin"))
    assert commit_evidence.branch_base_sha(str(repo)) is None


def test_a_remote_tracking_trunk_wins_over_a_lagging_local_one(tmp_path):
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(remote))
    work.mkdir()
    _init(work)
    _git(work, "remote", "add", "origin", str(remote))
    _commit(work, "seed.txt", "chore: seed")
    _git(work, "push", "-q", "origin", "main")
    _commit(work, "ahead.txt", "feat: lands on trunk")
    _git(work, "push", "-q", "origin", "main")
    ahead = _git(work, "rev-parse", "HEAD")
    _git(work, "reset", "-q", "--hard", "HEAD~1")  # local main now lags origin/main
    _git(work, "fetch", "-q", "origin")
    _git(work, "checkout", "-q", "-b", "feature", "origin/main")
    _commit(work, "a.py", "feat: work")
    assert commit_evidence.branch_base_sha(str(work)) == ahead


# ---------------------------------------------------------------------------
# commits_since
# ---------------------------------------------------------------------------


def test_commits_since_lists_lowercased_subjects_and_touched_files(repo):
    seed = _git(repo, "rev-parse", "main")
    _commit(repo, "docs/a.md", "Feat: Add The Parser")
    _commit(repo, "docs/b.md", "fix: second")
    subjects, files = commit_evidence.commits_since(str(repo), seed)
    assert sorted(subjects) == ["feat: add the parser", "fix: second"]
    assert files == {"docs/a.md", "docs/b.md"}


def test_commits_since_is_empty_when_the_branch_has_no_commits_past_the_base(repo):
    seed = _git(repo, "rev-parse", "main")
    assert commit_evidence.commits_since(str(repo), seed) == ([], set())


def test_commits_since_leaves_out_commits_at_or_before_the_base(repo):
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "old.py", "feat: before the branch point")
    _git(repo, "checkout", "-q", "-b", "feature2")
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "new.py", "feat: after")
    subjects, files = commit_evidence.commits_since(str(repo), base)
    assert subjects == ["feat: after"]
    assert files == {"new.py"}


def test_commits_since_leaves_out_merge_commits_from_the_subjects(repo):
    seed = _git(repo, "rev-parse", "main")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "side.py", "feat: side work")
    _git(repo, "checkout", "-q", "feature")
    _commit(repo, "main.py", "feat: main work")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge side", "side")
    subjects, _ = commit_evidence.commits_since(str(repo), seed)
    assert "merge side" not in subjects
    assert sorted(subjects) == ["feat: main work", "feat: side work"]


def test_commits_since_is_empty_for_an_unknown_base(repo):
    assert commit_evidence.commits_since(str(repo), "0" * 40) == ([], set())


def test_commits_since_is_empty_outside_a_repository(repo, tmp_path):
    real_sha = _git(repo, "rev-parse", "HEAD")
    plain = tmp_path / "plain"
    plain.mkdir()
    assert commit_evidence.commits_since(str(plain), real_sha) == ([], set())
    assert commit_evidence.checked_commits_since(str(plain), real_sha) is None


def test_checked_commits_since_matches_commits_since_on_success(repo):
    seed = _git(repo, "rev-parse", "main")
    _commit(repo, "docs/a.md", "feat: parse")
    assert commit_evidence.checked_commits_since(str(repo), seed) == (
        commit_evidence.commits_since(str(repo), seed)
    )


def test_checked_commits_since_is_empty_not_none_for_a_range_with_no_commit(repo):
    seed = _git(repo, "rev-parse", "main")
    assert commit_evidence.checked_commits_since(str(repo), seed) == ([], set())


def test_checked_commits_since_is_none_when_the_file_listing_fails(repo):
    seed = _git(repo, "rev-parse", "main")
    _commit(repo, "docs/a.md", "feat: parse")
    remove_loose_object(repo, _git(repo, "rev-parse", "HEAD^{tree}"))
    # The log still works (it needs commits only); the diff needs the tree.
    subjects, files = commit_evidence.commits_since(str(repo), seed)
    assert subjects == ["feat: parse"] and files == set()
    assert commit_evidence.checked_commits_since(str(repo), seed) is None


def test_checked_commits_since_is_none_for_an_unknown_base(repo):
    assert commit_evidence.checked_commits_since(str(repo), "0" * 40) is None


# ---------------------------------------------------------------------------
# item_backed: the per-item rule
# ---------------------------------------------------------------------------

PLAN = "### Slice 1: Parse\n\n**Files:** `docs/a.md`\n\n## Build Progress\n\n- [x] Slice 1: Parse\n"


def test_an_item_whose_declared_file_a_commit_touched_is_backed():
    assert commit_evidence.item_backed(
        "Slice 1: Parse", PLAN, ["feat: x"], {"docs/a.md"}
    )


def test_an_item_whose_declared_file_no_commit_touched_is_not_backed():
    assert not commit_evidence.item_backed(
        "Slice 1: Parse", PLAN, ["feat: slice 1: parse"], {"docs/b.md"}
    )


def test_a_declared_file_decides_even_when_a_subject_names_the_header():
    # The file rule wins; the subject fallback applies only with no declared files.
    assert not commit_evidence.item_backed(
        "Slice 1: Parse", PLAN, ["slice 1: parse"], set()
    )


def test_a_declared_directory_is_backed_by_a_file_under_it():
    plan = "### Slice 1: Parse\n\n**Files:** `docs/`\n"
    assert commit_evidence.item_backed("Slice 1: Parse", plan, [], {"docs/deep/a.md"})
    assert not commit_evidence.item_backed("Slice 1: Parse", plan, [], {"other/a.md"})


def test_an_item_with_no_declared_files_falls_back_to_the_commit_subject():
    plan = "- [x] Add the parser\n"
    assert commit_evidence.item_backed(
        "Add the parser", plan, ["feat: add the parser now"], set()
    )
    assert not commit_evidence.item_backed(
        "Add the parser", plan, ["feat: other"], {"a.py"}
    )


def test_the_subject_fallback_ignores_the_case_of_the_header():
    assert commit_evidence.item_backed(
        "Add The Parser", "", ["feat: add the parser"], set()
    )


def test_an_inline_layout_slice_reads_its_files_from_the_checkbox_block():
    plan = "- [x] Slice 1: Parse\n\n**Files:** `a.py`\n"
    assert commit_evidence.item_backed("Slice 1: Parse", plan, [], {"a.py"})
    assert not commit_evidence.item_backed(
        "Slice 1: Parse", plan, ["slice 1: parse"], {"b.py"}
    )


def test_an_inline_files_line_after_another_checkbox_belongs_to_that_checkbox():
    plan = "- [x] Slice 1: Parse\n- [x] Slice 2: Build\n\n**Files:** `b.py`\n"
    assert commit_evidence.parse_slice_files(plan, "Slice 1: Parse") == []
    assert commit_evidence.parse_slice_files(plan, "Slice 2: Build") == ["b.py"]
    assert not commit_evidence.item_backed("Slice 1: Parse", plan, [], {"b.py"})


def test_an_item_is_not_backed_when_there_are_no_commits_and_no_files():
    assert not commit_evidence.item_backed("Slice 1: Parse", PLAN, [], set())


# ---------------------------------------------------------------------------
# the declared-files helpers
# ---------------------------------------------------------------------------


def test_declared_paths_are_files_with_an_extension_and_directories():
    text = "`a/b.py`, `src/dir/`, `runHook()`, `SomeClass`"
    assert commit_evidence.extract_declared_paths(text) == ["a/b.py", "src/dir/"]


@pytest.mark.parametrize(
    "path,declared,expected",
    [
        ("a.py", ["a.py"], True),
        ("a.py", ["b.py"], False),
        ("src/x/a.py", ["src/"], True),
        ("srcs/a.py", ["src/"], False),
        ("src/auth/login.py", ["src/auth/*.py"], True),
        ("src/other/login.py", ["src/auth/*.py"], False),
        ("a.py", [], False),
    ],
)
def test_is_path_declared(path, declared, expected):
    assert commit_evidence.is_path_declared(path, declared) is expected


def test_parse_slice_files_reads_the_heading_anchored_files_line():
    plan = "### Slice 2: Build\n\n**Files:** `x.py`\n\n### Slice 3: Other\n\n**Files:** `y.py`\n"
    assert commit_evidence.parse_slice_files(plan, "Slice 2: Build") == ["x.py"]
    assert commit_evidence.parse_slice_files(plan, "Slice 3: Other") == ["y.py"]
    assert commit_evidence.parse_slice_files(plan, "Slice 4: None") == []


def test_parse_slice_files_stops_at_the_next_heading():
    plan = "### Slice 2: Build\n\nno files line\n\n## Next\n\n**Files:** `late.py`\n"
    assert commit_evidence.parse_slice_files(plan, "Slice 2: Build") == []


# ---------------------------------------------------------------------------
# module boundaries
# ---------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_commit_evidence_imports_neither_the_guardian_nor_the_record():
    imported = _imported_modules(_LIB / "commit_evidence.py")
    assert "progress_guardian" not in imported
    assert "feature_record" not in imported


def test_commit_evidence_imports_only_the_standard_library():
    imported = _imported_modules(_LIB / "commit_evidence.py")
    assert imported <= set(sys.stdlib_module_names)


def test_the_guardian_uses_the_one_commit_evidence_module():
    script = (
        f"import sys; sys.path.insert(0, {str(_SCRIPTS)!r})\n"
        "import progress_guardian\n"
        "import commit_evidence\n"
        "assert progress_guardian.commit_evidence is commit_evidence\n"
        "assert [k for k in sys.modules if k.endswith('commit_evidence')] == ['commit_evidence']\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
