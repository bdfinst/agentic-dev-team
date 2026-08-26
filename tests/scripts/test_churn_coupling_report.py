"""Unit tests for scripts/churn_coupling_report.py (issue #2004).

Two things the issue asks be pinned by tests, plus the arithmetic they feed:

1. **The mapping conventions.** The report's whole claim rests on knowing which
   source file a test file is about. A silently-wrong mapping produces a
   confidently-wrong ranking, so every convention (Python, JS/TS, Go, Java, C#),
   every directory rewrite, and both fallback tiers are pinned here.
2. **The shallow-clone refusal.** Churn read off a shallow clone measures clone
   depth. The refusal is exercised against a real `git clone --depth 1`, not a
   mocked `rev-parse`, because the thing under test is whether the script can
   tell a truncated history from a real one.

Plus the property that keeps a mapping miss from becoming a false finding: an
unmapped test file is reported, never scored (scoring it would rank it at 100%
solo -- maximally coupled -- which is exactly backwards).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "churn_coupling_report.py"


def _load():
    spec = importlib.util.spec_from_file_location("churn_coupling_report_under_test", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__], which is absent for a spec-loaded module and
    # makes the decorator raise on the first frozen dataclass.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ccr = _load()


def _commits(*specs):
    """Build Commit objects from (sha, [paths]) pairs, newest first."""
    return [ccr.Commit(sha=sha, paths=frozenset(paths)) for sha, paths in specs]


def _row_by_test(report, path):
    for row in report["rows"]:
        if row.test_file == path:
            return row
    raise AssertionError(f"{path} not in ranked rows: {[r.test_file for r in report['rows']]}")


# ---------------------------------------------------------------------------
# is_test_path
# ---------------------------------------------------------------------------


class TestIsTestPath:
    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_alpha.py",
            "pkg/alpha_test.py",
            "src/foo.test.ts",
            "src/foo.spec.tsx",
            "src/foo.test.js",
            "web/foo.spec.jsx",
            "pkg/foo_test.go",
            "src/test/java/com/example/FooTest.java",
            "src/test/java/com/example/FooSpec.java",
            "src/test/java/com/example/FooIT.java",
            "src/test/java/com/example/TestFoo.java",
            "tests/Foo.Tests/BarTests.cs",
            "tests/Foo.Tests/BarTest.cs",
        ],
    )
    def test_recognized_conventions(self, path):
        assert ccr.is_test_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/alpha.py",
            "tests/conftest.py",
            "tests/fixtures/sample.py",
            "tests/helpers.py",
            "src/foo.ts",
            "pkg/foo.go",
            "src/main/java/com/example/Foo.java",
            "src/Foo/Bar.cs",
            "README.md",
            "testing/utils.py",
        ],
    )
    def test_non_test_files(self, path):
        assert ccr.is_test_path(path) is False

    def test_classification_is_filename_driven_not_directory_driven(self):
        """A fixture living under tests/ is not a test file.

        Directory-driven classification would pull every conftest, fixture, and
        helper into the ranking as an unmapped row, burying the real signal.
        """
        assert ccr.is_test_path("tests/scripts/fixtures/data.py") is False
        assert ccr.is_test_path("tests/scripts/test_data.py") is True


# ---------------------------------------------------------------------------
# subject_basenames
# ---------------------------------------------------------------------------


class TestSubjectBasenames:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("test_alpha.py", "alpha.py"),
            ("alpha_test.py", "alpha.py"),
            ("alpha_test.go", "alpha.go"),
            ("AlphaTest.java", "Alpha.java"),
            ("AlphaTests.java", "Alpha.java"),
            ("AlphaSpec.java", "Alpha.java"),
            ("AlphaIT.java", "Alpha.java"),
            ("TestAlpha.java", "Alpha.java"),
            ("AlphaTests.cs", "Alpha.cs"),
            ("AlphaTest.cs", "Alpha.cs"),
        ],
    )
    def test_first_candidate_per_convention(self, name, expected):
        assert ccr.subject_basenames(name)[0] == expected

    def test_js_prefers_its_own_extension_then_the_family(self):
        candidates = ccr.subject_basenames("wallet.service.spec.ts")
        assert candidates[0] == "wallet.service.ts"
        assert "wallet.service.tsx" in candidates
        assert "wallet.service.js" in candidates
        assert "wallet.service.vue" in candidates

    def test_js_test_and_spec_are_equivalent(self):
        assert ccr.subject_basenames("general.effects.test.ts")[0] == "general.effects.ts"

    def test_unrecognized_name_yields_no_candidates(self):
        assert ccr.subject_basenames("alpha.py") == []
        assert ccr.subject_basenames("README.md") == []


# ---------------------------------------------------------------------------
# subject_dirs / candidate_paths
# ---------------------------------------------------------------------------


class TestSubjectDirs:
    def test_own_directory_comes_first(self):
        """Go's convention is strictly same-directory, and JS commonly co-locates."""
        assert ccr.subject_dirs("pkg/store")[0] == "pkg/store"

    def test_test_segment_is_dropped(self):
        assert "scripts" in ccr.subject_dirs("tests/scripts")

    def test_test_segment_is_rewritten_to_source_trees(self):
        candidates = ccr.subject_dirs("tests/billing")
        assert "billing" in candidates
        assert "src/billing" in candidates

    def test_java_maven_layout(self):
        candidates = ccr.subject_dirs("src/test/java/com/example")
        assert "src/main/java/com/example" in candidates

    def test_dotnet_sibling_test_project(self):
        candidates = ccr.subject_dirs("tests/Billing.Tests/Domain")
        assert "tests/Billing/Domain" in candidates

    def test_candidates_are_deduplicated_and_ordered(self):
        candidates = ccr.subject_dirs("tests/tests")
        assert len(candidates) == len(set(candidates))


class TestCandidatePaths:
    def test_python_tests_dir_to_source_dir(self):
        candidates = ccr.candidate_paths("tests/scripts/test_alpha.py")
        assert "scripts/alpha.py" in candidates
        assert candidates[0] == "tests/scripts/alpha.py"

    def test_go_same_directory(self):
        assert ccr.candidate_paths("pkg/store/cache_test.go")[0] == "pkg/store/cache.go"

    def test_the_test_file_itself_is_never_a_candidate(self):
        assert "tests/test_alpha.py" not in ccr.candidate_paths("tests/test_alpha.py")

    def test_unrecognized_test_name_has_no_candidates(self):
        assert ccr.candidate_paths("tests/helpers.py") == []


# ---------------------------------------------------------------------------
# resolve_subjects
# ---------------------------------------------------------------------------


def _index(paths):
    universe = set(paths)
    by_basename = {}
    for path in universe:
        by_basename.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    return universe, by_basename


class TestResolveSubjects:
    def test_structural_candidate_wins(self):
        universe, by_basename = _index(["scripts/alpha.py", "other/alpha.py"])
        mapping = ccr.resolve_subjects("tests/scripts/test_alpha.py", universe, by_basename)
        assert mapping.subjects == ("scripts/alpha.py",)
        assert mapping.method == "path"

    def test_basename_fallback_when_no_structural_candidate_exists(self):
        """Test trees that mirror nothing structurally still resolve.

        `tests/repo/test_alpha.py` -> `plugins/x/hooks/alpha.py` is this repo's
        own dominant shape, and no directory rewrite reaches it.
        """
        universe, by_basename = _index(["plugins/x/hooks/alpha.py"])
        mapping = ccr.resolve_subjects("tests/repo/test_alpha.py", universe, by_basename)
        assert mapping.subjects == ("plugins/x/hooks/alpha.py",)
        assert mapping.method == "basename"

    def test_ambiguous_basename_keeps_every_match_and_says_so(self):
        universe, by_basename = _index(["a/cost_meter.py", "b/cost_meter.py"])
        mapping = ccr.resolve_subjects("tests/repo/test_cost_meter.py", universe, by_basename)
        assert set(mapping.subjects) == {"a/cost_meter.py", "b/cost_meter.py"}
        assert mapping.method == "basename-ambiguous"

    def test_unmapped_reports_what_it_tried(self):
        universe, by_basename = _index(["src/unrelated.py"])
        mapping = ccr.resolve_subjects("tests/skills/test_phase_3.py", universe, by_basename)
        assert mapping.mapped is False
        assert mapping.subjects == ()
        assert "tests/skills/phase_3.py" in mapping.tried

    def test_a_test_file_never_maps_to_another_test_file(self):
        """The universe is built test-free upstream; this pins the contract."""
        universe, by_basename = _index(["src/alpha.py"])
        mapping = ccr.resolve_subjects("tests/test_alpha.py", universe, by_basename)
        assert all(not ccr.is_test_path(s) for s in mapping.subjects)


# ---------------------------------------------------------------------------
# build_report
# ---------------------------------------------------------------------------


class TestBuildReport:
    def test_co_change_and_solo_arithmetic(self):
        commits = _commits(
            ("c4", ["tests/test_alpha.py"]),
            ("c3", ["tests/test_alpha.py"]),
            ("c2", ["src/alpha.py", "tests/test_alpha.py"]),
            ("c1", ["src/alpha.py", "tests/test_alpha.py"]),
        )
        report = ccr.build_report(commits, {"src/alpha.py"}, min_edits=1, excludes=())
        row = _row_by_test(report, "tests/test_alpha.py")
        assert (row.edits, row.with_subject, row.solo) == (4, 2, 2)
        assert row.solo_ratio == pytest.approx(0.5)

    def test_score_is_the_solo_edit_count(self):
        """The issue's rule is solo-ratio x volume, which reduces to solo count."""
        commits = _commits(
            ("c3", ["tests/test_alpha.py"]),
            ("c2", ["tests/test_alpha.py"]),
            ("c1", ["src/alpha.py", "tests/test_alpha.py"]),
        )
        report = ccr.build_report(commits, {"src/alpha.py"}, min_edits=1, excludes=())
        row = _row_by_test(report, "tests/test_alpha.py")
        assert row.score == row.solo == 2
        assert row.score == pytest.approx(row.solo_ratio * row.edits)

    def test_ranking_puts_the_widest_solo_gap_first(self):
        commits = _commits(
            ("c5", ["tests/test_alpha.py"]),
            ("c4", ["tests/test_alpha.py"]),
            ("c3", ["tests/test_alpha.py"]),
            ("c2", ["src/beta.py", "tests/test_beta.py"]),
            ("c1", ["src/alpha.py", "tests/test_alpha.py", "src/beta.py", "tests/test_beta.py"]),
        )
        report = ccr.build_report(
            commits, {"src/alpha.py", "src/beta.py"}, min_edits=1, excludes=()
        )
        assert [r.test_file for r in report["rows"]] == [
            "tests/test_alpha.py",
            "tests/test_beta.py",
        ]

    def test_solo_ratio_breaks_a_tie_on_solo_count(self):
        commits = _commits(
            ("c4", ["tests/test_alpha.py"]),
            ("c3", ["src/beta.py", "tests/test_beta.py"]),
            ("c2", ["src/beta.py", "tests/test_beta.py"]),
            ("c1", ["tests/test_beta.py"]),
        )
        report = ccr.build_report(
            commits, {"src/alpha.py", "src/beta.py"}, min_edits=1, excludes=()
        )
        assert [r.solo for r in report["rows"]] == [1, 1]
        assert report["rows"][0].test_file == "tests/test_alpha.py"

    def test_unmapped_file_is_listed_and_never_scored(self):
        commits = _commits(
            ("c2", ["tests/skills/test_phase_3.py"]),
            ("c1", ["tests/skills/test_phase_3.py"]),
        )
        report = ccr.build_report(commits, set(), min_edits=1, excludes=())
        assert report["rows"] == []
        assert [u["test_file"] for u in report["unmapped"]] == ["tests/skills/test_phase_3.py"]
        assert report["unmapped"][0]["edits"] == 2
        assert report["unmapped"][0]["tried"]

    def test_min_edits_filters_before_mapping(self):
        commits = _commits(("c1", ["src/alpha.py", "tests/test_alpha.py"]))
        report = ccr.build_report(commits, {"src/alpha.py"}, min_edits=2, excludes=())
        assert report["test_files_seen"] == 1
        assert report["test_files_considered"] == 0
        assert report["rows"] == []

    def test_excluded_paths_are_dropped_from_churn_and_from_the_universe(self):
        commits = _commits(
            ("c2", ["node_modules/pkg/foo.spec.ts", "src/alpha.py", "tests/test_alpha.py"]),
            ("c1", ["src/alpha.py", "tests/test_alpha.py"]),
        )
        report = ccr.build_report(
            commits, {"src/alpha.py"}, min_edits=1, excludes=ccr.DEFAULT_EXCLUDES
        )
        assert [r.test_file for r in report["rows"]] == ["tests/test_alpha.py"]
        assert report["unmapped"] == []

    def test_subject_deleted_from_the_tree_still_resolves_from_history(self):
        """A subject that was deleted mid-window is still the right subject."""
        commits = _commits(
            ("c2", ["tests/test_alpha.py"]),
            ("c1", ["src/alpha.py", "tests/test_alpha.py"]),
        )
        report = ccr.build_report(commits, set(), min_edits=1, excludes=())
        row = _row_by_test(report, "tests/test_alpha.py")
        assert row.subjects == ("src/alpha.py",)
        assert (row.edits, row.with_subject, row.solo) == (2, 1, 1)

    def test_ambiguous_subjects_co_change_on_any_of_them(self):
        commits = _commits(
            ("c2", ["b/cost_meter.py", "tests/repo/test_cost_meter.py"]),
            ("c1", ["a/cost_meter.py", "tests/repo/test_cost_meter.py"]),
        )
        report = ccr.build_report(
            commits, {"a/cost_meter.py", "b/cost_meter.py"}, min_edits=1, excludes=()
        )
        row = _row_by_test(report, "tests/repo/test_cost_meter.py")
        assert row.method == "basename-ambiguous"
        assert (row.with_subject, row.solo) == (2, 0)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _rendered_report(commits, tracked, **kwargs):
    report = ccr.build_report(commits, tracked, min_edits=1, excludes=())
    report.setdefault("window", "90 days")
    report.setdefault("truncated", False)
    report.update(kwargs)
    return report


class TestRendering:
    def test_text_report_shows_counts_and_the_mapping(self):
        report = _rendered_report(
            _commits(
                ("c2", ["tests/test_alpha.py"]),
                ("c1", ["src/alpha.py", "tests/test_alpha.py"]),
            ),
            {"src/alpha.py"},
        )
        text = ccr.render_text(report, top=10)
        assert "tests/test_alpha.py -> src/alpha.py" in text
        assert "commits scanned: 2" in text

    def test_text_report_flags_an_ambiguous_mapping(self):
        report = _rendered_report(
            _commits(("c1", ["a/cost_meter.py", "tests/repo/test_cost_meter.py"])),
            {"a/cost_meter.py", "b/cost_meter.py"},
        )
        assert "[ambiguous mapping]" in ccr.render_text(report, top=10)

    def test_text_report_names_unmapped_files_as_unscored(self):
        report = _rendered_report(_commits(("c1", ["tests/skills/test_phase_3.py"])), set())
        text = ccr.render_text(report, top=10)
        assert "tests/skills/test_phase_3.py" in text
        assert "NOT" in text and "scored" in text

    def test_text_report_flags_a_truncated_window(self):
        report = _rendered_report(
            _commits(("c1", ["src/alpha.py", "tests/test_alpha.py"])), {"src/alpha.py"},
            truncated=True,
        )
        assert "--max-commits truncated the window" in ccr.render_text(report, top=10)

    def test_top_caps_the_rows_shown_not_the_rows_counted(self):
        commits = _commits(
            ("c3", ["tests/test_alpha.py"]),
            ("c2", ["tests/test_beta.py"]),
            ("c1", ["src/alpha.py", "src/beta.py", "tests/test_alpha.py", "tests/test_beta.py"]),
        )
        report = _rendered_report(commits, {"src/alpha.py", "src/beta.py"})
        payload = json.loads(ccr.render_json(report, top=1))
        assert len(payload["rows"]) == 1
        assert payload["test_files_considered"] == 2

    def test_unmapped_overflow_is_named_not_dropped(self):
        commits = _commits(
            ("c1", ["tests/skills/test_one.py", "tests/skills/test_two.py"]),
        )
        report = _rendered_report(commits, set())
        text = ccr.render_text(report, top=1)
        assert "... and 1 more" in text

    def test_json_carries_every_unmapped_file_regardless_of_top(self):
        commits = _commits(
            ("c1", ["tests/skills/test_one.py", "tests/skills/test_two.py"]),
        )
        report = _rendered_report(commits, set())
        payload = json.loads(ccr.render_json(report, top=1))
        assert len(payload["unmapped"]) == 2

    def test_json_row_shape(self):
        report = _rendered_report(
            _commits(
                ("c2", ["tests/test_alpha.py"]),
                ("c1", ["src/alpha.py", "tests/test_alpha.py"]),
            ),
            {"src/alpha.py"},
        )
        payload = json.loads(ccr.render_json(report, top=10))
        assert payload["rows"][0] == {
            "rank": 1,
            "test_file": "tests/test_alpha.py",
            "edits": 2,
            "with_subject": 1,
            "solo": 1,
            "solo_ratio": 0.5,
            "score": 1,
            "subjects": ["src/alpha.py"],
            "match": "path",
        }


# ---------------------------------------------------------------------------
# git integration: full clone works, shallow clone is refused
# ---------------------------------------------------------------------------


def _git(repo, *args):
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_repo(root):
    """A repo whose history encodes a known churn/co-change shape.

    tests/test_alpha.py: 4 edits, 2 with src/alpha.py, 2 solo.
    tests/test_beta.py:  2 edits, 2 with src/beta.py, 0 solo.
    tests/test_ghost.py: 2 edits, no subject anywhere -> unmapped.
    """
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True
    )
    steps = [
        ({"src/alpha.py": "a1", "tests/test_alpha.py": "t1", "src/beta.py": "b1",
          "tests/test_beta.py": "tb1", "tests/test_ghost.py": "g1"}, "seed"),
        ({"tests/test_alpha.py": "t2"}, "test-only change 1"),
        ({"tests/test_alpha.py": "t3"}, "test-only change 2"),
        ({"src/alpha.py": "a2", "tests/test_alpha.py": "t4"}, "behavior change"),
        ({"src/beta.py": "b2", "tests/test_beta.py": "tb2"}, "beta behavior change"),
        ({"tests/test_ghost.py": "g2"}, "ghost churn"),
    ]
    for files, message in steps:
        for rel, text in files.items():
            _write(root, rel, text + "\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", message)
    return root


@pytest.fixture(scope="module")
def full_clone(tmp_path_factory):
    return _seed_repo(tmp_path_factory.mktemp("origin") / "repo")


def _run_cli(argv, capsys):
    code = ccr.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestFullCloneEndToEnd:
    def test_report_matches_the_seeded_history(self, full_clone, capsys):
        code, out, _ = _run_cli(
            ["--repo", str(full_clone), "--since", "3650", "--min-edits", "1", "--json"],
            capsys,
        )
        assert code == 0
        payload = json.loads(out)
        rows = {row["test_file"]: row for row in payload["rows"]}

        alpha = rows["tests/test_alpha.py"]
        assert (alpha["edits"], alpha["with_subject"], alpha["solo"]) == (4, 2, 2)
        assert alpha["subjects"] == ["src/alpha.py"]
        assert alpha["rank"] == 1

        beta = rows["tests/test_beta.py"]
        assert (beta["edits"], beta["with_subject"], beta["solo"]) == (2, 2, 0)

        assert [u["test_file"] for u in payload["unmapped"]] == ["tests/test_ghost.py"]
        assert "tests/test_ghost.py" not in rows

    def test_text_report_is_produced_for_a_full_clone(self, full_clone, capsys):
        code, out, _ = _run_cli(
            ["--repo", str(full_clone), "--since", "3650", "--min-edits", "1"], capsys
        )
        assert code == 0
        assert "tests/test_alpha.py -> src/alpha.py" in out

    def test_a_full_clone_is_not_reported_as_shallow(self, full_clone):
        assert ccr.is_shallow(full_clone) is False

    def test_min_edits_narrows_the_ranking(self, full_clone, capsys):
        code, out, _ = _run_cli(
            ["--repo", str(full_clone), "--since", "3650", "--min-edits", "4", "--json"],
            capsys,
        )
        assert code == 0
        payload = json.loads(out)
        assert [row["test_file"] for row in payload["rows"]] == ["tests/test_alpha.py"]

    def test_empty_window_is_refused_rather_than_reported_as_zero(self, capsys, tmp_path):
        """A window with no commits is a non-answer, not a clean bill of health."""
        empty = tmp_path / "empty"
        empty.mkdir()
        subprocess.run(
            ["git", "init", "-q", "-b", "main", str(empty)], check=True, capture_output=True
        )
        code, _, err = _run_cli(["--repo", str(empty), "--since", "3650"], capsys)
        assert code == 2
        assert "empty-window" in err


@pytest.fixture(scope="module")
def shallow_clone(tmp_path_factory):
    origin = _seed_repo(tmp_path_factory.mktemp("shallow-origin") / "repo")
    target = tmp_path_factory.mktemp("shallow-clone") / "repo"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", origin.as_uri(), str(target)],
        check=True,
        capture_output=True,
    )
    return target


class TestShallowCloneRefusal:
    def test_detected_as_shallow(self, shallow_clone):
        assert ccr.is_shallow(shallow_clone) is True

    def test_cli_refuses_with_exit_code_2(self, shallow_clone, capsys):
        code, out, _err = _run_cli(["--repo", str(shallow_clone), "--since", "3650"], capsys)
        assert code == 2
        assert out == ""

    def test_refusal_names_the_reason_and_the_remedy(self, shallow_clone, capsys):
        _, _, err = _run_cli(["--repo", str(shallow_clone), "--since", "3650"], capsys)
        assert "shallow-clone" in err
        assert "git fetch --unshallow" in err

    def test_refusal_beats_the_report_even_when_history_looks_usable(
        self, shallow_clone, capsys
    ):
        """The point of the gate: a shallow clone CAN produce a number.

        `git log` on a depth-1 clone returns a commit, so without this refusal
        the script would emit a ranking whose churn counts describe clone depth.
        """
        assert ccr.git_log_commits(shallow_clone, since_days=3650)
        code, out, _ = _run_cli(
            ["--repo", str(shallow_clone), "--since", "3650", "--min-edits", "1"], capsys
        )
        assert code == 2
        assert "tests/test_alpha.py" not in out


class TestNonRepoRefusal:
    def test_a_directory_outside_a_repo_is_refused(self, tmp_path, capsys):
        outside = tmp_path / "plain"
        outside.mkdir()
        code, _, err = _run_cli(["--repo", str(outside), "--since", "30"], capsys)
        assert code == 2
        assert "not-a-git-repository" in err


class TestTrackedPaths:
    def test_paths_are_repo_root_relative_from_any_cwd(self, tmp_path, monkeypatch):
        """A subdirectory CWD must not shrink or re-root the subject universe.

        `git ls-files` without --full-name reports CWD-relative paths, which
        would silently miss every structural mapping against `git log`'s
        root-relative ones.
        """
        root = _seed_repo(tmp_path / "cwd-repo")
        monkeypatch.chdir(root / "src")
        assert "src/alpha.py" in ccr.tracked_paths(".")

    def test_report_from_a_subdirectory_still_maps_subjects(self, tmp_path, monkeypatch, capsys):
        root = _seed_repo(tmp_path / "cwd-report-repo")
        monkeypatch.chdir(root / "src")
        code, out, _ = _run_cli(["--repo", ".", "--since", "3650", "--min-edits", "1"], capsys)
        assert code == 0
        assert "tests/test_alpha.py -> src/alpha.py" in out


class TestGitLogParsing:
    def test_merge_commits_are_excluded(self, tmp_path):
        """A merge's --name-only output would double-count the merged side."""
        root = _seed_repo(tmp_path / "merge-repo")
        _git(root, "checkout", "-q", "-b", "side")
        _write(root, "src/alpha.py", "a3\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "side change")
        _git(root, "checkout", "-q", "main")
        _write(root, "docs/note.md", "n\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "main change")
        _git(root, "merge", "-q", "--no-ff", "-m", "merge side", "side")

        commits = ccr.git_log_commits(root, since_days=3650)
        assert all(commit.paths for commit in commits)
        assert len(commits) == 8

    def test_max_commits_caps_the_window(self, tmp_path):
        root = _seed_repo(tmp_path / "capped-repo")
        assert len(ccr.git_log_commits(root, since_days=3650, max_commits=2)) == 2

    def test_paths_with_spaces_survive_parsing(self, tmp_path):
        root = _seed_repo(tmp_path / "spaces-repo")
        _write(root, "src/two words.py", "x\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "spaced path")
        commits = ccr.git_log_commits(root, since_days=3650)
        assert "src/two words.py" in commits[0].paths
