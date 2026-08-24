#!/usr/bin/env python3
"""Resolve which review lenses apply to a set of changed files (#1516).

Given changed file paths, return the review-agent lenses whose ``Scope:``
declaration matches, ordered cheap-first (non-opus before opus). ``/build``'s
inline review checkpoints call this to avoid dispatching lenses with no
matching surface in the diff (a backend-only diff should not spend tokens on
frontend/UI lenses). ``/code-review`` Step 3 also adopted this resolver
(#1533) — both live call sites now share every rule below, not just the
ones present at #1523.
A ``Scope: always`` lens named in ``NON_EXECUTABLE_SKIP_ELIGIBLE`` is
additionally excluded when every changed file is non-executable
(docs/config/assets/lockfiles, never functional Claude-config markdown —
see ``NON_EXECUTABLE_EXTENSIONS`` and ``doc_classification.is_functional_config``), since
that lens's own Skip clause would otherwise just self-report
``{"status": "skip"}`` at opus, high-effort cost.

Roster source: the **Review Agents** table in ``knowledge/agent-registry.md``
(the curated lens list), minus the shared ``NON_REVIEW_AGENTS`` boundary and
the manifest-governed framework-reactivity agents — see ``MANIFEST_GOVERNED``.

Design: ``parse_scope`` and ``applicable_lenses`` are pure (unit-testable with
a synthetic roster). ``build_review_roster`` and ``_read_lines_from`` are the
I/O boundaries; both fail open (a read error never raises) and both report
the failure in ``warnings`` rather than silently narrowing the result —
``unreadable-registry:<file>`` / ``unreadable-files-from:<path>`` /
``unreadable-added-from:<path>``. An affected *agent* additionally stays
include-biased (``build_review_roster``'s unreadable-agent-file case); an
affected *file list* does not fabricate paths, so its warning is the only
signal that the returned list is short.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import review_roster

# skills/code-review/scripts/change_shape.py's runtime-surface gate already
# solves "is this path functional Claude-config, never skippable regardless
# of extension" — reuse its shared predicate (#1477, extended #1923) rather
# than adding a fourth, independently-drifting copy of the same
# classification (a real defect a prior draft of this filter had: `.md`
# alone made `plugins/dev-team/agents/*.md` — this very repo's shipped
# agent behavior — read as "non-executable"). Same cross-boundary import
# pattern that module already uses.
_HOOKS_LIB_DIR = _HERE.parent / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

# No `except ImportError` fallback (#1968). The fallback this replaced was a
# hand-written second copy of `is_functional_config`, and nothing could catch
# it drifting: the guard that claimed to (`test_select_lenses.py`'s
# `test_is_functional_config_matches_doc_classification_module`) compared the
# canonical implementation against itself whenever the import succeeded — which
# is always, here — so sabotaging the fallback to `return False` left the whole
# suite green. `hooks/lib/` ships inside this same plugin; an unreachable one is
# a broken install, not a supported degraded mode.
try:
    from doc_classification import (
        is_functional_config,  # type: ignore[import-not-found]
    )
except ImportError as exc:  # pragma: no cover - broken install, not a supported mode
    raise ImportError(
        f"{__name__} requires the shared classifier 'doc_classification' from "
        f"the dev-team plugin's hooks/lib, which could not be imported.\n"
        f"  searched: {_HOOKS_LIB_DIR}\n"
        f"  exists:   {_HOOKS_LIB_DIR.is_dir()}\n"
        "This module deliberately has no fallback copy of the classifier "
        "(#1968) — a divergent stand-in silently mis-classifies files. Fix the "
        "install or the path rather than re-adding a local implementation."
    ) from exc

# Framework-reactivity lenses declare bare ``**/*.ts`` / ``**/*.js`` globs, but
# their real trigger is a dependency-manifest match (``/code-review`` Step 3's
# separate rule), not a file-path match. Keep them OUT of this resolver's remit
# so a plain Node/TS backend with no React/Vue/Angular does not get reactivity
# lenses. MAINTENANCE: any new manifest-governed framework-reactivity agent
# with bare ``**/*.ts|js`` globs must be added here.
MANIFEST_GOVERNED = {
    "react-reactivity-review",
    "vue-reactivity-review",
    "angular-reactivity-review",
}

_SCOPE_RE = review_roster.SCOPE_LINE_RE
_MODEL_RE = re.compile(r"^\s*model\s*:\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*-\s*(\S+)")
_EXT_TOKEN_RE = re.compile(r"`?(\.\w[\w.]*)`?")
# Review Agents table rows look like: | <name> | `agents/<name>.md` | ... |
# The name must start with a letter so the markdown separator row
# (| ------- | ------ | ... |) is not captured as a bogus "-------" lens.
_TABLE_ROW_RE = re.compile(r"^\|\s*([a-z][a-z0-9-]*)\s*\|")

# The sentinel an agent uses to declare it applies to every diff (`Scope: always`).
SCOPE_ALWAYS = "always"
# The sentinel an agent uses to declare it should only fire when a matching
# file is newly *added*, not merely modified (#1733's dual-placement rule for
# `component-architecture-review`: unconditional whole-inventory pass in
# `/repo-review`, narrowed to added-only in `/code-review`'s per-diff panel).
# Parsed the same way as the empty-inline-value case (bullet block of globs)
# and encoded as `(SCOPE_ADDED_ONLY, globs)` so callers can tell it apart from
# a plain glob-list scope.
SCOPE_ADDED_ONLY = "added-only"
# The sentinel an agent uses to declare it is a genuine review agent whose
# findings are properties of the whole repository, not any single diff, and
# so must never be dispatched by the per-diff resolver — only by name (e.g.
# `/claude-setup-review`) or by the whole-tree `/repo-review` skill (#1735).
# A bare declaration, no bullet block: unlike `added-only`, there is no glob
# data to carry, so the resolver just excludes the lens outright. Replaces a
# prior, competing mechanism (listing the agent in `NON_REVIEW_AGENTS`) that
# also incorrectly exempted it from the `Scope:` declaration requirement it
# actually satisfies — see `scripts/lib/review_roster.py`'s docstring.
SCOPE_ON_DEMAND = "on-demand"
# Heading substring that marks the Review Agents section of agent-registry.md.
# Named so a heading rename over there is greppable from here (the coupling).
_REVIEW_AGENTS_HEADING_MARKER = "review agent"

# Lenses whose own Skip clause covers "static assets, configuration,
# markup, or documentation with no executable logic" / "generated code,
# vendored dependencies, or lockfiles" verbatim, checked directly against
# each candidate's own agent-body text before being added here (#1923
# review round): each would only ever self-report `{"status": "skip"}` on
# an all-non-executable diff, so dispatching an opus, high-effort model
# just to hear "skip" is pure waste.
#
# Deliberately ONE member today, not "every opus-tier always lens" —
# `security-review`, `arch-review`, and `domain-review` were considered and
# REJECTED: their own Skip clauses do not authorize this. security-review's
# clause covers only "static assets, images, or documentation", not
# config/lockfiles (`NON_EXECUTABLE_EXTENSIONS` includes both), and its own
# "## Scope — files always in scope" section mandates scanning some of the
# very file classes this filter would suppress (infra manifests, configs)
# for hardcoded credentials — a real, exploitable coverage gap this filter
# would otherwise create for A08.review-manipulation/A05 detection.
# arch-review's clause is about ADR/module-boundary *absence*, not a
# docs-only diff — a pure-markdown ADR update is exactly the case its own
# `## Detect` section (ADR compliance) exists to catch, so filtering it on
# `.md` would drop the one check aimed at that content. domain-review's
# clause is "infra-only code" / "no business logic present", which is a
# file-content judgment, not a file-type one this filter can safely proxy.
#
# An explicit allowlist (matching this file's own MANIFEST_GOVERNED
# precedent above) rather than an implicit `is_opus` check: a future opus
# `Scope: always` lens defaults to NOT being filtered until it is added
# here deliberately, after the same verification against its own Skip
# clause — so a Skip-clause change on `correctness-review` (or a new
# candidate with different semantics) can't silently start/stop being
# filtered with nothing forcing that decision. MAINTENANCE: re-verify
# against the named agent's own Skip clause before adding or keeping a name
# here; remove it the moment that clause no longer matches.
#
# Relationship to `skills/code-review/scripts/change_shape.py`'s
# `LOW_YIELD_LENSES` (`["performance-review", "correctness-review"]`):
# that gate is `/code-review`-Step-3-specific and already drops
# correctness-review on a no-runtime-surface changeset (with this same
# functional-config carve-out). This allowlist is NOT redundant with it —
# `/build`'s inline review checkpoints call `applicable_lenses` directly
# and never consult `change_shape.py`, so without this, correctness-review
# still paid full opus cost on every doc-only `/build` step. The two lists
# legitimately overlap on `correctness-review` rather than duplicating by
# accident; `performance-review` is haiku-tier and not this filter's cost
# concern, so it is intentionally absent here.
# frozenset (not a plain set), matching `doc_classification.py`'s own
# convention for these shared-literal-shaped tables: this allowlist governs
# which review lenses may be dropped, so it must not be mutable by any
# importer after module load.
NON_EXECUTABLE_SKIP_ELIGIBLE = frozenset({
    "correctness-review",
})

# Extensions/basenames the NON_EXECUTABLE_SKIP_ELIGIBLE lens(es) above would
# only ever self-report `{"status": "skip"}` against. Deliberately
# conservative: `.yaml`/`.yml` are excluded because CI workflow files
# routinely embed real conditionals/shell logic correctness-review
# legitimately checks (see its category 5); a lockfile written in YAML is
# instead named explicitly in NON_EXECUTABLE_BASENAMES. Safe to keep `.json`
# here even though it is a real security/execution surface elsewhere in this
# repo (`settings.json` hook registrations, `package.json` scripts) —
# `security-review` is not on the allowlist above, and correctness-review's
# "does this code do what it evidently intends" lens has no bearing on that
# concern. Deliberately DIFFERENT from `change_shape.py`'s own runtime-surface
# classifier, not merely a copy of it: the binary/vector asset extensions
# below (`.svg`/`.png`/etc.) appear in neither that module's `_DOC_EXTENSIONS`
# nor its `_CONFIG_EXTENSIONS`, so an asset-only diff is "runtime surface,
# keep every lens" there but "non-executable, skip correctness-review" here.
# That asymmetry is safe today (it can only make this module drop a lens
# `change_shape.py` would have kept, never the reverse, and only for
# correctness-review — no other lens reads this constant), but re-check it
# against `change_shape.py` before adding a second name to the allowlist
# above, per that constant's own MAINTENANCE note.
NON_EXECUTABLE_EXTENSIONS = frozenset({
    ".md", ".mdx", ".rst", ".txt",
    ".json", ".toml", ".ini", ".cfg",
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf",
    ".lock",
})
NON_EXECUTABLE_BASENAMES = frozenset({
    "LICENSE", "LICENSE.txt", ".gitignore", ".editorconfig", ".gitattributes",
    "pnpm-lock.yaml",
})

def _is_non_executable_file(file_path: str) -> bool:
    """True if ``file_path`` is a static asset, inert config/data,
    documentation, or a lockfile — see NON_EXECUTABLE_EXTENSIONS above.
    Never true for functional Claude-config markdown/paths (checked
    first, via the shared `is_functional_config` — same predicate
    `change_shape.py` uses), regardless of extension."""
    if is_functional_config(file_path):
        return False
    name = Path(file_path).name
    if name in NON_EXECUTABLE_BASENAMES:
        return True
    return Path(file_path).suffix.lower() in NON_EXECUTABLE_EXTENSIONS


def _is_all_non_executable(changed_files) -> bool:
    """True iff every file in ``changed_files`` is non-executable. Callers
    already special-case an empty list before reaching this."""
    return bool(changed_files) and all(
        _is_non_executable_file(f) for f in changed_files
    )


def _should_skip_non_executable(name: str, changed_files) -> bool:
    """True if ``name`` is on the skip allowlist and every changed file is
    non-executable — mirrors ``_added_only_eligible``'s role below for the
    added-only branch, hoisting a compound condition out of the
    ``applicable_lenses`` dispatcher's own branch body."""
    return name in NON_EXECUTABLE_SKIP_ELIGIBLE and _is_all_non_executable(changed_files)


def _consume_bullet_block(lines, start_index):
    """Collect a contiguous ``- <glob>`` bullet block starting after
    ``start_index``; stop at the first non-bullet line. Returns the globs."""
    globs = []
    for nxt in lines[start_index + 1:]:
        b = _BULLET_RE.match(nxt)
        if not b:
            break
        globs.append(b.group(1).strip("`"))
    return globs


def parse_scope(text: str):
    """Return ``"always"`` | ``"on-demand"`` | ``list[str]`` |
    ``(SCOPE_ADDED_ONLY, list[str])`` | ``None`` from agent markdown.

    The **first** ``Scope:`` line is authoritative. An empty inline value
    followed by a ``- **/*.ext`` bullet block yields that structured,
    fnmatch-ready list (preferred over the free-text second ``Scope:`` line some
    agents also carry). ``Scope: always`` -> ``"always"``. ``Scope: on-demand``
    -> ``SCOPE_ON_DEMAND`` (a bare declaration — no bullet block, unlike
    ``added-only``). ``Scope: added-only`` followed by the same bullet-block
    shape -> ``(SCOPE_ADDED_ONLY, globs)`` (no bullet block -> ``None``, same
    fail-open rule as a missing declaration). Other inline prose -> ``.ext``
    tokens extracted as a fallback (``None`` if it names no extension). No
    ``Scope:`` line -> ``None``.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _SCOPE_RE.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if value.lower() == SCOPE_ALWAYS:
            return SCOPE_ALWAYS
        if value.lower() == SCOPE_ON_DEMAND:
            return SCOPE_ON_DEMAND
        if value.lower() == SCOPE_ADDED_ONLY:
            globs = _consume_bullet_block(lines, i)
            return (SCOPE_ADDED_ONLY, globs) if globs else None
        if value:
            tokens = _EXT_TOKEN_RE.findall(value)
            return [f"**/*{t}" for t in tokens] or None
        # Empty inline value: consume the following bullet block (authoritative).
        return _consume_bullet_block(lines, i) or None
    return None


def parse_model_is_opus(text: str) -> bool:
    """True if the agent's ``model:`` frontmatter resolves to an opus tier."""
    for line in text.splitlines():
        m = _MODEL_RE.match(line)
        if m:
            return "opus" in m.group(1).strip().lower()
    return False


def _matches(file_path: str, pattern: str) -> bool:
    """Extension-aware glob match, robust to directory depth.

    ``**/*.tsx`` -> match any path ending ``.tsx``; ``**/*.component.ts`` ->
    ending ``.component.ts``. Directory-insensitive on purpose (fnmatch's ``*``
    would otherwise require a ``/`` for a ``**/`` prefix and miss top-level
    files). A non-glob pattern matches by exact path or basename.
    """
    if "*" in pattern:
        suffix = pattern.rsplit("*", 1)[-1]
        return bool(suffix) and file_path.endswith(suffix)
    return file_path == pattern or Path(file_path).name == pattern


def _scope_matches(scope, changed_files) -> bool:
    """True if a glob-list ``scope`` matches any changed file (``"always"`` is
    handled by the caller, not here)."""
    return any(_matches(f, g) for f in changed_files for g in scope)


def _is_added_only_scope(scope) -> bool:
    """True if ``scope`` is the ``(SCOPE_ADDED_ONLY, globs)`` shape."""
    return isinstance(scope, tuple) and scope[0] == SCOPE_ADDED_ONLY


def _added_only_eligible(globs, changed_files, added_files) -> bool:
    """True if an added-only scope's ``globs`` match within the eligible set.

    ``added_files=None`` (no change-type data supplied) falls back to
    matching any changed file — the fail-safe direction every other
    ambiguity in this module already resolves toward. A supplied set (even
    empty) narrows eligibility to only files present in it.
    """
    eligible = changed_files if added_files is None else [
        f for f in changed_files if f in added_files
    ]
    return bool(eligible) and _scope_matches(globs, eligible)


def applicable_lenses(changed_files, roster, added_files=None):
    """Pure resolver. ``roster`` = ``[(name, scope, is_opus)]``. Returns
    ``(lenses, warnings)`` with lenses ordered cheap-first (non-opus, then opus).

    An empty ``changed_files`` yields ``([], [])`` — nothing to review, so no
    lens (not even ``Scope: always``) is selected. ``scope is None`` ->
    include-biased + warn (never non-executable-filtered, regardless of
    ``name`` or ``is_opus`` — that filter applies only inside this
    ``SCOPE_ALWAYS`` branch); ``"always"`` -> include, UNLESS ``name`` is on
    the ``NON_EXECUTABLE_SKIP_ELIGIBLE`` allowlist and every changed file is
    non-executable (see ``_should_skip_non_executable``) — that combination
    is excluded and warned as ``skipped-non-executable:<name>`` rather than
    paying an opus round trip for a self-reported skip; glob list -> include
    iff any changed file matches; ``SCOPE_ON_DEMAND`` -> never include, no
    warning (a deliberate, self-declared exclusion, not a defect to
    surface).

    ``added_files`` (#1733) narrows a ``(SCOPE_ADDED_ONLY, globs)`` scope to
    only the changed files that are also newly *added* — but **only when the
    caller actually supplies it**. ``added_files=None`` (the default — a
    caller, e.g. ``/build``'s inline checkpoints, that has no change-type data
    to offer) makes an added-only scope behave exactly like a plain glob list,
    matching any changed file. This is deliberately fail-safe in the same
    direction every other gate in this module already leans: ambiguity always
    resolves toward *keeping* a lens, never toward silently dropping one a
    caller never asked to narrow. When that fallback fires (a lens selected
    via an added-only scope with no ``added_files`` supplied), it is recorded
    in ``warnings`` as ``unnarrowed-added-only:<name>`` — the same "never
    silently dropped" transparency the missing-``Scope:`` case already gets,
    applied to a silent *widening* instead.
    """
    if not changed_files:
        return [], []
    selected: list[tuple[str, bool]] = []
    warnings: list[str] = []
    for name, scope, is_opus in roster:
        if scope is None:
            warnings.append(name)
            selected.append((name, is_opus))
        elif scope == SCOPE_ALWAYS:
            if _should_skip_non_executable(name, changed_files):
                warnings.append(f"skipped-non-executable:{name}")
                continue
            selected.append((name, is_opus))
        elif scope == SCOPE_ON_DEMAND:
            continue  # never dispatched by the per-diff resolver, by design
        elif _is_added_only_scope(scope):
            if not _added_only_eligible(scope[1], changed_files, added_files):
                continue
            selected.append((name, is_opus))
            if added_files is None:
                warnings.append(f"unnarrowed-added-only:{name}")
        elif _scope_matches(scope, changed_files):
            selected.append((name, is_opus))
    # Stable cheap-first: False (non-opus) sorts before True (opus).
    selected.sort(key=lambda pair: pair[1])
    return [name for name, _ in selected], warnings


def _registry_lens_names(registry_text: str) -> list[str]:
    """Names in the Review Agents table section of agent-registry.md."""
    names: list[str] = []
    in_section = False
    for line in registry_text.splitlines():
        if line.startswith("## "):
            in_section = _REVIEW_AGENTS_HEADING_MARKER in line.lower()
            continue
        if in_section:
            m = _TABLE_ROW_RE.match(line)
            if m:
                names.append(m.group(1))
    return names


def build_review_roster(agents_dir: Path, registry_path: Path):
    """I/O boundary: build ``roster = [(name, scope, is_opus)]`` from disk.

    Fails open: an unreadable registry yields ``([], [warning])``; an unreadable
    agent file is include-biased (``scope=None`` -> included + warned) rather
    than raising.
    """
    warnings: list[str] = []
    try:
        registry_text = registry_path.read_text(encoding="utf-8")
    except OSError:
        return [], [f"unreadable-registry:{registry_path.name}"]
    roster = []
    for name in _registry_lens_names(registry_text):
        if name in review_roster.NON_REVIEW_AGENTS or name in MANIFEST_GOVERNED:
            continue
        try:
            text = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        except OSError:
            roster.append((name, None, False))  # include-biased fail-open
            continue
        roster.append((name, parse_scope(text), parse_model_is_opus(text)))
    return roster, warnings


def _read_lines_from(path_or_dash: str):
    """Read newline-separated, non-blank lines from a file or stdin (``-``).

    Returns ``(lines, error)``. Never raises — a missing or unreadable file
    contributes no lines, matching `changed_file_list.py`'s identical helper
    — but unlike that helper, the failure is reported back via ``error``
    (``None`` on success, including a genuinely empty readable source) so
    the caller can tell "nothing was there" apart from "couldn't read it"
    and warn on the latter. Silently treating the two the same would make an
    unreadable ``--files-from`` indistinguishable from a legitimate
    "nothing changed" result.
    """
    try:
        if path_or_dash == "-":
            text = sys.stdin.read()
        else:
            with open(path_or_dash, encoding="utf-8") as handle:
                text = handle.read()
    except (OSError, ValueError) as exc:
        return [], type(exc).__name__
    return [line for line in text.splitlines() if line.strip()], None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Resolve applicable review lenses.")
    parser.add_argument("--files", nargs="*", default=[], help="Changed file paths")
    parser.add_argument(
        "--files-from", default=None,
        help=(
            "Read newline-separated changed-file paths from this file "
            "('-' for stdin), combined with --files. Prefer this for a "
            "machine-generated or caller-uncontrolled list: it avoids "
            "argparse's own argv-parsing hazards (a path starting with '-' "
            "reinterpreted as a flag, word-splitting on an unquoted space) "
            "— it does NOT by itself protect against a caller that "
            "builds the file this reads from by shell-interpolating "
            "untrusted path text; that boundary is the caller's to hold "
            "(mirrors changed_file_list.py's --name-status-from)."
        ),
    )
    parser.add_argument(
        "--added", nargs="*", default=None,
        help=(
            "Paths that are newly added (git change-type A) in this "
            "changeset, e.g. from changed_file_list.py's 'added' list. "
            "Narrows any 'Scope: added-only' lens to only these paths; "
            "omit both this and --added-from when the caller has no "
            "change-type data (fail-safe: added-only scopes then match "
            "like a plain glob list)."
        ),
    )
    parser.add_argument(
        "--added-from", default=None,
        help=(
            "Read newline-separated added-file paths from this file "
            "('-' for stdin), combined with --added. Same caveat as "
            "--files-from."
        ),
    )
    parser.add_argument("--agents-dir", type=Path, default=_HERE.parent / "agents")
    parser.add_argument(
        "--registry",
        type=Path,
        default=_HERE.parent / "knowledge" / "agent-registry.md",
    )
    args = parser.parse_args(argv)
    if args.files_from == "-" and args.added_from == "-":
        parser.error(
            "--files-from and --added-from cannot both read stdin ('-') — "
            "the second read gets nothing, silently. Use a file path or "
            "process substitution for at least one."
        )
    roster, roster_warnings = build_review_roster(args.agents_dir, args.registry)

    resolver_warnings: list[str] = []

    files = list(args.files)
    if args.files_from:
        extra, error = _read_lines_from(args.files_from)
        files.extend(extra)
        if error:
            resolver_warnings.append(f"unreadable-files-from:{args.files_from}")

    added_files = None
    if args.added is not None or args.added_from:
        added_files = set(args.added or [])
        if args.added_from:
            extra, error = _read_lines_from(args.added_from)
            added_files.update(extra)
            if error:
                resolver_warnings.append(f"unreadable-added-from:{args.added_from}")

    lenses, warnings = applicable_lenses(files, roster, added_files=added_files)
    all_warnings = roster_warnings + resolver_warnings + warnings
    print(json.dumps({"lenses": lenses, "warnings": all_warnings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
