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


def test_parse_scope_test_files():
    assert SL.parse_scope("Scope: test-files\nCites: foo\n") == SL.SCOPE_TEST_FILES


def test_test_files_scope_included_only_when_a_test_file_changed():
    roster = [("test-smell-review", SL.SCOPE_TEST_FILES, False)]
    changed = ["svc/foo.py", "tests/test_foo.py"]
    lenses, warnings = SL.applicable_lenses(
        changed, roster, test_files={"tests/test_foo.py"}
    )
    assert lenses == ["test-smell-review"]
    assert warnings == []
    lenses, _ = SL.applicable_lenses(["svc/foo.py"], roster, test_files=set())
    assert lenses == []


def test_test_files_scope_without_classification_is_include_biased_and_warns():
    """`test_files=None` means the caller offered no classification. Mirrors
    the added-only fallback: never silently drop a lens nobody asked to
    narrow, and say so in warnings rather than widening in silence."""
    roster = [("test-smell-review", SL.SCOPE_TEST_FILES, False)]
    lenses, warnings = SL.applicable_lenses(["svc/foo.py"], roster)
    assert lenses == ["test-smell-review"]
    assert warnings == ["unnarrowed-test-files:test-smell-review"]


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_pricing.py",       # Python prefix
        "svc/pricing_test.py",         # Python suffix
        "src/__tests__/cart.js",       # JS/TS directory
        "src/cart.test.ts",            # JS/TS suffix
        "src/cart.spec.tsx",           # JS/TS spec suffix
        "features/checkout.feature",   # Gherkin
        "e2e/checkout.steps.ts",       # step definitions
        "src/OrderTest.java",          # Java class-name convention
    ],
)
def test_test_file_subset_covers_every_name_based_indicator(path, tmp_path):
    """Each family from knowledge/test-file-indicators.md that resolves by
    name. Three of these (the `test_*.py` prefix, the `__tests__/` directory,
    the Java class-name rule) cannot be written as a `**/*.suffix` glob at
    all — which is why this scope is a sentinel over the shared classifier
    rather than a glob list that would have silently missed them."""
    assert SL.test_file_subset([path], root=tmp_path) == {path}


def test_test_file_subset_classifies_the_relative_path_not_the_checkout_path(tmp_path):
    """Regression: the classifier's `__tests__/` rule matches ANY path
    segment, so classifying `root / path` made every file in a checkout
    living under a directory named `__tests__` (a CI workspace at
    /build/__tests__/repo) read as a test."""
    workspace = tmp_path / "__tests__" / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text("x = 1\n")
    assert SL.test_file_subset(["src/app.py"], root=workspace) == set()


def test_test_file_subset_excludes_ordinary_source(tmp_path):
    assert SL.test_file_subset(["svc/pricing.py", "src/cart.ts"], root=tmp_path) == set()


def test_test_file_subset_reads_content_for_csharp_on_disk(tmp_path):
    """C# test-ness is an attribute in the file body, so the classifier reads
    it. Both answers must come from the real file, not from its name."""
    (tmp_path / "OrderTests.cs").write_text("[Fact]\npublic void Works() {}\n")
    (tmp_path / "Order.cs").write_text("public class Order {}\n")
    assert SL.test_file_subset(["OrderTests.cs", "Order.cs"], root=tmp_path) == {
        "OrderTests.cs"
    }


def test_test_file_subset_include_biases_a_present_but_unreadable_file(tmp_path):
    """The include-bias must cover "exists but could not be read" too, not
    just "not on disk": the shared probe returns "" for both, and treating
    that as "read it, found no test marker" silently drops the lens."""
    unreadable = tmp_path / "Order.cs"
    unreadable.write_text("[Fact]\npublic void Works() {}\n")
    unreadable.chmod(0o000)
    try:
        assert SL.test_file_subset(["Order.cs"], root=tmp_path) == {"Order.cs"}
    finally:
        unreadable.chmod(0o644)


def test_test_file_subset_is_include_biased_for_unreadable_content_probed_files(tmp_path):
    """A `.cs`/`.java` path not on disk (a deleted file, or a caller outside
    the checkout) cannot be classified by content. Counting it as a possible
    test keeps the lens — the same direction every other ambiguity in this
    module resolves toward — instead of silently dropping coverage."""
    assert SL.test_file_subset(["gone/Deleted.cs"], root=tmp_path) == {"gone/Deleted.cs"}
    # A name-classified language is unaffected: absence proves nothing is needed.
    assert SL.test_file_subset(["gone/deleted.py"], root=tmp_path) == set()


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


def test_non_executable_file_detects_docs_config_assets_and_lockfiles():
    for f in ("README.md", "package.json", "logo.svg", "yarn.lock", "Cargo.lock",
              "pnpm-lock.yaml", "LICENSE", ".gitignore", "notes.mdx", "guide.rst",
              "pyproject.toml", "setup.cfg", "banner.png", "LICENSE.txt", ".editorconfig"):
        assert SL._is_non_executable_file(f), f"{f} should be non-executable"
    for f in ("app.py", "handler.ts", "Makefile", "config.yaml", "deploy.yml"):
        assert not SL._is_non_executable_file(f), f"{f} should NOT be non-executable"


def test_non_executable_file_never_true_for_functional_claude_config():
    # A plain .md/.json suffix is never enough — a path that drives agent/
    # skill/command behavior stays "executable" regardless of extension
    # (#1923 review round: an earlier draft misclassified this repo's own
    # shipped plugins/dev-team/agents/*.md as non-executable documentation).
    for f in (
        "plugins/dev-team/agents/correctness-review.md",
        "plugins/dev-team/skills/build/SKILL.md",
        ".claude/settings.json",
        "plugins/dev-team/knowledge/agent-registry.md",
        "CLAUDE.md",
        "AGENTS.md",
    ):
        assert not SL._is_non_executable_file(f), f"{f} is functional config, must stay executable"


def test_non_executable_skip_eligible_justification_matches_agent_skip_clause():
    # Mechanically re-verifies NON_EXECUTABLE_SKIP_ELIGIBLE's own MAINTENANCE
    # comment ("re-verify against the named agent's own Skip clause before
    # adding or keeping a name here") instead of trusting prose: reads each
    # allowlisted agent's real `## Skip` section and asserts it still
    # contains the phrases the allowlist's justifying comment quotes. Fails
    # loudly if a future edit narrows the clause or renames the agent file,
    # rather than leaving the allowlist silently wrong.
    required_phrases = (
        "static assets, configuration, markup, or documentation with no executable logic",
        "generated code, vendored dependencies, or lockfiles",
    )
    for name in SL.NON_EXECUTABLE_SKIP_ELIGIBLE:
        agent_path = _REPO_ROOT / "plugins" / "dev-team" / "agents" / f"{name}.md"
        text = agent_path.read_text(encoding="utf-8")
        skip_section = text.split("## Skip", 1)[1].split("## Detect", 1)[0]
        for phrase in required_phrases:
            assert phrase in skip_section, (
                f"{name}.md's Skip clause no longer matches "
                f"NON_EXECUTABLE_SKIP_ELIGIBLE's justification: missing '{phrase}'"
            )


def test_security_review_never_on_non_executable_skip_allowlist():
    # Direct membership pin (not just a behavioral one) — security-review's
    # own Skip clause does not cover config/lockfiles, and its "## Scope —
    # files always in scope" section mandates scanning some of the file
    # classes this allowlist would otherwise suppress (#1923 review round).
    assert "security-review" not in SL.NON_EXECUTABLE_SKIP_ELIGIBLE


def test_is_functional_config_matches_change_shape_py_semantics():
    assert SL.is_functional_config("plugins/dev-team/agents/foo.md") is True
    assert SL.is_functional_config(".claude/settings.json") is True
    assert SL.is_functional_config("plugins/dev-team/templates/agents/python.md") is True
    assert SL.is_functional_config("CLAUDE.md") is True
    assert SL.is_functional_config("docs/x.md") is False
    assert SL.is_functional_config("README.md") is False


def test_all_non_executable_requires_every_file_to_match():
    assert SL._is_all_non_executable(["a.md", "b.json"]) is True
    assert SL._is_all_non_executable(["a.md", "b.py"]) is False
    assert SL._is_all_non_executable([]) is False


def test_allowlisted_always_lens_skipped_on_all_non_executable_diff():
    roster = [
        ("correctness-review", "always", True),
        ("spec-compliance-review", "always", False),
    ]
    lenses, warnings = SL.applicable_lenses(["docs/x.md"], roster)
    assert lenses == ["spec-compliance-review"]
    assert warnings == ["skipped-non-executable:correctness-review"]


def test_allowlisted_always_lens_still_runs_when_any_file_is_executable():
    roster = [("correctness-review", "always", True)]
    lenses, warnings = SL.applicable_lenses(["docs/x.md", "app.py"], roster)
    assert lenses == ["correctness-review"]
    assert warnings == []


def test_non_allowlisted_always_lens_never_filtered_by_non_executable_diff():
    # The property under test is allowlist membership, not opus tier — an
    # allowlisted non-opus lens would in fact be filtered (there is no
    # is_opus check left in `_should_skip_non_executable`), so this pins
    # security-review specifically: opus-tier, `Scope: always`, but absent
    # from NON_EXECUTABLE_SKIP_ELIGIBLE (#1923 review round: its own Skip
    # clause does not cover config/lockfiles the way correctness-review's
    # does), so it must survive an all-non-executable diff unfiltered.
    roster = [("security-review", "always", True)]
    lenses, warnings = SL.applicable_lenses(["docs/x.md"], roster)
    assert lenses == ["security-review"]
    assert warnings == []


def test_missing_scope_lens_never_non_executable_filtered_even_if_allowlisted():
    # The non-executable skip is wired only inside the SCOPE_ALWAYS branch —
    # a lens with scope=None (missing Scope:, include-biased) stays included
    # even when its name is on NON_EXECUTABLE_SKIP_ELIGIBLE and every changed
    # file is non-executable, pinning that the filter can't leak into the
    # missing-scope path.
    roster = [("correctness-review", None, True)]
    lenses, warnings = SL.applicable_lenses(["docs/x.md"], roster)
    assert lenses == ["correctness-review"]
    assert warnings == ["correctness-review"]  # missing-scope warning, not skipped-non-executable


def test_lens_not_on_skip_allowlist_still_runs_on_non_executable_diff():
    # Only names in NON_EXECUTABLE_SKIP_ELIGIBLE are filtered, regardless of
    # is_opus (checked both ways here) — a hypothetical future always lens
    # not yet added to that allowlist must stay included by default (the
    # coupling this allowlist exists to avoid).
    for is_opus in (True, False):
        roster = [("hypothetical-new-lens", "always", is_opus)]
        lenses, warnings = SL.applicable_lenses(["docs/x.md"], roster)
        assert lenses == ["hypothetical-new-lens"]
        assert warnings == []


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


def test_cli_test_files_scope_resolves_against_the_real_working_directory(tmp_path):
    """End-to-end through `main()`, which is where `test_file_subset` is
    actually wired: the pure resolver tests above cannot catch a bug in the
    cwd-relative path resolution or the real on-disk classification. Uses a
    C# pair specifically — the one family whose answer comes from file
    CONTENT, so a broken read would show up here and nowhere else."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "OrderTests.cs").write_text("[Fact]\npublic void Works() {}\n")
    (tmp_path / "src" / "Order.cs").write_text("public class Order {}\n")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}

    def lenses_for(*files):
        r = subprocess.run(
            [sys.executable, str(_SCRIPT), "--files", *files],
            capture_output=True, text=True, check=False, env=env, cwd=str(tmp_path),
        )
        assert r.returncode == 0, r.stderr
        return set(json.loads(r.stdout)["lenses"])

    assert "test-smell-review" in lenses_for("src/OrderTests.cs")
    assert "test-smell-review" not in lenses_for("src/Order.cs")


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


def test_cli_docs_only_diff_skips_only_the_allowlisted_lens():
    r = _run("docs/README.md")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    for eligible in SL.NON_EXECUTABLE_SKIP_ELIGIBLE:
        assert eligible not in out["lenses"], f"{eligible} should skip a docs-only diff"
        assert f"skipped-non-executable:{eligible}" in out["warnings"]
    # Regression pin (#1923 review round): security-review/arch-review/
    # domain-review were considered for this allowlist and rejected — their
    # own Skip clauses don't authorize it — so they must still run.
    for still_runs in ("security-review", "arch-review", "domain-review", "spec-compliance-review"):
        assert still_runs in out["lenses"], f"{still_runs} must NOT skip a docs-only diff"


def test_cli_agent_markdown_only_diff_keeps_every_always_lens():
    # Functional Claude-config markdown is never "non-executable" (#1923
    # review round) — an all-agents/*.md diff must not lose any Scope:
    # always lens, including the allowlisted correctness-review.
    out = json.loads(_run("plugins/dev-team/agents/correctness-review.md").stdout)
    assert "correctness-review" in out["lenses"]
    assert not any(w.startswith("skipped-non-executable:") for w in out["warnings"])


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
# `refactor-opportunity-review` left the same way (#1976), for a reason
# specific to its charter rather than to per-diff cost: it assesses
# refactoring opportunities *after tests pass*, which is `/build`'s post-GREEN
# REFACTOR checkpoint, and in the review panel it re-covered ground
# `structure-review` (SRP, DRY, coupling, and — since #2093 folded
# `complexity-review` into it — nesting depth, cognitive load, and
# async-pattern judgment) already holds as `Scope: always`.
# `test-smell-review` is not here either, but it is NOT on-demand (#1978) —
# it declares the `test-files` sentinel below, so it still runs per-diff,
# just only when the diff touches a test file. `test-review` deliberately
# stays `Scope: always`: its coverage-gap check must see production diffs
# that add code *without* a matching test.
ALWAYS_LENSES = {
    "arch-review",
    "concurrency-review", "correctness-review", "doc-review", "domain-review",
    "naming-review", "performance-review",
    "security-review", "spec-compliance-review", "structure-review", "test-review",
}
FILE_TYPE_LENSES = {
    "a11y-review", "js-fp-review", "component-architecture-review",
}
# Lenses gated on "the changeset touches a test file" (#1978). Resolved
# against the shared encoding of knowledge/test-file-indicators.md, not a
# glob list — the glob vocabulary cannot express `test_*.py`, `__tests__/`,
# or the C#/Java annotation indicators.
TEST_FILE_LENSES = {"test-smell-review"}
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
    (["svc/handler.ts"], {"js-fp-review"}),                                     # .ts→js-fp boundary
    # docs/x.md alone is all-non-executable, so the allowlisted lens skips
    # (see test_allowlisted_always_lens_skipped_on_all_non_executable_diff
    # and test_cli_docs_only_diff_skips_only_the_allowlisted_lens below) —
    # pairing it with src/App.tsx instead of a second backend file keeps
    # this row distinct from the plain-backend row above: it proves every
    # always lens stays included on a mixed diff (not all files
    # non-executable) AND exercises the file-type-lens union, rather than
    # duplicating svc/foo.py's expected output with no new signal.
    (["docs/x.md", "src/App.tsx"], {"js-fp-review", "a11y-review", "component-architecture-review"}),
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
    # `test-files` scope (#1978), one row per indicator family the glob
    # vocabulary could NOT have expressed — the reason it is a sentinel.
    (["tests/test_pricing.py"], {"test-smell-review"}),            # test_*.py prefix
    (["src/__tests__/cart.js"],                                    # __tests__/ directory
     {"test-smell-review", "js-fp-review"}),
    (["src/cart.test.ts"], {"test-smell-review", "js-fp-review"}),  # *.test.* suffix
    # A production file next to a test file still triggers it (any-match, not all-match).
    (["svc/foo.py", "tests/test_foo.py"], {"test-smell-review"}),
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
    test_scoped = {
        name for name, scope, _ in roster if scope == SL.SCOPE_TEST_FILES
    }
    assert test_scoped == TEST_FILE_LENSES


# review-config.json "enabled: false" honoring is orchestrator-executed prose
# (no shared function implements it), so it has no executable unit oracle — a
# set-difference test would be a self-referential tautology. Its presence is
# guarded instead by the content-guard in test_code_review_frontend_dispatch.py
# (review-config.json paragraph still in Step 3). See #1523 plan AC6.
