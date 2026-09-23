"""Tests for scripts/verdict_scope.py (#2167).

Covers the pure resolver (`resolve_dispatch`) directly with synthetic
verdict rows, plus an end-to-end CLI round trip through a real
`review_verdicts.emit_review_verdict()`-written ledger, so the "identical
findings, cold vs warm" claim in #2167's acceptance criteria is exercised
against the SAME writer the production hook uses, not a hand-rolled stand-in.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SCRIPTS_DIR = _PLUGIN_ROOT / "scripts"
_HOOKS_LIB_DIR = _PLUGIN_ROOT / "hooks" / "lib"
for _p in (_SCRIPTS_DIR, _HOOKS_LIB_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import verdict_scope  # type: ignore[import-not-found]
from review_verdicts import (  # type: ignore[import-not-found]
    emit_review_verdict,
    hash_file,
    load_verdicts,
)

_SCRIPT = _SCRIPTS_DIR / "verdict_scope.py"


def _run_cli(root: Path, lens_files: dict) -> dict:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root), "--lens-files", json.dumps(lens_files)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# resolve_dispatch — pure resolver
# ---------------------------------------------------------------------------


def test_no_verdicts_dispatches_everything() -> None:
    result = verdict_scope.resolve_dispatch(
        {"security-review": ["a.py", "b.py"]}, [], {"a.py": "h1", "b.py": "h2"}
    )
    assert result == {
        "toDispatch": {"security-review": ["a.py", "b.py"]},
        "skipped": {},
        "fullySkippedLenses": [],
    }


def test_exact_pass_match_is_skipped() -> None:
    row = {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "pass"}
    result = verdict_scope.resolve_dispatch(
        {"security-review": ["a.py"]}, [row], {"a.py": "h1"}
    )
    assert result["toDispatch"] == {}
    assert result["fullySkippedLenses"] == ["security-review"]
    assert result["skipped"]["security-review"] == [{"file": "a.py", "verdict": row}]


def test_findings_outcome_is_not_skipped() -> None:
    row = {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "findings"}
    result = verdict_scope.resolve_dispatch(
        {"security-review": ["a.py"]}, [row], {"a.py": "h1"}
    )
    assert result["toDispatch"] == {"security-review": ["a.py"]}
    assert result["skipped"] == {}
    assert result["fullySkippedLenses"] == []


def test_changed_content_hash_is_not_skipped() -> None:
    """A `pass` row for the file's OLD content must never suppress a
    dispatch against its current, different content."""
    row = {"lens": "security-review", "file_path": "a.py", "file_content_hash": "old-hash", "outcome": "pass"}
    result = verdict_scope.resolve_dispatch(
        {"security-review": ["a.py"]}, [row], {"a.py": "new-hash"}
    )
    assert result["toDispatch"] == {"security-review": ["a.py"]}


def test_pass_row_for_a_different_lens_does_not_cross_apply() -> None:
    row = {"lens": "correctness-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "pass"}
    result = verdict_scope.resolve_dispatch(
        {"security-review": ["a.py"]}, [row], {"a.py": "h1"}
    )
    assert result["toDispatch"] == {"security-review": ["a.py"]}


def test_unhashable_file_is_never_skipped_even_with_a_pass_row() -> None:
    """Fail-closed: a file this run couldn't hash (deleted, unreadable) must
    always dispatch, regardless of what the ledger says about its (now
    unverifiable) prior content."""
    row = {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "pass"}
    result = verdict_scope.resolve_dispatch(
        {"security-review": ["a.py"]}, [row], {"a.py": None}
    )
    assert result["toDispatch"] == {"security-review": ["a.py"]}
    assert result["skipped"] == {}


def test_most_recent_row_wins_pass_then_later_findings() -> None:
    rows = [
        {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "pass"},
        {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "findings"},
    ]
    result = verdict_scope.resolve_dispatch({"security-review": ["a.py"]}, rows, {"a.py": "h1"})
    assert result["toDispatch"] == {"security-review": ["a.py"]}


def test_most_recent_row_wins_findings_then_later_pass() -> None:
    rows = [
        {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "findings"},
        {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "pass"},
    ]
    result = verdict_scope.resolve_dispatch({"security-review": ["a.py"]}, rows, {"a.py": "h1"})
    assert result["toDispatch"] == {}
    assert result["fullySkippedLenses"] == ["security-review"]


def test_partial_skip_keeps_lens_in_todispatch_with_only_the_remaining_files() -> None:
    row = {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "pass"}
    result = verdict_scope.resolve_dispatch(
        {"security-review": ["a.py", "b.py"]}, [row], {"a.py": "h1", "b.py": "h2"}
    )
    assert result["toDispatch"] == {"security-review": ["b.py"]}
    assert result["fullySkippedLenses"] == []
    assert result["skipped"]["security-review"] == [{"file": "a.py", "verdict": row}]


def test_lens_with_no_candidate_files_is_absent_from_every_output() -> None:
    result = verdict_scope.resolve_dispatch({"security-review": []}, [], {})
    assert result == {"toDispatch": {}, "skipped": {}, "fullySkippedLenses": []}


def test_a_stale_version_row_already_excluded_upstream_is_not_skipped() -> None:
    """`load_verdicts` is what filters stale `plugin_version` rows (see its
    own docstring) -- this module never sees them. Simulate that by simply
    not including a stale row in `verdicts`, proving the resolver dispatches
    when no usable row survives that upstream filter."""
    result = verdict_scope.resolve_dispatch({"security-review": ["a.py"]}, [], {"a.py": "h1"})
    assert result["toDispatch"] == {"security-review": ["a.py"]}


# ---------------------------------------------------------------------------
# compute_file_hashes
# ---------------------------------------------------------------------------


def test_compute_file_hashes_maps_missing_file_to_none(tmp_path: Path) -> None:
    hashes = verdict_scope.compute_file_hashes(["missing.py"], tmp_path)
    assert hashes == {"missing.py": None}


def test_compute_file_hashes_matches_review_verdicts_hash_file(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    hashes = verdict_scope.compute_file_hashes(["a.py"], tmp_path)
    assert hashes["a.py"] == hash_file(tmp_path / "a.py")


def test_compute_file_hashes_normalizes_a_dot_slash_prefix(tmp_path: Path) -> None:
    """#2167 review (correctness/security/arch): the raw key must still
    hash the real file even when spelled with a `./` prefix."""
    (tmp_path / "a.py").write_text("x = 1\n")
    hashes = verdict_scope.compute_file_hashes(["./a.py"], tmp_path)
    assert hashes["./a.py"] == hash_file(tmp_path / "a.py")


def test_compute_file_hashes_never_hashes_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("evil\n")
    root = tmp_path / "repo"
    root.mkdir()
    traversal = os.path.relpath(outside, root)
    assert verdict_scope.compute_file_hashes([traversal], root) == {traversal: None}


# ---------------------------------------------------------------------------
# _load_json_arg (#2167 correctness review)
# ---------------------------------------------------------------------------


def test_load_json_arg_parses_inline_json_over_path_max(tmp_path: Path) -> None:
    """A realistic multi-lens, multi-file `--lens-files` payload is well
    over Linux's PATH_MAX (4096) -- the previous `Path(value).exists()`
    check-path-first order raised `ENAMETOOLONG` on a string this size
    instead of falling through to a JSON parse."""
    big = json.dumps({"security-review": [f"file{i}.py" for i in range(300)]})
    assert len(big) > 4096
    parsed = verdict_scope._load_json_arg(big)
    assert len(parsed["security-review"]) == 300


def test_load_json_arg_still_reads_a_real_file_path(tmp_path: Path) -> None:
    payload = {"security-review": ["a.py"]}
    path = tmp_path / "lens-files.json"
    path.write_text(json.dumps(payload))
    assert verdict_scope._load_json_arg(str(path)) == payload


def test_cli_accepts_lens_files_from_a_file_path(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n")
    path = tmp_path / "lens-files.json"
    path.write_text(json.dumps({"security-review": ["a.py"]}))
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--lens-files", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(result.stdout)
    assert out["toDispatch"] == {"security-review": ["a.py"]}


# ---------------------------------------------------------------------------
# _canonicalize_lens_files (#2167 correctness/security/arch review)
# ---------------------------------------------------------------------------


def test_canonicalize_lens_files_normalizes_a_dot_slash_prefix(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n")
    result = verdict_scope._canonicalize_lens_files({"security-review": ["./a.py"]}, tmp_path)
    assert result == {"security-review": ["a.py"]}


def test_canonicalize_lens_files_keeps_an_unresolvable_path_as_an_unmatchable_placeholder(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text("evil\n")
    root = tmp_path / "repo"
    root.mkdir()
    traversal = os.path.relpath(outside, root)
    result = verdict_scope._canonicalize_lens_files({"security-review": [traversal]}, root)
    assert result == {"security-review": [traversal]}


def test_cli_matches_a_ledger_row_when_caller_passes_a_dot_slash_prefixed_path(
    tmp_path: Path,
) -> None:
    """The end-to-end proof that the writer's canonical form and the
    reader's now-canonicalized input agree: a caller spelling the same file
    `./a.py` still finds the real, canonically-keyed ledger row."""
    a = tmp_path / "a.py"
    a.write_text("a\n")
    emit_review_verdict(tmp_path, "security-review", "a.py", hash_file(a), "pass")

    out = _run_cli(tmp_path, {"security-review": ["./a.py"]})
    assert out["toDispatch"] == {}
    assert out["fullySkippedLenses"] == ["security-review"]
    assert out["skipped"]["security-review"][0]["file"] == "a.py"


# ---------------------------------------------------------------------------
# CLI round trip, and the "identical findings cold vs warm" proof
# ---------------------------------------------------------------------------


def test_cli_cold_run_dispatches_every_candidate(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a\n")
    (tmp_path / "b.py").write_text("b\n")
    out = _run_cli(tmp_path, {"security-review": ["a.py", "b.py"], "doc-review": ["a.py"]})
    assert set(out["toDispatch"]["security-review"]) == {"a.py", "b.py"}
    assert out["toDispatch"]["doc-review"] == ["a.py"]
    assert out["fullySkippedLenses"] == []


def test_gate_built_to_fail_a_saboteur_always_pass_check_fails_this_suite() -> None:
    """Per this repo's own rule ('a gate that cannot fail is worse than no
    gate' -- root CLAUDE.md), confirm `resolve_dispatch` can actually FAIL a
    test rather than vacuously pass everything: a saboteur that always
    treats a match as a skip (ignoring the outcome) must diverge from the
    correct resolver on the findings-outcome case above."""

    def _saboteur_always_skip_on_any_match(lens_files, verdicts, file_hashes):
        to_dispatch: dict[str, list[str]] = {}
        skipped: dict[str, list[dict]] = {}
        for lens, files in lens_files.items():
            for file_path in files:
                file_hash = file_hashes.get(file_path)
                match = next(
                    (
                        row
                        for row in verdicts
                        if row.get("lens") == lens
                        and row.get("file_path") == file_path
                        and row.get("file_content_hash") == file_hash
                    ),
                    None,
                )
                if match is not None:
                    skipped.setdefault(lens, []).append({"file": file_path, "verdict": match})
                else:
                    to_dispatch.setdefault(lens, []).append(file_path)
        return {"toDispatch": to_dispatch, "skipped": skipped, "fullySkippedLenses": []}

    row = {"lens": "security-review", "file_path": "a.py", "file_content_hash": "h1", "outcome": "findings"}
    correct = verdict_scope.resolve_dispatch({"security-review": ["a.py"]}, [row], {"a.py": "h1"})
    saboteur = _saboteur_always_skip_on_any_match({"security-review": ["a.py"]}, [row], {"a.py": "h1"})

    assert correct["toDispatch"] == {"security-review": ["a.py"]}
    assert saboteur["toDispatch"] == {}
    assert correct != saboteur


def test_cli_warm_run_after_real_pass_verdicts_skips_unchanged_files_only(tmp_path: Path) -> None:
    """The full proof this slice's acceptance criteria demand: a fixture
    reviewed with the ledger cold (everything dispatches), then warm after
    ONE file changes, dispatches only the lenses/files touching that one
    changed file -- using the real `emit_review_verdict` writer, not a
    synthetic row, so this proves the CLI's read side actually agrees with
    the production write side."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("a\n")
    b.write_text("b\n")

    cold = _run_cli(tmp_path, {"security-review": ["a.py", "b.py"]})
    assert set(cold["toDispatch"]["security-review"]) == {"a.py", "b.py"}

    # Simulate both files having been reviewed and cleared by the real
    # writer (as `hooks/review_verdict_recorder.py` would after a genuine
    # dispatch that returned zero findings for either file).
    emit_review_verdict(tmp_path, "security-review", "a.py", hash_file(a), "pass")
    emit_review_verdict(tmp_path, "security-review", "b.py", hash_file(b), "pass")

    # Nothing changed: a second run dispatches zero lenses, and reports why.
    unchanged = _run_cli(tmp_path, {"security-review": ["a.py", "b.py"]})
    assert unchanged["toDispatch"] == {}
    assert unchanged["fullySkippedLenses"] == ["security-review"]
    matched_files = {entry["file"] for entry in unchanged["skipped"]["security-review"]}
    assert matched_files == {"a.py", "b.py"}

    # Touch one file: only that file's lens dispatch needs to re-run.
    b.write_text("b-changed\n")
    warm = _run_cli(tmp_path, {"security-review": ["a.py", "b.py"]})
    assert warm["toDispatch"] == {"security-review": ["b.py"]}
    assert warm["skipped"]["security-review"] == [
        {
            "file": "a.py",
            "verdict": {
                "lens": "security-review",
                "file_path": "a.py",
                "file_content_hash": hash_file(a),
                "outcome": "pass",
                "plugin_version": load_verdicts(tmp_path)[0]["plugin_version"],
                "ts": load_verdicts(tmp_path)[0]["ts"],
            },
        }
    ]
