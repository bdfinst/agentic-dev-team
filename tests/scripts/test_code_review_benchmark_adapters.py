"""Unit tests for the #821 benchmark harness's Defects4J and BugsJS adapters.

CSV fixtures are real (trimmed) data fetched from the actual datasets this
session — `list_bugs()` is asserted against real column names/formats, not
assumed ones. All checkout/describe/ground-truth calls use an injected
`run_fn` (dependency injection, matching `scripts/agent_calibrate.py`'s
`dispatch_fn` pattern) — no real subprocess or network call is made.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

from adapters import bugsjs_adapter, defects4j_adapter  # noqa: E402

_FIXTURES = _HARNESS_DIR / "fixtures"


class _FakeRun:
    """Injected `run_fn` recording every call; returns a canned CompletedProcess."""

    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.calls: List[dict] = []

    def __call__(self, timeout, argv, **kwargs):
        self.calls.append({"timeout": timeout, "argv": list(argv), "kwargs": kwargs})
        return subprocess.CompletedProcess(
            args=list(argv), returncode=self.returncode, stdout=self.stdout, stderr=""
        )


# ---------------------------------------------------------------------------
# Defects4J
# ---------------------------------------------------------------------------


@pytest.fixture()
def d4j_home(tmp_path: Path) -> Path:
    home = tmp_path / "d4j-home"
    patches_dir = home / "framework" / "projects" / "Lang" / "patches"
    patches_dir.mkdir(parents=True)
    shutil.copy(
        _FIXTURES / "lang-active-bugs.csv", patches_dir.parent / "active-bugs.csv"
    )
    shutil.copy(_FIXTURES / "lang-1.src.patch", patches_dir / "1.src.patch")
    return home


def test_defects4j_list_bugs_real_format(d4j_home: Path) -> None:
    cases = defects4j_adapter.list_bugs("Lang", str(d4j_home))
    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "defects4j:Lang:1"
    assert case.language == "java"
    assert case.ground_truth_files == [
        "src/main/java/org/apache/commons/lang3/math/NumberUtils.java"
    ]
    assert case.extra["revision_buggy"] == "396afc3e4693cfee182efe582455f2d97058c068"
    assert case.description == "https://issues.apache.org/jira/browse/LANG-747"


def test_defects4j_list_bugs_skips_bug_with_no_patch(d4j_home: Path) -> None:
    # active-bugs.csv (from the fixture) lists bug 1 only — no patch for a
    # nonexistent bug id should ever surface, by construction. Sanity-check
    # a genuinely absent project returns [].
    assert defects4j_adapter.list_bugs("NoSuchProject", str(d4j_home)) == []


def test_defects4j_list_projects(d4j_home: Path) -> None:
    assert defects4j_adapter.list_projects(str(d4j_home)) == ["Lang"]


def test_defects4j_detect_false_without_binary(
    d4j_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert defects4j_adapter.detect(str(d4j_home)) is False


def test_defects4j_detect_false_without_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/defects4j")
    assert defects4j_adapter.detect(None) is False
    assert defects4j_adapter.detect("/nonexistent") is False


def test_defects4j_checkout_builds_expected_argv(d4j_home: Path) -> None:
    cases = defects4j_adapter.list_bugs("Lang", str(d4j_home))
    fake = _FakeRun(returncode=0)
    ok = defects4j_adapter.checkout(cases[0], "/tmp/workdir", run_fn=fake)
    assert ok is True
    assert fake.calls[0]["argv"] == [
        "defects4j",
        "checkout",
        "-p",
        "Lang",
        "-v",
        "1b",
        "-w",
        "/tmp/workdir",
    ]


def test_defects4j_checkout_false_on_nonzero_exit(d4j_home: Path) -> None:
    cases = defects4j_adapter.list_bugs("Lang", str(d4j_home))
    fake = _FakeRun(returncode=1)
    assert defects4j_adapter.checkout(cases[0], "/tmp/workdir", run_fn=fake) is False


def test_defects4j_describe_none_on_failure(d4j_home: Path) -> None:
    cases = defects4j_adapter.list_bugs("Lang", str(d4j_home))
    fake = _FakeRun(returncode=1)
    assert defects4j_adapter.describe(cases[0], run_fn=fake) is None


def test_defects4j_describe_returns_stdout_on_success(d4j_home: Path) -> None:
    cases = defects4j_adapter.list_bugs("Lang", str(d4j_home))
    fake = _FakeRun(returncode=0, stdout="Bug info text")
    assert defects4j_adapter.describe(cases[0], run_fn=fake) == "Bug info text"


# ---------------------------------------------------------------------------
# BugsJS
# ---------------------------------------------------------------------------


@pytest.fixture()
def bugsjs_home(tmp_path: Path) -> Path:
    home = tmp_path / "bugsjs-home"
    (home / "Projects" / "Bower").mkdir(parents=True)
    (home / "main.py").write_text("# stub\n", encoding="utf-8")
    shutil.copy(_FIXTURES / "bower-projects.csv", home / "Projects.csv")
    shutil.copy(
        _FIXTURES / "bower-bugs.csv", home / "Projects" / "Bower" / "Bower_bugs.csv"
    )
    return home


def test_bugsjs_detect(bugsjs_home: Path) -> None:
    assert bugsjs_adapter.detect(str(bugsjs_home)) is True
    assert bugsjs_adapter.detect(None) is False
    assert bugsjs_adapter.detect("/nonexistent") is False


def test_bugsjs_list_projects(bugsjs_home: Path) -> None:
    projects = bugsjs_adapter.list_projects(str(bugsjs_home))
    assert "Bower" in projects
    assert "Express" in projects


def test_bugsjs_list_bugs_real_format(bugsjs_home: Path) -> None:
    cases = bugsjs_adapter.list_bugs("Bower", str(bugsjs_home))
    assert len(cases) == 3
    case = cases[0]
    assert case.case_id == "bugsjs:Bower:1"
    assert case.language == "javascript"
    assert case.extra["repo_url"] == "https://github.com/BugsJS/bower"
    # No commit hash / description available from this dataset's CSV.
    assert case.ground_truth_hunks == []


def test_bugsjs_checkout_clones_then_checks_out_parent_tag(bugsjs_home: Path) -> None:
    cases = bugsjs_adapter.list_bugs("Bower", str(bugsjs_home))
    fake = _FakeRun(returncode=0)
    ok = bugsjs_adapter.checkout(cases[0], "/tmp/bower-work", run_fn=fake)
    assert ok is True
    assert fake.calls[0]["argv"] == [
        "git",
        "clone",
        "https://github.com/BugsJS/bower",
        "/tmp/bower-work",
    ]
    assert fake.calls[1]["argv"] == ["git", "checkout", "tags/Bug-1^"]


def test_bugsjs_checkout_false_when_clone_fails(bugsjs_home: Path) -> None:
    cases = bugsjs_adapter.list_bugs("Bower", str(bugsjs_home))
    fake = _FakeRun(returncode=1)
    assert bugsjs_adapter.checkout(cases[0], "/tmp/bower-work", run_fn=fake) is False
    assert len(fake.calls) == 1  # never reaches the checkout call


def test_bugsjs_ground_truth_filters_test_files(bugsjs_home: Path) -> None:
    cases = bugsjs_adapter.list_bugs("Bower", str(bugsjs_home))
    diff_text = """diff --git a/lib/core/resolvers/Resolver.js b/lib/core/resolvers/Resolver.js
--- a/lib/core/resolvers/Resolver.js
+++ b/lib/core/resolvers/Resolver.js
@@ -10,2 +10,3 @@
-old
+new
diff --git a/test/core/resolvers/Resolver.js b/test/core/resolvers/Resolver.js
--- a/test/core/resolvers/Resolver.js
+++ b/test/core/resolvers/Resolver.js
@@ -1,2 +1,2 @@
-old test
+new test
"""
    fake = _FakeRun(returncode=0, stdout=diff_text)
    hunks = bugsjs_adapter.ground_truth(cases[0], "/tmp/bower-work", run_fn=fake)
    assert len(hunks) == 1
    assert hunks[0].file == "lib/core/resolvers/Resolver.js"


def test_bugsjs_ground_truth_empty_on_git_failure(bugsjs_home: Path) -> None:
    cases = bugsjs_adapter.list_bugs("Bower", str(bugsjs_home))
    fake = _FakeRun(returncode=1)
    assert bugsjs_adapter.ground_truth(cases[0], "/tmp/bower-work", run_fn=fake) == []
