"""review_findings_log: fail-open append and category ranking."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import review_findings_log as log


def test_append_then_rank(tmp_path):
    p = tmp_path / "m" / "f.jsonl"
    assert log.append(p, "correctness-review", "off-by-one", "error", 1, True)
    assert log.append(p, "correctness-review", "off-by-one", "error", 2, False)
    assert log.append(p, "naming-review", "magic-value", "suggestion", 1, True)
    ranked = log.rank(log.load(p))
    assert ranked[0] == {"lens": "correctness-review", "category": "off-by-one",
                         "count": 2, "first_pass_fix_rate": 0.5}
    assert ranked[1]["first_pass_fix_rate"] == 1.0


def test_append_is_fail_open(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert log.append(blocker / "sub" / "f.jsonl", "l", "c", "s", 1, False) is False


def test_load_skips_malformed_lines(tmp_path):
    p = tmp_path / "f.jsonl"
    p.write_text('not json\n{"lens":"a","category":"b"}\n[1]\n')
    assert len(log.load(p)) == 1


def test_missing_log_reports_empty(tmp_path):
    assert log.rank(log.load(tmp_path / "none.jsonl")) == []
