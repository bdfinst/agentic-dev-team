"""Tests for scripts/select_lenses.py — the diff-domain review-lens resolver (#1516)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPT = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "select_lenses.py"


def _load():
    spec = importlib.util.spec_from_file_location("select_lenses", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SL = _load()


# --------------------------------------------------------------------------
# parse_scope (pure)
# --------------------------------------------------------------------------
def test_parse_scope_always():
    assert SL.parse_scope("---\nx\n---\nScope: always\n") == "always"


def test_parse_scope_structured_bullet_block_is_authoritative():
    # Empty inline Scope + bullet block, then a prose Scope line naming .py.
    text = "Scope:\n- **/*.svelte\n- **/*.tsx\nCites: foo\n\nScope: also .py files\n"
    assert SL.parse_scope(text) == ["**/*.svelte", "**/*.tsx"]


def test_parse_scope_prose_fallback_when_no_block():
    text = "Scope: JavaScript files only (`.js`, `.ts`).\n"
    assert SL.parse_scope(text) == ["**/*.js", "**/*.ts"]


def test_parse_scope_added_only_bullet_block():
    text = "Scope: added-only\n- **/*.tsx\n- **/*.vue\nCites: foo\n"
    assert SL.parse_scope(text) == (SL.SCOPE_ADDED_ONLY, ["**/*.tsx", "**/*.vue"])


def test_parse_scope_added_only_without_bullet_block_is_none():
    assert SL.parse_scope("Scope: added-only\nCites: foo\n") is None


def test_parse_scope_on_demand():
    assert SL.parse_scope("Scope: on-demand\nCites: foo\n") == SL.SCOPE_ON_DEMAND


def test_parse_scope_missing_is_none():
    assert SL.parse_scope("---\nname: x\n---\nNo scope here.\n") is None


def test_parse_scope_prose_without_extension_is_none():
    assert SL.parse_scope("Scope: various source files\n") is None


def test_matches_suffix_boundary():
    # .ts must not over-match .mts; declaration files (.d.ts) are a real .ts suffix.
    assert SL._matches("foo.mts", "**/*.ts") is False
    assert SL._matches("foo.d.ts", "**/*.ts") is True
    assert SL._matches("a/b/App.tsx", "**/*.tsx") is True


def test_matches_literal_and_empty_suffix():
    # Non-glob pattern matches by basename/exact path; a bare "**/*" (empty suffix) never matches.
    assert SL._matches("a/Dockerfile", "Dockerfile") is True
    assert SL._matches("a/Dockerfile.bak", "Dockerfile") is False
    assert SL._matches("foo.py", "**/*") is False


def test_registry_lens_names_skips_separator_and_other_sections():
    registry = (
        "## Review Agents\n"
        "| Agent | File | Focus |\n"
        "| ------- | ------ | ------ |\n"
        "| a11y-review | `agents/a11y-review.md` | x |\n"
        "## Other Agents\n"
        "| trap-agent | `agents/trap-agent.md` | y |\n"
    )
    names = SL._registry_lens_names(registry)
    assert names == ["a11y-review"]  # no "-------" separator, no cross-section leak


def test_parse_model_is_opus():
    assert SL.parse_model_is_opus("model: opus\n") is True
    assert SL.parse_model_is_opus("model: haiku\n") is False
    assert SL.parse_model_is_opus("no model line\n") is False


# --------------------------------------------------------------------------
# applicable_lenses (pure, synthetic rosters)
# --------------------------------------------------------------------------
def test_backend_only_excludes_globbed_lenses_keeps_always():
    roster = [
        ("correctness-review", "always", True),
        ("a11y-review", ["**/*.tsx", "**/*.svelte"], False),
    ]
    lenses, warnings = SL.applicable_lenses(["plugins/dev-team/scripts/foo.py"], roster)
    assert "correctness-review" in lenses
    assert "a11y-review" not in lenses
    assert warnings == []


def test_tsx_includes_globbed_lens():
    roster = [
        ("correctness-review", "always", True),
        ("component-architecture-review", ["**/*.tsx"], False),
    ]
    lenses, _ = SL.applicable_lenses(["src/App.tsx"], roster)
    assert "component-architecture-review" in lenses
    assert "correctness-review" in lenses


def test_missing_scope_included_and_warned():
    roster = [("stub-review", None, False)]
    lenses, warnings = SL.applicable_lenses(["foo.py"], roster)
    assert lenses == ["stub-review"]
    assert warnings == ["stub-review"]


def test_empty_file_set_yields_nothing():
    roster = [("correctness-review", "always", True), ("stub-review", None, False)]
    assert SL.applicable_lenses([], roster) == ([], [])


def test_cheap_first_ordering_follows_model_not_name():
    # "a-review" is opus, "z-review" is non-opus — order must be z (non-opus) then a (opus).
    roster = [("a-review", "always", True), ("z-review", "always", False)]
    lenses, _ = SL.applicable_lenses(["foo.py"], roster)
    assert lenses == ["z-review", "a-review"]


def test_compound_extension_match():
    roster = [("comp", ["**/*.component.ts"], False)]
    assert SL.applicable_lenses(["a/b/widget.component.ts"], roster)[0] == ["comp"]
    assert SL.applicable_lenses(["a/b/widget.ts"], roster)[0] == []


def test_extensionless_file_excludes_globbed_lens():
    roster = [("a11y-review", ["**/*.tsx"], False)]
    assert SL.applicable_lenses(["Makefile"], roster) == ([], [])


def test_added_only_scope_with_no_added_files_arg_matches_like_plain_glob():
    # Fail-safe: a caller (e.g. /build) that never passes added_files gets the
    # pre-#1733 behavior — any matching changed file, modified or added.
    roster = [("component-architecture-review", (SL.SCOPE_ADDED_ONLY, ["**/*.tsx"]), False)]
    lenses, warnings = SL.applicable_lenses(["src/App.tsx"], roster)
    assert lenses == ["component-architecture-review"]
    # The fallback is silent widening, not silent dropping — it must be named
    # in warnings the same way a missing Scope: already is (domain-review).
    assert warnings == ["unnarrowed-added-only:component-architecture-review"]


def test_added_only_scope_narrowed_by_caller_emits_no_warning():
    roster = [("component-architecture-review", (SL.SCOPE_ADDED_ONLY, ["**/*.tsx"]), False)]
    lenses, warnings = SL.applicable_lenses(
        ["src/App.tsx"], roster, added_files={"src/App.tsx"}
    )
    assert lenses == ["component-architecture-review"]
    assert warnings == []


def test_added_only_scope_excludes_merely_modified_file():
    roster = [("component-architecture-review", (SL.SCOPE_ADDED_ONLY, ["**/*.tsx"]), False)]
    lenses, _ = SL.applicable_lenses(["src/App.tsx"], roster, added_files=set())
    assert lenses == []


def test_added_only_scope_includes_added_file():
    roster = [("component-architecture-review", (SL.SCOPE_ADDED_ONLY, ["**/*.tsx"]), False)]
    lenses, _ = SL.applicable_lenses(
        ["src/App.tsx", "src/Existing.tsx"], roster, added_files={"src/App.tsx"}
    )
    assert lenses == ["component-architecture-review"]


def test_added_only_scope_non_matching_added_file_excluded():
    roster = [("component-architecture-review", (SL.SCOPE_ADDED_ONLY, ["**/*.tsx"]), False)]
    lenses, _ = SL.applicable_lenses(["src/App.vue"], roster, added_files={"src/App.vue"})
    assert lenses == []


def test_on_demand_scope_never_selected_and_never_warned():
    # Deliberate self-exclusion (claude-setup-review, token-efficiency-review,
    # ai-provenance-review) — unlike a missing Scope:, this is not a defect,
    # so it gets no entry in warnings either.
    roster = [
        ("correctness-review", "always", True),
        ("claude-setup-review", SL.SCOPE_ON_DEMAND, False),
    ]
    lenses, warnings = SL.applicable_lenses(["foo.py"], roster)
    assert lenses == ["correctness-review"]
    assert warnings == []


# --------------------------------------------------------------------------
# integration — real agent files + registry via the CLI
# --------------------------------------------------------------------------
def _run(*files, agents_dir=None, registry=None, added=None):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
    args = [sys.executable, str(_SCRIPT), "--files", *files]
    if agents_dir is not None:
        args += ["--agents-dir", str(agents_dir)]
    if registry is not None:
        args += ["--registry", str(registry)]
    if added is not None:
        args += ["--added", *added]
    r = subprocess.run(args, capture_output=True, text=True, check=False, env=env)
    return r


def test_cli_backend_only_diff():
    r = _run("plugins/dev-team/scripts/foo.py")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    lenses = out["lenses"]
    for excluded in (
        "a11y-review",
        "js-fp-review",
        "component-architecture-review",
        "react-reactivity-review",
        "vue-reactivity-review",
        "angular-reactivity-review",
    ):
        assert excluded not in lenses, f"{excluded} should not fire on a .py diff"
    for always in ("security-review", "correctness-review", "spec-compliance-review"):
        assert always in lenses


def test_cli_backend_only_diff_emits_no_separator_row_garbage():
    # Regression: the registry markdown separator row must not become a "-------" lens.
    out = json.loads(_run("plugins/dev-team/scripts/foo.py").stdout)
    both = set(out["lenses"]) | set(out["warnings"])
    assert not any(set(name) <= {"-"} for name in both), f"dash-only garbage in {both}"


def test_cli_tsx_diff_includes_frontend_but_not_reactivity():
    r = _run("src/App.tsx")
    assert r.returncode == 0
    lenses = json.loads(r.stdout)["lenses"]
    for inc in ("component-architecture-review", "a11y-review", "js-fp-review"):
        assert inc in lenses
    for exc in ("react-reactivity-review", "vue-reactivity-review", "angular-reactivity-review"):
        assert exc not in lenses


def test_cli_non_review_agents_never_appear():
    r = _run("src/util.py")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "correctness-review" in out["lenses"]  # guard: roster actually resolved
    both = set(out["lenses"]) | set(out["warnings"])
    for nonlens in (
        "progress-guardian",
        "quality-reviewer",
        "spec-reviewer",
        "data-flow-tracer",
        "mutation-kill",
        "session-analysis",
        "claude-setup-review",
        "token-efficiency-review",
        "ai-provenance-review",
    ):
        assert nonlens not in both


def test_cli_opus_lenses_sort_after_non_opus():
    # Corroborating integration check; the robust sort guard is the pure
    # test_cheap_first_ordering_follows_model_not_name. Depends on live roster
    # frontmatter: security-review declares model: opus, a11y-review does not —
    # a frontmatter change that flips a bucket is a conscious update to this test.
    r = _run("src/App.tsx")
    assert r.returncode == 0
    lenses = json.loads(r.stdout)["lenses"]
    assert lenses.index("a11y-review") < lenses.index("security-review")


def test_cli_fails_open_on_nonexistent_agents_dir(tmp_path):
    # Registry is real (so the roster is known), but no agent file is readable.
    r = _run("app.py", agents_dir=tmp_path / "nope")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    # Include-biased: every roster lens is returned + warned, none raise.
    assert "security-review" in out["lenses"]
    assert "security-review" in out["warnings"]


def test_cli_fails_open_on_unreadable_registry(tmp_path):
    r = _run("app.py", registry=tmp_path / "nope.md")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["lenses"] == []
    assert any(w.startswith("unreadable-registry:") for w in out["warnings"])


def test_cli_added_flag_narrows_component_architecture_review_to_added_files():
    # Modified-only .tsx: excluded from /code-review's per-diff panel now
    # that component-architecture-review's Scope is added-only (#1733).
    # added=[] states "an --added flag was supplied, with zero added files"
    # explicitly, rather than relying on argparse's option-boundary behavior
    # to infer it from a bare trailing "--added" (test-review/test-smell-review).
    r = _run("src/App.tsx", added=[])
    assert r.returncode == 0
    assert "component-architecture-review" not in json.loads(r.stdout)["lenses"]


def test_cli_added_flag_includes_matching_added_file():
    r = _run("src/App.tsx", added=["src/App.tsx"])
    assert r.returncode == 0
    assert "component-architecture-review" in json.loads(r.stdout)["lenses"]


def test_cli_without_added_flag_matches_plain_glob_fail_safe():
    # No --added at all (e.g. /build's caller): unchanged pre-#1733 behavior.
    r = _run("src/App.tsx")
    assert r.returncode == 0
    assert "component-architecture-review" in json.loads(r.stdout)["lenses"]


def test_cli_empty_files_yields_no_lenses():
    r = _run()
    assert json.loads(r.stdout)["lenses"] == []


def test_cli_files_from_stdin():
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files-from", "-"],
        input="src/App.tsx\n",
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    assert "component-architecture-review" in json.loads(r.stdout)["lenses"]


def test_cli_files_from_combines_with_files():
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files", "src/App.tsx", "--files-from", "-"],
        input="src/handler.ts\n",
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    lenses = json.loads(r.stdout)["lenses"]
    assert "component-architecture-review" in lenses  # from --files
    assert "js-fp-review" in lenses  # from --files-from


def test_cli_files_from_missing_file_fails_open_but_warns():
    # Fails open (still returns the always-on lens, exit 0) but the failure
    # is NOT silent — an unreadable --files-from must not read the same as
    # "nothing changed" (security-review: a silently-empty review gate).
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files", "app.py", "--files-from", "/nonexistent/path.txt"],
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert "correctness-review" in out["lenses"]
    assert any(w.startswith("unreadable-files-from:") for w in out["warnings"])


def test_cli_files_from_readable_empty_file_emits_no_warning():
    # A genuinely empty (but readable) --files-from source is not an error —
    # only an unreadable one is.
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files-from", "-"],
        input="",
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert not any(w.startswith("unreadable-files-from:") for w in out["warnings"])


def test_cli_added_from_stdin_narrows_added_only_scope():
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files", "src/App.tsx", "--added-from", "-"],
        input="src/App.tsx\n",
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    assert "component-architecture-review" in json.loads(r.stdout)["lenses"]


def test_cli_added_from_stdin_empty_excludes_added_only_scope():
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files", "src/App.tsx", "--added-from", "-"],
        input="",
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    assert "component-architecture-review" not in json.loads(r.stdout)["lenses"]


def test_cli_added_from_missing_file_warns():
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files", "src/App.tsx", "--added-from", "/nonexistent/added.txt"],
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert any(w.startswith("unreadable-added-from:") for w in out["warnings"])


def test_cli_added_and_added_from_combine():
    r = subprocess.run(
        [
            sys.executable, str(_SCRIPT), "--files", "src/App.tsx", "src/Other.vue",
            "--added", "src/App.tsx", "--added-from", "-",
        ],
        input="src/Other.vue\n",
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode == 0
    assert "component-architecture-review" in json.loads(r.stdout)["lenses"]


def test_cli_rejects_both_flags_reading_stdin():
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--files-from", "-", "--added-from", "-"],
        capture_output=True, text=True, check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"},
    )
    assert r.returncode != 0
    assert "cannot both read stdin" in r.stderr


# ---------------------------------------------------------------------------
# #1523 — frozen equivalence baseline for /code-review Step 3 adoption.
# ALWAYS_LENSES and the expected sets are hand-derived from the agents' own
# Scope: declarations (the pre-#1523 in-model rule's output), NOT copied from
# select_lenses' output — so a match proves equivalence rather than restating
# the resolver. A new Scope: always review lens must update ALWAYS_LENSES
# deliberately (that break is the intended "review the baseline" signal).
# ---------------------------------------------------------------------------
# `claude-setup-review` was here until it declared `Scope: on-demand`: it
# reviews the harness (CLAUDE.md, rules, skills, agent frontmatter), not the
# changeset, so `Scope: always` had it joining an 18-lens panel for a
# two-file JS change in a project with no Claude config at all. It is now
# dispatched on demand by the user-invocable `/claude-setup-review` command.
# `ai-provenance-review` and `token-efficiency-review` moved the same way
# (#1733): both are repo-wide drift/trend metrics, not per-diff correctness
# gates, so they now run only in the whole-tree `/repo-review` skill (#1735).
# All three declare `Scope: on-demand` directly (SL.SCOPE_ON_DEMAND) rather
# than being listed in `review_roster.NON_REVIEW_AGENTS`.
ALWAYS_LENSES = {
    "arch-review", "complexity-review",
    "concurrency-review", "correctness-review", "doc-review", "domain-review",
    "naming-review", "performance-review", "refactor-opportunity-review",
    "security-review", "spec-compliance-review", "structure-review", "test-review",
    "test-smell-review",
}
FILE_TYPE_LENSES = {
    "a11y-review", "js-fp-review", "component-architecture-review",
}
# `component-architecture-review`'s Scope is now `(SCOPE_ADDED_ONLY, globs)`,
# not a plain glob list (#1733) — it still belongs in FILE_TYPE_LENSES
# conceptually (file-type-gated, not `Scope: always`), so this helper picks
# both scope shapes apart from `test_file_type_lens_set_is_pinned_to_the_known_three`'s
# `isinstance(scope, list)` check rather than folding it into that check.
def _is_file_type_scope(scope) -> bool:
    return isinstance(scope, list) or (
        isinstance(scope, tuple) and scope and scope[0] == SL.SCOPE_ADDED_ONLY
    )
REACTIVITY_LENSES = {
    "react-reactivity-review", "vue-reactivity-review", "angular-reactivity-review",
}

_BASELINE = [
    (["svc/foo.py"], set()),                                                    # backend — A only
    (["docs/x.md"], set()),                                                     # docs — A only
    (["svc/handler.ts"], {"js-fp-review"}),                                     # .ts→js-fp boundary
    (["src/App.tsx"], {"js-fp-review", "a11y-review", "component-architecture-review"}),
    (["src/W.vue"], {"a11y-review", "component-architecture-review"}),          # NOT js-fp
    (["src/W.svelte"], {"a11y-review", "component-architecture-review"}),        # the svelte lens is gone (#1524)
    (["a/x.component.ts"], {"js-fp-review", "component-architecture-review"}),  # NOT a11y
    (["tpl/p.html"], {"a11y-review"}),                                          # a11y only
    # .component.html matches BOTH a11y (.html suffix) and component-architecture (.component.html).
    (["a/x.component.html"], {"a11y-review", "component-architecture-review"}),
    # multi-file union pulls file-type lenses from both members (.ts→js-fp; .svelte→a11y+comp-arch).
    (["svc/handler.ts", "src/W.svelte"],
     {"js-fp-review", "a11y-review", "component-architecture-review"}),
]


@pytest.mark.parametrize("files,extra", _BASELINE)
def test_frozen_baseline_selection(files, extra):
    lenses = set(json.loads(_run(*files).stdout)["lenses"])
    assert lenses == ALWAYS_LENSES | extra


def test_manifest_governed_reactivity_lenses_never_in_roster():
    # Input-independent invariant (build_review_roster excludes MANIFEST_GOVERNED),
    # so asserted once rather than per baseline shape.
    lenses = set(json.loads(_run("src/App.tsx").stdout)["lenses"])
    assert lenses.isdisjoint(REACTIVITY_LENSES)


def test_baseline_fixture_exercises_every_file_type_lens():
    # Guards the _BASELINE fixture table (not select_lenses runtime): every
    # file-type lens must be triggered by at least one shape.
    covered = set()
    for _files, extra in _BASELINE:
        covered |= extra
    assert FILE_TYPE_LENSES <= covered


def test_file_type_lens_set_is_pinned_to_the_known_three():
    # Guard: a future agent introducing a new file-type Scope pattern trips this,
    # forcing a new baseline shape rather than going silently unverified.
    roster, _ = SL.build_review_roster(
        SL._HERE.parent / "agents", SL._HERE.parent / "knowledge" / "agent-registry.md"
    )
    file_type = {name for name, scope, _ in roster if _is_file_type_scope(scope)}
    assert file_type == FILE_TYPE_LENSES
    always = {name for name, scope, _ in roster if scope == "always"}
    assert always == ALWAYS_LENSES


# review-config.json "enabled: false" honoring is orchestrator-executed prose
# (no shared function implements it), so it has no executable unit oracle — a
# set-difference test would be a self-referential tautology. Its presence is
# guarded instead by the content-guard in test_code_review_frontend_dispatch.py
# (review-config.json paragraph still in Step 3). See #1523 plan AC6.
