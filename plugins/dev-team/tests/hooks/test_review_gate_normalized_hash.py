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
import subprocess
import sys
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

    def test_embedded_form_feed_does_not_desync_hunk_line_counting(self):
        """#1904 item 15: git's own `@@ -a,b +c,d @@` hunk-header counts are
        computed over literal "\\n" bytes only, but `str.splitlines()` also
        breaks on the wider Unicode line-boundary set (form feed, U+2028,
        etc.). A changed line with a form feed embedded mid-line used to make
        `splitlines()` see one extra "line" the hunk header's counts don't
        account for, closing the hunk one line early and silently dropping
        everything after the form feed from the digest — so two patches
        differing only in the content after the form feed hashed identically.
        """
        before = _patch("src/a.js", ["orig"], ["line\x0cchanged-A"])
        after = _patch("src/a.js", ["orig"], ["line\x0cchanged-B"])
        before_norm = ngh.normalize_patch(before)
        after_norm = ngh.normalize_patch(after)
        assert before_norm not in ("", None)
        assert after_norm not in ("", None)
        assert before_norm != after_norm, (
            "content after an embedded form feed must survive into the digest"
        )

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


#: `(path, opener, closer)` for every form whose body is line-granular
#: (heredocs) or delimiter-granular (inline spans). Collapsed from seven
#: hand-copied near-duplicates (#1666): each differed only in these three
#: literals while sharing one arrange-act-assert shape, and the copies had
#: already drifted — some asserted the non-empty postcondition, some did
#: not. Cases with a genuinely different assertion shape stay separate
#: tests below.
_REINDENT_FORMS = [
    ("a.rb", "sql = <<~SQL", "SQL"),
    ("a.rb", "x = <<-EOF", "  EOF"),
    ("a.rb", "x = <<EOF", "EOF"),
    ("a.rb", "r = <<`EOC`", "EOC"),
    ("a.rb", "s = <<~'1SQL'", "1SQL"),
    ("a.php", "$msg = <<<TXT", "TXT;"),
    ("a.pl", "my $t = <<EOF;", "EOF"),
    ("a.pl", 'print << "EOF";', "EOF"),
    ("a.pl", "print <<\\EOF;", "EOF"),
    ("a.tf", "user_data = <<-EOT", "  EOT"),
    ("a.lua", "local s = [[", "]]"),
    ("a.lua", "local s = [==[", "]==]"),
    ("a.sql", "CREATE FUNCTION f() RETURNS int AS $$", "$$"),
    ("a.sql", "CREATE FUNCTION f() RETURNS int AS $body$", "$body$"),
    ("a.go", "s := `", "`"),
    ("a.ts", "const s = `", "`;"),
    ("a.js", "const s = `", "`;"),
    ("a.cpp", 'auto s = R"(', ')";'),
    ("a.cpp", 'auto s = R"xy(', ')xy";'),
]


class TestHeredocBodies:
    """#1638. Unquoted heredoc bodies carry no quote character, so the rule
    in `_canonical_line` that keeps string data out of the cosmetic bucket
    never sees them. Each language test opens, reindents, and closes a
    heredoc within one hunk — the shape `_heredoc_body_marks` reasons over."""

    @pytest.mark.parametrize("path, opener, closer", _REINDENT_FORMS)
    def test_reindenting_a_multiline_literal_body_survives(self, path, opener, closer):
        """Reindenting a line INSIDE an unquoted multi-line literal is a data
        change, and must never normalize away as cosmetic. Covers #1638's
        original heredoc forms plus #1660's Lua long brackets and SQL
        dollar-quoting, #1661's Go/JS/TS/C++ raw-string forms, and #1667's
        Ruby backtick, quoted-digit-leading, and Perl empty-delimiter
        openers."""
        body = "  literal text that matters"
        unchanged = [opener, body, closer]
        reindented = [opener, "  " + body, closer]
        before = _patch(path, unchanged, list(unchanged))
        after = _patch(path, unchanged, reindented)
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_perl_empty_delimiter_heredoc_reindent_survives(self):
        """#1667: Perl's `<<"";` is terminated by a BLANK line, so its closer
        is the empty string rather than an identifier — a shape the shared
        `(opener, closer)` parametrization above cannot express."""
        unchanged = ['print <<"";', "  literal text", ""]
        reindented = ['print <<"";', "    literal text", ""]
        before = _patch("a.pl", unchanged, list(unchanged))
        after = _patch("a.pl", unchanged, reindented)
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_php_inline_html_reindent_survives(self):
        """#1660: text between `?>` and the next `<?` is emitted verbatim, so
        reindenting it changes program OUTPUT."""
        unchanged = ["<?php $a = 1; ?>", "  <div>hello</div>", "<?php $b = 2;"]
        reindented = ["<?php $a = 1; ?>", "    <div>hello</div>", "<?php $b = 2;"]
        before = _patch("a.php", unchanged, list(unchanged))
        after = _patch("a.php", unchanged, reindented)
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_an_inline_literal_closed_on_its_own_line_does_not_swallow_the_rest(self):
        """A one-line template literal closes where it opened, so following
        lines stay eligible for whitespace collapsing. Without the positional
        resume in `_enqueue_openers` an inline grammar would mark the entire
        remainder of every hunk containing one backtick pair."""
        assert ngh._heredoc_body_marks(["const s = `abc`;", "  code()"], ".ts") == [
            False,
            False,
        ]

    def test_an_inline_literal_may_reopen_on_the_line_that_closed_it(self):
        """The case the pre-#1660 scanner could not represent: a closer line
        that also carries a fresh opener. Marking must continue past it."""
        assert ngh._heredoc_body_marks(["a := `", "x", "` + `", "y", "`"], ".go") == [
            False,
            True,
            True,
            True,
            True,
        ]

    @pytest.mark.parametrize(
        "suffix, line",
        [(".lua", "t[idx] = other[key]"), (".sql", "SELECT cost * 2 FROM t")],
    )
    def test_inline_grammars_do_not_false_open_on_ordinary_code(self, suffix, line):
        """Lua's `[[` and SQL's `$...$` must not match ordinary indexing or
        arithmetic — a false opener marks the rest of the hunk byte-exact,
        which is safe but costs every carry-forward on the file."""
        assert ngh._heredoc_body_marks([line, "  next_line()"], suffix) == [False, False]

    def test_xml_is_compared_byte_exactly(self):
        """#1660: `.xml` was dropped from `_WHITESPACE_INSIGNIFICANT_EXTENSIONS`
        rather than given a grammar — element text and CDATA preserve
        whitespace across most of a document."""
        assert ".xml" not in ngh._WHITESPACE_INSIGNIFICANT_EXTENSIONS
        before = _patch("a.xml", ["  <note>text</note>"], ["  <note>text</note>"])
        after = _patch("a.xml", ["  <note>text</note>"], ["    <note>text</note>"])
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)

    def test_the_grammar_table_cannot_be_mutated_by_an_importer(self):
        """#1665: a safety-relevant table that any importer could rewrite at
        runtime. Its sibling language tables are already `frozenset`."""
        with pytest.raises(TypeError):
            ngh._HEREDOC_GRAMMARS[".rb"] = ()

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


class TestHunkStartGuard:
    """#1662. `--unified=100000` was trusted to guarantee every hunk spans the
    whole file, so a heredoc opener above a changed body line is always
    visible. That is a magic number, not a guarantee: a file longer than the
    context window still yields a hunk starting partway down, and an opener
    above it is invisible — failing OPEN, the one exception to this module's
    fail-closed posture."""

    @staticmethod
    def _offset_patch(path: str, removed: list, added: list, start: int) -> str:
        lines = [
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            f"@@ -{start},{len(removed)} +{start},{len(added)} @@",
        ]
        lines += [f"-{ln}" for ln in removed]
        lines += [f"+{ln}" for ln in added]
        return "\n".join(lines) + "\n"

    def test_a_hunk_not_starting_at_line_one_is_byte_exact_for_grammared_files(self):
        """The body could be inside a heredoc opened above the window. Without
        the guard this reindent normalizes away as cosmetic."""
        before = self._offset_patch("a.rb", ["  body text"], ["  body text"], 5000)
        after = self._offset_patch("a.rb", ["  body text"], ["    body text"], 5000)
        assert ngh.normalize_patch(before) != ngh.normalize_patch(after)
        assert ngh.normalize_patch(after) not in ("", None)

    def test_a_whole_file_hunk_still_takes_the_normal_path(self):
        """A hunk starting at line 1 has its openers in view by construction,
        so the guard must not cost the invariance this module exists for."""
        before = self._offset_patch("a.rb", ["  x = 1"], ["  x = 1"], 1)
        after = self._offset_patch("a.rb", ["  x = 1"], ["      x = 1"], 1)
        assert ngh.normalize_patch(before) == ngh.normalize_patch(after) == ""

    def test_an_added_file_reports_start_zero_and_still_collapses(self):
        """A pure add is `@@ -0,0 +1,n @@`. `> 1` (not `!= 1`) is what keeps
        that on the fast path."""
        patch = (
            "diff --git a/a.rb b/a.rb\n"
            "--- /dev/null\n"
            "+++ b/a.rb\n"
            "@@ -0,0 +1,1 @@\n"
            "+  x = 1\n"
        )
        assert ngh.normalize_patch(patch) not in (None,)

    def test_an_offset_hunk_in_a_grammarless_language_is_unaffected(self):
        """The guard is scoped to extensions with a grammar — everything else
        already had no opener to miss."""
        before = self._offset_patch("a.java", ["  int x = 1;"], ["  int x = 1;"], 900)
        after = self._offset_patch("a.java", ["  int x = 1;"], ["      int x = 1;"], 900)
        assert ngh.normalize_patch(before) == ngh.normalize_patch(after) == ""


class TestNormalizerBounds:
    """#1663. `--unified=100000` turns a one-line edit to a large tracked file
    into a whole-file diff, processed synchronously inside a PreToolUse hook
    with no subprocess timeout and no cap on the payload."""

    def test_the_git_diff_call_carries_an_explicit_timeout(self, monkeypatch):
        seen = {}

        def fake(extra_flags, cwd=None, text=False, target="--cached", timeout=None):
            seen["timeout"] = timeout
            raise AssertionError("stop after recording")

        monkeypatch.setattr(ngh, "run_safe_git_diff", fake)
        with pytest.raises(AssertionError):
            ngh.normalized_gate_hash()
        assert seen["timeout"] == ngh._GIT_DIFF_TIMEOUT_SECONDS
        assert seen["timeout"] > 0

    def test_a_timed_out_git_diff_fails_closed(self, monkeypatch):
        """`TimeoutExpired` is a `SubprocessError`, NOT an `OSError` — the
        pre-existing `except (FileNotFoundError, OSError)` would not have
        caught it, and an uncaught raise inside the hook is not fail-closed."""

        def fake(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd=["git", "diff"], timeout=1)

        monkeypatch.setattr(ngh, "run_safe_git_diff", fake)
        assert ngh.normalized_gate_hash() is None

    def test_an_oversized_patch_fails_closed(self, monkeypatch):
        oversized = b"x" * (ngh._MAX_PATCH_BYTES + 1)

        def fake(*_args, **_kwargs):
            return subprocess.CompletedProcess(["git"], 0, stdout=oversized, stderr=b"")

        monkeypatch.setattr(ngh, "run_safe_git_diff", fake)
        assert ngh.normalized_gate_hash() is None


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


# --- layer 2: the gate lens, end to end (historical, #1886) --------------
#
# The cosmetic-delta carry-forward lens this section exercised lived in
# `pre_commit_review.py`'s (now-removed) `_cosmetic_carry_forward_verdict`.
# #1886 moved the review-corroboration gate from `git commit` to
# `gh pr create` and deliberately did NOT carry this lens forward — see
# `hooks/pre_pr_review.py`'s own module docstring for why (the friction it
# relieved — a whitespace-only re-stage forcing a fresh review-agent
# dispatch before the NEXT commit — was a direct consequence of gating
# every commit, which no longer happens). `hooks/pre_commit_review.py` is
# now a documented no-op and emits no `cosmetic-delta-carry-forward` event
# under any input. The end-to-end integration coverage this section used to
# provide has no successor: `pre_pr_review.py` never emits this event
# either, by design.


class TestSingleSourceNormalization:
    def test_ledger_no_longer_stamps_the_normalized_hash(self):
        """Reversed by issue #1904 (was: "the ledger keeps stamping it
        defensively (a future gate could still consume it)"). By the time
        #1886 retired `pre_commit_review.py` to a no-op, NOTHING consumed
        `subject_hash_normalized` at all — confirmed by a repo-wide grep
        before this fix. Stamping it anyway cost a whole-repo diff
        (`--unified=100000`, per this module's own docstring) on EVERY
        Agent/Task dispatch for zero benefit; #1904 removed the call.
        A future gate that wants normalization back should re-add the call
        deliberately, not inherit a stale "just in case" one."""
        ledger = (_PLUGIN_ROOT / "hooks" / "agent_dispatch_ledger.py").read_text("utf-8")
        assert "normalized_gate_hash" not in ledger

    def test_skill_no_longer_references_the_retired_normalization_write(self):
        """`.review-passed` (the two-line, normalization-carrying gate file)
        is retired — `/code-review` now writes only the single-line
        `.pr-review-passed` (#1886), which has no normalized-hash leg (see
        `hooks/pre_pr_review.py`'s module docstring: the cosmetic-delta
        carry-forward mechanism this normalization existed for was
        deliberately dropped for the PR-time gate). The skill must not
        reference the normalization module at all."""
        skill = (_PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md").read_text("utf-8")
        assert "review_gate_normalized_hash.py" not in skill

    def test_no_second_normalization_implementation_exists(self):
        owners = set()
        for path in _PLUGIN_ROOT.rglob("*.py"):
            if path.name.startswith("test_"):
                continue
            if "_canonical_line" in path.read_text(encoding="utf-8", errors="replace"):
                owners.add(path.name)
        assert owners == {"review_gate_normalized_hash.py"}
