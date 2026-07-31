"""Unit tests for the normalized gate hash and its carry-forward lens (#1627).

Two layers:
  1. `normalize_patch` / `normalized_gate_hash` — what counts as cosmetic,
     and (more importantly) what does NOT.
  2. `pre_commit_review.py` invoked as a subprocess — the gate's real
     behavior: a whitespace-only re-stage carries corroboration forward with
     an audit event; a single non-whitespace source change is blocked exactly
     as before; a doc-file delta alongside corroborated code is allowed.
"""

from __future__ import annotations

import importlib.util as _importlib_util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_HOOK = _PLUGIN_ROOT / "hooks" / "pre_commit_review.py"
_LIB_DIR = _PLUGIN_ROOT / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

_TESTS_LIB = Path(__file__).resolve().parents[2] / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import review_gate_hash as _rgh  # type: ignore[import-not-found]
import review_gate_normalized_hash as ngh  # type: ignore[import-not-found]
from hermetic import hermetic_git_env  # type: ignore[import-not-found]

_pcr_spec = _importlib_util.spec_from_file_location("pcr_normalized", _HOOK)
assert _pcr_spec is not None and _pcr_spec.loader is not None
_pcr = _importlib_util.module_from_spec(_pcr_spec)
_pcr_spec.loader.exec_module(_pcr)


# --- layer 1: normalization semantics -------------------------------------


def _patch(path: str, removed: list, added: list) -> str:
    lines = [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}", "@@ -1,2 +1,2 @@"]
    lines += [f"-{ln}" for ln in removed]
    lines += [f"+{ln}" for ln in added]
    return "\n".join(lines) + "\n"


class TestNormalizePatch:
    def test_indentation_only_change_normalizes_away(self):
        a = _patch("src/a.js", ["    x = 1"], ["        x = 1"])
        b = _patch("src/a.js", ["  x = 1"], ["\tx = 1"])
        assert ngh.normalize_patch(a) == ngh.normalize_patch(b) == ""

    def test_a_real_source_change_does_not_normalize_away(self):
        cosmetic = ngh.normalize_patch(_patch("src/a.js", ["x = 1"], ["    x = 1"]))
        real = ngh.normalize_patch(_patch("src/a.js", ["x = 1"], ["x = 2"]))
        assert cosmetic == ""
        assert real != ""
        assert real != cosmetic

    def test_reindenting_a_file_with_other_real_changes_still_matches(self):
        """A reindent must be invariant per line, not merely when the file's
        entire delta is whitespace — otherwise a reformat riding alongside a
        reviewed change still voids corroboration."""
        before = _patch("src/a.js", ["    x = 1"], ["    x = 2"])
        after = _patch("src/a.js", ["  x = 1"], ["        x = 2"])
        assert ngh.normalize_patch(before) == ngh.normalize_patch(after) != ""

    def test_interior_whitespace_is_never_collapsed(self):
        """Collapsing interior whitespace would make `a  b` and `a b` hash
        identically. That is a behavior change reading as cosmetic."""
        assert ngh.normalize_patch(_patch("src/a.js", ["x = a  + b"], ["x = a + b"])) != ""

    def test_a_string_literal_change_is_never_cosmetic(self):
        """The load-bearing security property: any quote-bearing line is
        compared byte-exactly, so no string edit can ride the carry-forward."""
        changed = ngh.normalize_patch(
            _patch("src/a.js", ['    s = "a  b"'], ['        s = "a b"'])
        )
        assert changed != "", "a string-literal edit must survive normalization"

    def test_reindenting_a_quote_bearing_line_also_survives(self):
        # Errs closed: a genuine indentation fix on a quoted line costs a
        # re-dispatch rather than weakening the gate.
        assert ngh.normalize_patch(_patch("src/a.js", ['s = "x"'], ['    s = "x"'])) != ""

    @pytest.mark.parametrize("path", ["src/a.py", "conf/x.yaml", "Main.hs", "deploy.yml"])
    def test_indentation_is_never_collapsed_in_indent_significant_languages(self, path):
        """Dedenting a Python line moves it out of its block — a control-flow
        change that must never read as cosmetic."""
        assert ngh.normalize_patch(_patch(path, ["    return total"], ["return total"])) != ""

    @pytest.mark.parametrize("path", ["Makefile", "src/thing.unknownext", "bin/run"])
    def test_unknown_and_extensionless_files_are_compared_byte_exactly(self, path):
        """The safe default for 'is this language's indentation meaningless?'
        is no — an extension this module has never heard of is not one it can
        prove is brace-delimited."""
        assert ngh.normalize_patch(_patch(path, ["\tfoo"], ["        foo"])) != ""

    def test_the_two_extension_sets_do_not_overlap(self):
        assert not (
            ngh._INDENT_SIGNIFICANT_EXTENSIONS & ngh._WHITESPACE_INSIGNIFICANT_EXTENSIONS
        )

    def test_doc_file_hunks_are_dropped(self):
        assert ngh.normalize_patch(_patch("README.md", ["old"], ["new"])) == ""
        assert ngh.normalize_patch(_patch("docs/guide.md", ["old"], ["new"])) == ""

    @pytest.mark.parametrize(
        "path",
        [
            "agents/correctness-review.md",
            "skills/code-review/SKILL.md",
            ".claude/settings.json",
            "CLAUDE.md",
            "knowledge/telemetry-schema.md",
        ],
    )
    def test_functional_claude_config_is_never_dropped_as_documentation(self, path):
        """The carve-out that makes this lens safe: a 'cosmetic' edit to
        enforcement machinery can never ride the carry-forward."""
        assert ngh.normalize_patch(_patch(path, ["old"], ["new"])) != ""

    def test_a_doc_edit_alongside_a_code_change_keeps_only_the_code(self):
        combined = _patch("README.md", ["a"], ["b"]) + _patch("src/a.js", ["x = 1"], ["x = 2"])
        code_only = _patch("src/a.js", ["x = 1"], ["x = 2"])
        assert ngh.normalize_patch(combined) == ngh.normalize_patch(code_only)

    def test_file_order_does_not_change_the_result(self):
        one = _patch("src/a.js", ["x = 1"], ["x = 2"]) + _patch("src/b.js", ["y = 1"], ["y = 2"])
        two = _patch("src/b.js", ["y = 1"], ["y = 2"]) + _patch("src/a.js", ["x = 1"], ["x = 2"])
        assert ngh.normalize_patch(one) == ngh.normalize_patch(two)

    def test_none_input_fails_closed(self):
        assert ngh.normalize_patch(None) is None

    def test_hash_of_a_non_repo_is_none_not_an_empty_digest(self, tmp_path):
        """An empty-input digest would be a CONSTANT across every broken-git
        invocation — exactly the subject-binding bypass the raw hash's
        docstring warns about."""
        assert ngh.normalized_gate_hash(tmp_path) is None


class TestNormalizedGateHashAgainstRealGit:
    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("function f() {\n  return 1\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)
        return tmp_path

    def test_reindenting_staged_code_leaves_the_normalized_hash_unchanged(self, repo):
        env = hermetic_git_env(home=repo)
        (repo / "a.js").write_text("function f() {\n  return 2\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=repo, env=env, check=True)
        before_raw = _rgh.review_gate_hash(repo)
        before_norm = ngh.normalized_gate_hash(repo)

        (repo / "a.js").write_text("function f() {\n      return 2\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=repo, env=env, check=True)
        assert _rgh.review_gate_hash(repo) != before_raw, "raw hash must change"
        assert ngh.normalized_gate_hash(repo) == before_norm, "normalized hash must not"

    def test_adding_a_markdown_file_leaves_the_normalized_hash_unchanged(self, repo):
        env = hermetic_git_env(home=repo)
        (repo / "a.js").write_text("function f() {\n  return 2\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=repo, env=env, check=True)
        before_norm = ngh.normalized_gate_hash(repo)

        (repo / "NOTES.md").write_text("some notes\n")
        subprocess.run(["git", "add", "NOTES.md"], cwd=repo, env=env, check=True)
        assert ngh.normalized_gate_hash(repo) == before_norm

    def test_a_real_code_change_changes_the_normalized_hash(self, repo):
        env = hermetic_git_env(home=repo)
        (repo / "a.js").write_text("function f() {\n  return 2\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=repo, env=env, check=True)
        before_norm = ngh.normalized_gate_hash(repo)

        (repo / "a.js").write_text("function f() {\n  return 3\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=repo, env=env, check=True)
        assert ngh.normalized_gate_hash(repo) != before_norm


# --- layer 2: the gate lens, end to end -----------------------------------


def _run_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    proc_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    return subprocess.run(
        ["python3", str(_HOOK)],
        input=json.dumps(payload),
        env=proc_env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _commit_payload(cwd: Path) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m wip"},
        "cwd": str(cwd),
        "session_id": "s1",
    }


def _seed_dispatches(repo: Path, agents: list, raw: str, normalized: str | None) -> None:
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with log.open("a", encoding="utf-8") as fh:
        for agent in agents:
            event = {
                "ts": now,
                "hook": "agent_dispatch_ledger",
                "tool": "Agent",
                "decision": "record",
                "matched_rule": agent,
                "plugin_version": "0.0.0",
                "subject_hash": raw,
            }
            if normalized:
                event["subject_hash_normalized"] = normalized
            fh.write(json.dumps(event) + "\n")


def _write_gate(repo: Path, raw: str, normalized: str | None) -> None:
    gate = repo / ".claude" / "memory" / ".review-passed"
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_text(f"{raw}\n{normalized}\n" if normalized else f"{raw}\n")


@pytest.fixture
def reviewed_repo(tmp_path: Path) -> Path:
    """A repo where a genuine 2-agent review just corroborated the staged
    content, with both hashes recorded."""
    env = hermetic_git_env(home=tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
    (tmp_path / "a.js").write_text("function f() {\n  return 1\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)

    (tmp_path / "a.js").write_text("function f() {\n  return 2\n}\n")
    subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)

    raw = _rgh.review_gate_hash(tmp_path)
    normalized = ngh.normalized_gate_hash(tmp_path)
    _seed_dispatches(tmp_path, ["correctness-review", "doc-review"], raw, normalized)
    _write_gate(tmp_path, raw, normalized)
    return tmp_path


def _boundary_rules(repo: Path) -> list:
    log = repo / ".claude" / "metrics" / "boundary-events.jsonl"
    if not log.is_file():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line).get("matched_rule"))
        except ValueError:
            continue
    return out


class TestCarryForwardLens:
    def test_baseline_matching_hash_still_passes(self, reviewed_repo):
        assert _run_hook(_commit_payload(reviewed_repo), reviewed_repo).returncode == 0

    def test_whitespace_only_restage_carries_corroboration_forward(self, reviewed_repo):
        env = hermetic_git_env(home=reviewed_repo)
        (reviewed_repo / "a.js").write_text("function f() {\n      return 2\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=reviewed_repo, env=env, check=True)

        result = _run_hook(_commit_payload(reviewed_repo), reviewed_repo)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "cosmetic-delta-carry-forward" in _boundary_rules(reviewed_repo), (
            "the pass path must always leave an audit event"
        )

    def test_doc_file_delta_alongside_corroborated_code_is_allowed(self, reviewed_repo):
        env = hermetic_git_env(home=reviewed_repo)
        (reviewed_repo / "NOTES.md").write_text("notes\n")
        subprocess.run(["git", "add", "NOTES.md"], cwd=reviewed_repo, env=env, check=True)

        result = _run_hook(_commit_payload(reviewed_repo), reviewed_repo)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "cosmetic-delta-carry-forward" in _boundary_rules(reviewed_repo)

    def test_a_single_non_whitespace_source_change_is_blocked_exactly_as_today(
        self, reviewed_repo
    ):
        env = hermetic_git_env(home=reviewed_repo)
        (reviewed_repo / "a.js").write_text("function f() {\n  return 3\n}\n")
        subprocess.run(["git", "add", "a.js"], cwd=reviewed_repo, env=env, check=True)

        result = _run_hook(_commit_payload(reviewed_repo), reviewed_repo)
        assert result.returncode == 2
        assert "Code review required" in result.stdout
        assert "cosmetic-delta-carry-forward" not in _boundary_rules(reviewed_repo)

    def test_a_string_literal_edit_is_blocked(self, reviewed_repo):
        env = hermetic_git_env(home=reviewed_repo)
        (reviewed_repo / "a.js").write_text('function f() {\n  return "x"\n}\n')
        subprocess.run(["git", "add", "a.js"], cwd=reviewed_repo, env=env, check=True)
        assert _run_hook(_commit_payload(reviewed_repo), reviewed_repo).returncode == 2

    def test_an_agent_markdown_edit_never_rides_the_carry_forward(self, reviewed_repo):
        env = hermetic_git_env(home=reviewed_repo)
        agent_file = reviewed_repo / "agents" / "correctness-review.md"
        agent_file.parent.mkdir(parents=True, exist_ok=True)
        agent_file.write_text("---\nname: correctness-review\n---\n")
        subprocess.run(["git", "add", "agents"], cwd=reviewed_repo, env=env, check=True)
        assert _run_hook(_commit_payload(reviewed_repo), reviewed_repo).returncode == 2

    def test_a_one_line_gate_file_never_carries_forward(self, tmp_path):
        """Backward compatibility: a `.review-passed` written by an older
        plugin version has no normalized line and must behave exactly as
        before."""
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 1\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 2\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)

        raw = _rgh.review_gate_hash(tmp_path)
        normalized = ngh.normalized_gate_hash(tmp_path)
        _seed_dispatches(tmp_path, ["correctness-review", "doc-review"], raw, normalized)
        _write_gate(tmp_path, raw, None)  # raw-only, pre-#1627 shape

        (tmp_path / "a.js").write_text("        const x = 2\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        assert _run_hook(_commit_payload(tmp_path), tmp_path).returncode == 2

    def test_dispatch_events_without_the_normalized_field_never_match(self, tmp_path):
        """A stale ledger written by an older plugin version carries no
        `subject_hash_normalized`; it must not corroborate on this path."""
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 1\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 2\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)

        raw = _rgh.review_gate_hash(tmp_path)
        normalized = ngh.normalized_gate_hash(tmp_path)
        _seed_dispatches(tmp_path, ["correctness-review", "doc-review"], raw, None)
        _write_gate(tmp_path, raw, normalized)

        (tmp_path / "a.js").write_text("        const x = 2\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        assert _run_hook(_commit_payload(tmp_path), tmp_path).returncode == 2

    def test_carry_forward_still_requires_two_distinct_dispatches(self, tmp_path):
        """The lens relaxes WHICH hash binds the evidence, never how much
        evidence is required."""
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 1\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 2\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)

        raw = _rgh.review_gate_hash(tmp_path)
        normalized = ngh.normalized_gate_hash(tmp_path)
        _seed_dispatches(tmp_path, ["correctness-review"], raw, normalized)  # only 1
        _write_gate(tmp_path, raw, normalized)

        (tmp_path / "a.js").write_text("        const x = 2\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        assert _run_hook(_commit_payload(tmp_path), tmp_path).returncode == 2

    def test_missing_gate_file_is_still_a_hard_block(self, tmp_path):
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 1\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        assert _run_hook(_commit_payload(tmp_path), tmp_path).returncode == 2


class TestSingleSourceNormalization:
    def test_ledger_hook_skill_and_gate_all_use_the_one_implementation(self):
        """Drift guard (the `mtime_to_iso` sharing precedent): the ledger
        stamp, the skill's write site, and the gate's read must all route
        through `review_gate_normalized_hash`, never a second copy."""
        ledger = (_PLUGIN_ROOT / "hooks" / "agent_dispatch_ledger.py").read_text("utf-8")
        assert "from review_gate_normalized_hash import normalized_gate_hash" in ledger

        gate = (_PLUGIN_ROOT / "hooks" / "pre_commit_review.py").read_text("utf-8")
        assert "review_gate_normalized_hash" in gate

        skill = (_PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md").read_text("utf-8")
        assert "hooks/lib/review_gate_normalized_hash.py" in skill

    def test_no_second_normalization_implementation_exists(self):
        owners = set()
        for path in _PLUGIN_ROOT.rglob("*.py"):
            if path.name.startswith("test_"):
                continue
            if "_canonical_line" in path.read_text(encoding="utf-8", errors="replace"):
                owners.add(path.name)
        assert owners == {"review_gate_normalized_hash.py"}
