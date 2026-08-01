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


def _patch(path: str, removed: list, added: list, context: list | None = None) -> str:
    """A minimal well-formed unified diff for one file.

    The hunk header's counts MUST match the body: `normalize_patch` consumes
    hunk bodies by those counts (#1631 security review — dispatching on line
    prefixes let a removed `-- ...` line masquerade as a file header), and a
    header that over-runs its body is a malformed patch it deliberately fails
    closed on. Real git output is always self-consistent; a fixture that
    isn't tests nothing a hook will ever see.
    """
    context = context or []
    old_count = len(removed) + len(context)
    new_count = len(added) + len(context)
    lines = [
        f"diff --git a/{path} b/{path}",
        f"--- a/{path}",
        f"+++ b/{path}",
        f"@@ -1,{old_count} +1,{new_count} @@",
    ]
    lines += [f"-{ln}" for ln in removed]
    lines += [f"+{ln}" for ln in added]
    lines += [f" {ln}" for ln in context]
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


class TestHeredocBodies:
    """#1638. Unquoted heredoc bodies carry no quote character, so the rule
    in `_canonical_line` that keeps string data out of the cosmetic bucket
    never sees them. Each language test opens, reindents, and closes a
    heredoc within one hunk — the shape `_heredoc_body_marks` reasons over."""

    def test_ruby_squiggly_heredoc_reindent_survives(self):
        before = _patch(
            "a.rb",
            ["sql = <<~SQL", "  SELECT * FROM users WHERE role = admin", "SQL"],
            ["sql = <<~SQL", "  SELECT * FROM users WHERE role = admin", "SQL"],
        )
        after = _patch(
            "a.rb",
            ["sql = <<~SQL", "  SELECT * FROM users WHERE role = admin", "SQL"],
            ["sql = <<~SQL", "    SELECT * FROM users WHERE role = admin", "SQL"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_ruby_dash_heredoc_reindent_survives(self):
        before = _patch("a.rb", ["x = <<-EOF", "  body", "  EOF"], ["x = <<-EOF", "  body", "  EOF"])
        after = _patch("a.rb", ["x = <<-EOF", "  body", "  EOF"], ["x = <<-EOF", "    body", "  EOF"])
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)

    def test_ruby_bare_heredoc_reindent_survives(self):
        before = _patch("a.rb", ["x = <<EOF", "  body", "EOF"], ["x = <<EOF", "  body", "EOF"])
        after = _patch("a.rb", ["x = <<EOF", "  body", "EOF"], ["x = <<EOF", "    body", "EOF"])
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)

    def test_php_heredoc_reindent_survives(self):
        before = _patch(
            "a.php",
            ["$msg = <<<TXT", "  Dear customer, your balance is overdue", "TXT;"],
            ["$msg = <<<TXT", "  Dear customer, your balance is overdue", "TXT;"],
        )
        after = _patch(
            "a.php",
            ["$msg = <<<TXT", "  Dear customer, your balance is overdue", "TXT;"],
            ["$msg = <<<TXT", "    Dear customer, your balance is overdue", "TXT;"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_perl_shell_style_heredoc_reindent_survives(self):
        """Perl and shell share the `<<EOF` grammar (the issue's own grouping
        of the two); `.pl`/`.pm` are the tracked extension, matching
        `_WHITESPACE_INSIGNIFICANT_EXTENSIONS`."""
        before = _patch(
            "a.pl",
            ["my $t = <<EOF;", "  literal text that matters", "EOF"],
            ["my $t = <<EOF;", "  literal text that matters", "EOF"],
        )
        after = _patch(
            "a.pl",
            ["my $t = <<EOF;", "  literal text that matters", "EOF"],
            ["my $t = <<EOF;", "    literal text that matters", "EOF"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_perl_spaced_quoted_heredoc_opener_reindent_survives(self):
        """Perl legally allows whitespace before a QUOTED delimiter
        (`print << "EOF";`) — only the bare spaced form (`<< EOF`) is
        deprecated/fatal. The `.pl` regex must still catch this: missing it
        would be a false negative on a real heredoc, the unsafe direction."""
        before = _patch(
            "a.pl",
            ['print << "EOF";', "  literal text that matters", "EOF"],
            ['print << "EOF";', "  literal text that matters", "EOF"],
        )
        after = _patch(
            "a.pl",
            ['print << "EOF";', "  literal text that matters", "EOF"],
            ['print << "EOF";', "    literal text that matters", "EOF"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_perl_backslash_quoted_heredoc_opener_reindent_survives(self):
        """`<<\\EOF` (perlop: no-interpolation shorthand for `<<'EOF'`) must
        still be recognized as an opener — missing it is a false negative on
        a real heredoc, the unsafe direction this grammar exists to close."""
        before = _patch(
            "a.pl",
            ["print <<\\EOF;", "  literal text that matters", "EOF"],
            ["print <<\\EOF;", "  literal text that matters", "EOF"],
        )
        after = _patch(
            "a.pl",
            ["print <<\\EOF;", "  literal text that matters", "EOF"],
            ["print <<\\EOF;", "    literal text that matters", "EOF"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_indented_closer_with_trailing_whitespace_does_not_false_close(self):
        """#1638 regression: `_bareish_heredoc_close` used `.strip()` for the
        indent-tolerant (`~`/`-`) forms, which also strips TRAILING
        whitespace — so a body line reading exactly the identifier plus
        trailing spaces (`"  SQL  "`) falsely closed the heredoc, dumping
        every later body line back into whitespace collapsing. A real
        terminator is the identifier and nothing else on the line."""
        before = _patch(
            "a.rb",
            ["sql = <<~SQL", "  SELECT 1", "  SQL  ", "    secret data", "SQL"],
            ["sql = <<~SQL", "  SELECT 1", "  SQL  ", "    secret data", "SQL"],
        )
        after = _patch(
            "a.rb",
            ["sql = <<~SQL", "  SELECT 1", "  SQL  ", "    secret data", "SQL"],
            ["sql = <<~SQL", "  SELECT 1", "  SQL  ", "        secret data", "SQL"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_php_closer_with_trailing_whitespace_does_not_false_close(self):
        """#1638 regression: the PHP closer carried the identical
        trailing-whitespace false-close defect just fixed in
        `_bareish_heredoc_close` — `.strip()` (not `.lstrip()`) let a body
        line reading the identifier plus trailing spaces close the heredoc
        early."""
        before = _patch(
            "a.php",
            ["$m = <<<TXT", "  Dear customer", "  TXT  ", "    secret data", "TXT;"],
            ["$m = <<<TXT", "  Dear customer", "  TXT  ", "    secret data", "TXT;"],
        )
        after = _patch(
            "a.php",
            ["$m = <<<TXT", "  Dear customer", "  TXT  ", "    secret data", "TXT;"],
            ["$m = <<<TXT", "  Dear customer", "  TXT  ", "        secret data", "TXT;"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_perl_module_extension_uses_the_same_grammar_as_pl(self):
        assert ngh._HEREDOC_GRAMMARS[".pm"] is ngh._HEREDOC_GRAMMARS[".pl"]

    @pytest.mark.parametrize("suffix", [".tf", ".hcl"])
    def test_terraform_and_hcl_alias_the_ruby_style_grammar(self, suffix):
        """Terraform/HCL heredocs (`<<EOT` / `<<-EOT`) share Ruby's exact
        opener/closer grammar — not Perl's, whose regex has no dash-modifier
        capture and would silently fail to match `<<-EOT` at all."""
        assert ngh._HEREDOC_GRAMMARS[suffix] is ngh._HEREDOC_GRAMMARS[".rb"]

    def test_terraform_heredoc_reindent_survives(self):
        before = _patch(
            "main.tf",
            ["user_data = <<-EOF", "  #!/bin/bash", "  echo hi", "EOF"],
            ["user_data = <<-EOF", "  #!/bin/bash", "  echo hi", "EOF"],
        )
        after = _patch(
            "main.tf",
            ["user_data = <<-EOF", "  #!/bin/bash", "  echo hi", "EOF"],
            ["user_data = <<-EOF", "  #!/bin/bash", "    echo hi", "EOF"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_an_opener_with_no_close_inside_the_hunk_fails_closed(self):
        """The true closer might be outside this hunk's side entirely; the
        safe assumption is that every line after an unresolved opener is
        still inside the heredoc body, not eligible for collapsing. Only the
        FAR line is reindented — leaving the near line byte-identical between
        before/after — so a regression that only marks the line immediately
        after the opener (rather than every remaining line) would still be
        caught here."""
        before = _patch("a.rb", ["x = <<~SQL", "  line one", "  line two"], ["x = <<~SQL", "  line one", "  line two"])
        after = _patch("a.rb", ["x = <<~SQL", "  line one", "  line two"], ["x = <<~SQL", "  line one", "    line two"])
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_ordinary_reindented_code_outside_a_heredoc_still_collapses(self):
        """Regression guard: the heredoc handling must not make Ruby/PHP/Perl
        stop getting carry-forward for perfectly ordinary reindents."""
        assert ngh.normalize_patch(_patch("a.rb", ["  x = 1"], ["x = 1"])) == ""
        assert ngh.normalize_patch(_patch("a.php", ["  $x = 1;"], ["$x = 1;"])) == ""
        assert ngh.normalize_patch(_patch("a.pl", ["  $x = 1;"], ["$x = 1;"])) == ""

    @pytest.mark.parametrize(
        "suffix,line",
        [
            (".rb", "arr << item"),
            (".rb", "x << y"),
            (".rb", "result = a << 2"),
            (".pl", "arr << item"),
            (".pl", "x << y"),
            (".pl", "result = a << 2"),
        ],
    )
    def test_idiomatic_spaced_shift_or_shovel_is_never_mistaken_for_a_heredoc(self, suffix, line):
        """Ruby/Perl's `<<` is also their shift/append operator, always
        written with spaces by convention. A heredoc opener has no space
        between `<<` and its delimiter, so the idiomatic spaced form must
        never be misread as one. Exercised through the public API: if the
        regex falsely opened a heredoc on `line`, the ordinary reindent right
        after it would be swept into the (fail-closed, byte-exact) heredoc
        body and stop collapsing — this asserts it still collapses to ""."""
        before = _patch(f"a{suffix}", ["  x = 1"], ["x = 1"], context=[line])
        assert ngh.normalize_patch(before) == "", (
            f"{line!r} on {suffix} must not open a phantom heredoc that blocks "
            "carry-forward for an unrelated ordinary reindent in the same hunk"
        )

    def test_two_heredocs_opened_on_one_line_both_get_body_tracking(self):
        """#1638 regression: the original fix tracked only ONE pending
        heredoc via `.search()` (leftmost match), so a line with two stacked
        openers — an ordinary idiom (`print <<A, <<B;`) — left the SECOND
        heredoc's body unmarked and collapsible. Reindenting body b alone
        must still survive normalization."""
        before = _patch(
            "a.pl",
            ["print <<A, <<B;", "  body a", "A", "  body b", "B"],
            ["print <<A, <<B;", "  body a", "A", "  body b", "B"],
        )
        after = _patch(
            "a.pl",
            ["print <<A, <<B;", "  body a", "A", "  body b", "B"],
            ["print <<A, <<B;", "  body a", "A", "      body b", "B"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_two_sequential_heredocs_in_one_hunk_each_get_body_tracking(self):
        before = _patch(
            "a.rb",
            ["a = <<~A", "  body a", "A", "b = <<~B", "  body b", "B"],
            ["a = <<~A", "  body a", "A", "b = <<~B", "  body b", "B"],
        )
        after = _patch(
            "a.rb",
            ["a = <<~A", "  body a", "A", "b = <<~B", "  body b", "B"],
            ["a = <<~A", "  body a", "A", "b = <<~B", "      body b", "B"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_php_nowdoc_single_quoted_delimiter_reindent_survives(self):
        before = _patch(
            "a.php",
            ["$msg = <<<'TXT'", "  Dear customer, your balance is overdue", "TXT;"],
            ["$msg = <<<'TXT'", "  Dear customer, your balance is overdue", "TXT;"],
        )
        after = _patch(
            "a.php",
            ["$msg = <<<'TXT'", "  Dear customer, your balance is overdue", "TXT;"],
            ["$msg = <<<'TXT'", "    Dear customer, your balance is overdue", "TXT;"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_body_line_containing_identifier_as_substring_does_not_false_close(self):
        before = _patch(
            "a.rb",
            ["x = <<~SQL", "  SQL is fun to write", "SQL"],
            ["x = <<~SQL", "  SQL is fun to write", "SQL"],
        )
        after = _patch(
            "a.rb",
            ["x = <<~SQL", "  SQL is fun to write", "SQL"],
            ["x = <<~SQL", "    SQL is fun to write", "SQL"],
        )
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_reindenting_staged_ruby_heredoc_body_leaves_the_normalized_hash_changed(
        self, tmp_path
    ):
        """End to end against real git, with an opener far enough above the
        changed line that it would be invisible under git's default 3-line
        hunk context — the exact hazard `normalized_gate_hash`'s
        `--unified=100000` closes. Padding sits BETWEEN the opener and the
        edited line, not after it, so this genuinely exercises the gap."""
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)

        lines = ["sql = <<~SQL"]
        lines += [f"  -- padding comment {i}" for i in range(10)]
        lines.append("  SELECT * FROM users WHERE role = admin")
        lines.append("SQL")
        (tmp_path / "a.rb").write_text("\n".join(lines) + "\n")
        subprocess.run(["git", "add", "a.rb"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)

        lines[-2] = "      SELECT * FROM users WHERE role = admin"
        (tmp_path / "a.rb").write_text("\n".join(lines) + "\n")

        # Confirm the setup actually creates the gap this test is for, using
        # the actual UNSTAGED edit (captured only now, after the write —
        # capturing it earlier on the clean post-commit tree would make this
        # assertion vacuously true regardless of the padding size): with
        # git's default 3-line hunk context, the opener 11 lines above the
        # edited line must not appear among the hunk's BODY lines (the ones
        # `normalize_patch` actually consumes). `@@ ... @@` header lines are
        # excluded from this check on purpose — git appends a heuristic
        # "nearest preceding line" section heading to the header for
        # readability (confirmed here: it echoes `sql = <<~SQL`), but that
        # heading is never fed to `_heredoc_body_marks`; only `+`/`-`/` `
        # body lines are, and the assertion must mirror what the module
        # under test actually sees, not raw diff text.
        default_diff = subprocess.run(
            ["git", "diff"], cwd=tmp_path, env=env, capture_output=True, text=True, check=True
        )
        body_lines = "\n".join(
            ln for ln in default_diff.stdout.splitlines() if not ln.startswith("@@")
        )
        assert "<<~SQL" not in body_lines, (
            "setup didn't create the gap: the opener leaked into the default-context "
            "diff's body lines before the edit, so this test wouldn't exercise "
            "--unified=100000"
        )

        subprocess.run(["git", "add", "a.rb"], cwd=tmp_path, env=env, check=True)
        assert ngh.normalized_gate_hash(tmp_path) is not None, (
            "a heredoc-body reindent must never normalize to nothing, even when its "
            "opener sits outside git's default hunk context"
        )


class TestNormalizationCollisions:
    """#1631 adversarial review. Each test pins one collision where two
    behaviorally DIFFERENT changesets normalized to the same digest, letting
    unreviewed content ride a carry-forward. See fixes 1-5 in the module
    docstring."""

    def test_an_insertion_at_a_different_position_is_not_the_same_change(self):
        """Fix 2. Flat per-file removed/added lists carry no position, so
        `+audit()` before vs. after a call produced one digest. Context lines
        are what make an insertion point part of the subject."""
        header = "diff --git a/a.js b/a.js\n--- a/a.js\n+++ b/a.js\n@@ -1,2 +1,3 @@\n"
        early = header + "+audit()\n a()\n b()\n"
        late = header + " a()\n b()\n+audit()\n"
        # Identical added and removed line sets; only the position differs.
        assert ngh.normalize_patch(early) != ngh.normalize_patch(late)
        assert ngh.normalize_patch(early) not in ("", None)

    def test_a_line_moved_between_hunks_is_not_formatting(self):
        """Fix 3. Whole-file removed-equals-added read a relocated
        `lock.acquire()` as formatting, because the file's removed and added
        lists matched across the two hunks."""
        moved = (
            "diff --git a/svc.js b/svc.js\n"
            "--- a/svc.js\n"
            "+++ b/svc.js\n"
            "@@ -1,2 +1,1 @@\n"
            "-lock.acquire()\n"
            " work()\n"
            "@@ -20,1 +19,2 @@\n"
            " more()\n"
            "+lock.acquire()\n"
        )
        assert ngh.normalize_patch(moved) not in ("", None)

    @pytest.mark.parametrize(
        "metadata",
        [
            "old mode 100644\nnew mode 100755",
            "similarity index 100%\nrename from old.js\nrename to new.js",
            "new file mode 100644",
            "deleted file mode 100644",
        ],
    )
    def test_a_change_carried_only_by_patch_metadata_is_recorded(self, metadata):
        """Fix 4. A mode flip, a rename, and an empty new or deleted file
        produce a diff with NO hunk body. Skipping them made such a change
        invisible, so it could be staged on top of corroborated content."""
        patch = f"diff --git a/x.js b/x.js\n{metadata}\n"
        assert ngh.normalize_patch(patch) not in ("", None)

    def test_a_binary_swap_binds_its_blob_shas(self):
        """Fix 4. A binary file has no textual hunk at all; its `index` blob
        SHAs are the only content signal a textual diff exposes."""
        one = (
            "diff --git a/blob.bin b/blob.bin\n"
            "index 1111111..2222222 100644\n"
            "Binary files a/blob.bin and b/blob.bin differ\n"
        )
        two = one.replace("2222222", "3333333")
        assert ngh.normalize_patch(one) not in ("", None)
        assert ngh.normalize_patch(one) != ngh.normalize_patch(two)

    def test_a_removed_comment_line_cannot_masquerade_as_a_file_header(self):
        """Fix 1, the sharpest of the five. A REMOVED source line beginning
        `-- ` (a SQL/Lua/Haskell comment) renders as `--- ...`. Dispatching on
        that prefix read it as a file header and silently terminated the
        hunk, so every following line — including injected code — vanished
        from the digest."""
        benign = _patch("db.sql", ["-- legacy note"], [], context=["SELECT 1;"])
        injected = _patch(
            "db.sql", ["-- legacy note"], ["GRANT ALL ON *.* TO 'x'@'%';"], context=["SELECT 1;"]
        )
        normalized = ngh.normalize_patch(injected)
        assert normalized not in ("", None)
        assert "GRANT ALL" in normalized, "injected code must reach the digest"
        assert ngh.normalize_patch(benign) != normalized

    def test_an_added_line_beginning_with_plus_plus_cannot_either(self):
        """Fix 1, the `+++ ` half of the same confusion."""
        normalized = ngh.normalize_patch(_patch("a.js", [], ["++ x", "evil()"]))
        assert normalized is not None and "evil()" in normalized

    def test_a_hunk_body_that_contradicts_its_header_fails_closed(self):
        """Real git output is always self-consistent. A patch whose body does
        not match its declared counts is a shape this module cannot reason
        about, so it must not produce a digest at all."""
        malformed = (
            "diff --git a/a.js b/a.js\n--- a/a.js\n+++ b/a.js\n@@ -1,2 +1,2 @@\n-x\n"
            "diff --git a/b.js b/b.js\n--- a/b.js\n+++ b/b.js\n@@ -1,1 +1,1 @@\n-y\n+z\n"
        )
        assert ngh.normalize_patch(malformed) is None

    def test_a_fully_cosmetic_changeset_gets_no_digest(self, tmp_path):
        """Fix 5, and the reason the whole chain was exploitable end to end.

        `sha256("")` is a CONSTANT shared by every fully-cosmetic changeset
        AND by every dispatch recorded while the index was still clean. Two
        review dispatches made before anything was staged stamped exactly the
        value a later mode-only or rename-only stage recomputes — clearing
        the `>= 2` floor with evidence from agents that reviewed nothing.
        """
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("x\n")
        subprocess.run(["git", "add", "a.js"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)

        # A clean index is the bootstrap: it must yield no digest at all.
        assert ngh.normalized_gate_hash(tmp_path) is None
        assert ngh.normalize_patch("") == ""

        # And so must a changeset whose entire delta is documentation.
        (tmp_path / "NOTES.md").write_text("notes\n")
        subprocess.run(["git", "add", "NOTES.md"], cwd=tmp_path, env=env, check=True)
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

    def test_a_binary_swap_on_top_of_reviewed_code_is_blocked(self, reviewed_repo):
        """#1631. A binary file produces no hunk body, so it was invisible to
        the digest: staging one on top of already-corroborated code left the
        normalized hash untouched and rode the carry-forward."""
        env = hermetic_git_env(home=reviewed_repo)
        (reviewed_repo / "blob.bin").write_bytes(b"\x00\x01MALICIOUS")
        subprocess.run(["git", "add", "blob.bin"], cwd=reviewed_repo, env=env, check=True)
        assert _run_hook(_commit_payload(reviewed_repo), reviewed_repo).returncode == 2

    def test_making_a_file_executable_on_top_of_reviewed_code_is_blocked(self, reviewed_repo):
        """#1631. Same shape as the binary swap: a mode flip has no hunk."""
        env = hermetic_git_env(home=reviewed_repo)
        script = reviewed_repo / "deploy.sh"
        script.write_text("echo hi\n")
        subprocess.run(["git", "add", "deploy.sh"], cwd=reviewed_repo, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "add script"], cwd=reviewed_repo, env=env, check=True)
        script.chmod(0o755)
        subprocess.run(["git", "add", "deploy.sh"], cwd=reviewed_repo, env=env, check=True)
        assert _run_hook(_commit_payload(reviewed_repo), reviewed_repo).returncode == 2

    def test_dispatches_recorded_against_a_clean_index_corroborate_nothing(self, tmp_path):
        """#1631, the end-to-end bypass chain, and the reason fix 5 exists.

        Two genuine review dispatches made BEFORE anything was staged used to
        stamp `sha256("")` — the same constant a later mode-only stage
        recomputes. That cleared the `>= 2` distinct-dispatch floor with
        evidence from agents that had reviewed nothing at all, which is
        exactly the #1461 property this slice must not reopen.
        """
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        (tmp_path / "a.js").write_text("const x = 1\n")
        (tmp_path / "deploy.sh").write_text("echo hi\n")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, env=env, check=True)

        # Reviews dispatched against a clean index: whatever they stamp must
        # never be a value a real changeset can recompute.
        clean_index_normalized = ngh.normalized_gate_hash(tmp_path)
        assert clean_index_normalized is None
        _seed_dispatches(tmp_path, ["correctness-review", "doc-review"], "rawhash", None)
        _write_gate(tmp_path, "rawhash", None)

        # Now stage a mode-only change and try to ride that "evidence".
        (tmp_path / "deploy.sh").chmod(0o755)
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
        result = _run_hook(_commit_payload(tmp_path), tmp_path)
        assert result.returncode == 2, result.stdout + result.stderr
        assert "cosmetic-delta-carry-forward" not in _boundary_rules(tmp_path)


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
