"""Unit tests for skills/code-review/scripts/review_round_log.py (#1624).

The load-bearing piece is `fix_provenance_new` — the judgment-free "the
previous round's fix introduced this finding" signal that makes #1623's
churn-vs-value question answerable. These tests pin the diff interval math
that computes it, plus the row shape `/harness-audit` consumes.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import review_round_log

SIMPLE_DIFF = """diff --git a/src/cache.js b/src/cache.js
index 1111111..2222222 100644
--- a/src/cache.js
+++ b/src/cache.js
@@ -10,6 +10,8 @@ export class Cache {
   get(key) {
     return this.store.get(key)
   }
+
+  has(key) { return this.store.has(key) }

   set(key, value) {
     this.store.set(key, value)
"""


class TestChangedLineIntervals:
    def test_added_lines_produce_new_side_intervals(self):
        intervals = review_round_log.changed_line_intervals(SIMPLE_DIFF)
        # Hunk starts at new-side line 10; three context lines (10,11,12)
        # precede the two added lines, which therefore occupy 13-14.
        assert intervals == {"src/cache.js": [(13, 14)]}

    def test_pure_deletion_contributes_no_interval(self):
        diff = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -5,4 +5,3 @@ def f():
     x = 1
-    y = 2
     return x
"""
        assert review_round_log.changed_line_intervals(diff) == {}

    def test_multiple_files_and_hunks_are_tracked_separately(self):
        diff = """diff --git a/a.ts b/a.ts
--- a/a.ts
+++ b/a.ts
@@ -1,2 +1,3 @@
 const a = 1
+const b = 2
 export {}
@@ -20,2 +21,3 @@
 const c = 3
+const d = 4
 export {}
diff --git a/b.ts b/b.ts
--- a/b.ts
+++ b/b.ts
@@ -7,1 +7,2 @@
+const e = 5
 const f = 6
"""
        intervals = review_round_log.changed_line_intervals(diff)
        assert intervals == {"a.ts": [(2, 2), (22, 22)], "b.ts": [(7, 7)]}

    def test_new_file_against_dev_null_still_records_the_new_side(self):
        diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,3 @@
+import os
+
+print(os)
"""
        assert review_round_log.changed_line_intervals(diff) == {"new.py": [(1, 3)]}

    def test_deleted_file_target_is_skipped(self):
        diff = """diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1,2 +0,0 @@
-import os
-print(os)
"""
        assert review_round_log.changed_line_intervals(diff) == {}

    def test_garbage_input_yields_no_intervals_rather_than_raising(self):
        assert review_round_log.changed_line_intervals("not a diff at all\n@@ broken") == {}
        assert review_round_log.changed_line_intervals("") == {}


class TestFindingProvenance:
    def test_finding_inside_the_fix_delta_is_credited(self):
        intervals = review_round_log.changed_line_intervals(SIMPLE_DIFF)
        assert review_round_log.finding_has_fix_provenance(
            {"file": "src/cache.js", "line": 13}, intervals
        )

    def test_finding_outside_the_fix_delta_is_not_credited(self):
        intervals = review_round_log.changed_line_intervals(SIMPLE_DIFF)
        assert not review_round_log.finding_has_fix_provenance(
            {"file": "src/cache.js", "line": 40}, intervals
        )

    def test_finding_in_an_untouched_file_is_not_credited(self):
        intervals = review_round_log.changed_line_intervals(SIMPLE_DIFF)
        assert not review_round_log.finding_has_fix_provenance(
            {"file": "src/other.js", "line": 13}, intervals
        )

    def test_leading_dot_slash_in_a_finding_path_still_matches(self):
        intervals = review_round_log.changed_line_intervals(SIMPLE_DIFF)
        assert review_round_log.finding_has_fix_provenance(
            {"file": "./src/cache.js", "line": 14}, intervals
        )

    @pytest.mark.parametrize("line", [None, 0, -3, "13", True])
    def test_findings_without_a_usable_line_are_never_credited(self, line):
        # Conservative direction: "somewhere in a touched file" is too weak a
        # claim to score as churn.
        intervals = review_round_log.changed_line_intervals(SIMPLE_DIFF)
        assert not review_round_log.finding_has_fix_provenance(
            {"file": "src/cache.js", "line": line}, intervals
        )

    def test_count_aggregates_over_a_finding_list(self):
        intervals = review_round_log.changed_line_intervals(SIMPLE_DIFF)
        findings = [
            {"file": "src/cache.js", "line": 13},
            {"file": "src/cache.js", "line": 14},
            {"file": "src/cache.js", "line": 99},
            "not-a-dict",
        ]
        assert review_round_log.count_fix_provenance(findings, intervals) == 2


class TestSeverityBreakdown:
    def test_counts_the_three_buckets(self):
        findings = [
            {"severity": "error"},
            {"severity": "warning"},
            {"severity": "Warning"},
            {"severity": "suggestion"},
        ]
        assert review_round_log.severity_breakdown(findings) == {
            "errors": 1,
            "warnings": 2,
            "suggestions": 1,
        }

    def test_unknown_severities_are_dropped_so_the_sum_stays_meaningful(self):
        assert review_round_log.severity_breakdown([{"severity": "nit"}, {}]) == {
            "errors": 0,
            "warnings": 0,
            "suggestions": 0,
        }


class TestBuildRoundEntry:
    def test_round_one_has_no_fix_diff_and_therefore_no_provenance(self):
        entry = review_round_log.build_round_entry(
            round_number=1,
            agents_run=["doc-review", "correctness-review", "doc-review"],
            findings_new=[{"file": "a.js", "line": 3, "severity": "warning"}],
            findings_carried=0,
            dispatch_purpose="discovery",
            outcome="fixed",
        )
        assert entry["round"] == 1
        assert entry["source"] == "code-review"
        assert entry["agents_run"] == ["correctness-review", "doc-review"]
        assert entry["findings_new"] == 1
        assert entry["fix_provenance_new"] == 0
        assert entry["dispatch_purpose"] == "discovery"
        assert entry["severity_breakdown"] == {"errors": 0, "warnings": 1, "suggestions": 0}

    def test_round_two_credits_provenance_for_findings_inside_the_fix(self):
        entry = review_round_log.build_round_entry(
            round_number=2,
            agents_run=["correctness-review"],
            findings_new=[
                {"file": "src/cache.js", "line": 13, "severity": "error"},
                {"file": "src/cache.js", "line": 200, "severity": "warning"},
            ],
            findings_carried=1,
            dispatch_purpose="verification",
            outcome="fixed",
            fix_diff=SIMPLE_DIFF,
        )
        assert entry["findings_new"] == 2
        assert entry["findings_carried"] == 1
        assert entry["fix_provenance_new"] == 1

    @pytest.mark.parametrize("purpose", ["discovery", "verification", "closing"])
    def test_every_declared_dispatch_purpose_is_accepted(self, purpose):
        entry = review_round_log.build_round_entry(
            round_number=1,
            agents_run=[],
            findings_new=[],
            findings_carried=0,
            dispatch_purpose=purpose,
            outcome="no-op",
        )
        assert entry["dispatch_purpose"] == purpose

    def test_unknown_purpose_or_outcome_is_rejected(self):
        with pytest.raises(ValueError):
            review_round_log.build_round_entry(
                round_number=1,
                agents_run=[],
                findings_new=[],
                findings_carried=0,
                dispatch_purpose="rubber-stamp",
                outcome="no-op",
            )
        with pytest.raises(ValueError):
            review_round_log.build_round_entry(
                round_number=1,
                agents_run=[],
                findings_new=[],
                findings_carried=0,
                dispatch_purpose="discovery",
                outcome="shipped",
            )

    def test_row_carries_no_code_or_message_content(self):
        entry = review_round_log.build_round_entry(
            round_number=2,
            agents_run=["correctness-review"],
            findings_new=[
                {
                    "file": "src/secret.js",
                    "line": 13,
                    "severity": "error",
                    "message": "API_KEY = 'sk-live-do-not-log-me'",
                }
            ],
            findings_carried=0,
            dispatch_purpose="verification",
            outcome="fixed",
            fix_diff=SIMPLE_DIFF,
        )
        serialized = json.dumps(entry)
        assert "sk-live-do-not-log-me" not in serialized
        assert "src/secret.js" not in serialized


class TestAppendRound:
    def test_writes_one_json_line_to_the_project_metrics_stream(self, tmp_path):
        entry = review_round_log.build_round_entry(
            round_number=1,
            agents_run=["doc-review"],
            findings_new=[],
            findings_carried=0,
            dispatch_purpose="discovery",
            outcome="no-op",
        )
        written = review_round_log.append_round(entry, cwd=tmp_path)
        assert written is not None
        assert written.name == "review-value.jsonl"
        lines = written.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["source"] == "code-review"

    def test_write_failure_is_fail_open(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            review_round_log.artifact_paths,
            "resolve_file",
            lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")),
        )
        assert review_round_log.append_round({"a": 1}, cwd=tmp_path) is None


class TestCli:
    def test_cli_appends_a_round_and_echoes_it(self, tmp_path):
        findings = tmp_path / "findings.json"
        findings.write_text(
            json.dumps([{"file": "src/cache.js", "line": 13, "severity": "error"}]),
            encoding="utf-8",
        )
        diff = tmp_path / "fix.diff"
        diff.write_text(SIMPLE_DIFF, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "review_round_log.py"),
                "--round",
                "2",
                "--agents",
                "correctness-review,doc-review",
                "--findings",
                str(findings),
                "--carried",
                "1",
                "--purpose",
                "verification",
                "--outcome",
                "fixed",
                "--fix-diff",
                str(diff),
                "--cwd",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        echoed = json.loads(result.stdout)
        assert echoed["round"] == 2
        assert echoed["fix_provenance_new"] == 1
        assert echoed["agents_run"] == ["correctness-review", "doc-review"]

        stream = tmp_path / ".claude" / "metrics" / "review-value.jsonl"
        assert json.loads(stream.read_text(encoding="utf-8").strip())["round"] == 2

    def test_dry_run_writes_nothing(self, tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPTS_DIR / "review_round_log.py"),
                "--round",
                "1",
                "--purpose",
                "discovery",
                "--outcome",
                "no-op",
                "--cwd",
                str(tmp_path),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout)["round"] == 1
        assert not (tmp_path / ".claude" / "metrics" / "review-value.jsonl").exists()
