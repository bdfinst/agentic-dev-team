#!/usr/bin/env python3
"""Architectural-impact gate for expensive structural lenses.

`arch-review` is `Scope: always` and opus-tier: it runs on every non-empty
changeset, including diffs that cannot possibly exhibit what it looks for.
Its declared scope is ADR compliance, **layer boundary violations**,
**dependency direction**, and pattern consistency — all of which are
properties of a codebase's *structure*. A diff that adds a guard clause
inside an existing function, with no import change, no new or moved file, no
manifest edit, and no public-interface change, has not moved any boundary
for it to evaluate.

This is the third gate in the same family, applied after the existing two
(`select_lenses.py`'s `Scope:` eligibility, then `change_shape.py`'s
runtime-surface gate, then `change_size.py`'s diff-size gate). It narrows by
*architectural signal* rather than by file type or diff size.

## Fail-safe, and deliberately include-biased

Any file this module cannot classify, any diff it cannot parse, and any empty
input all count as architectural impact and keep every lens. The gate can only
ever remove a lens it can prove has nothing to look at. Mirrors
`change_shape.py`'s own fail-safe posture — see that module.

## Why only `arch-review` in this pass

`domain-review` is the obvious next candidate and is deliberately NOT gated
here. Its scope includes "business logic placement", and putting business
logic into a controller method body is a real domain violation introduced by
a *body-only* edit with no structural signal at all — exactly the diff shape
this gate would skip. Gating it would create a silent coverage hole.

The same evidence-first discipline `verification-mode.md` applies to
tier-down opt-ins applies here: gate the one lens whose scope is
unambiguously structural, record the skip (`review-value.jsonl`'s
`dispatch_purpose`/agent split, #1624), and let measured data authorize
widening `GATED_LENSES` — not intuition about which lens "probably" no-ops.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: Lens -> the impact signals that justify dispatching it. A lens is dropped
#: only when NONE of its signals are present. Grow this map from #1624's
#: measured per-agent data, not from intuition (see module docstring).
GATED_LENSES = {
    "arch-review": frozenset(
        {"structure", "dependency", "manifest", "infra", "interface", "adr"}
    ),
}

#: Dependency-manifest basenames. A change here can move dependency direction
#: without touching a single source line.
_MANIFEST_NAMES = frozenset(
    {
        "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
        "requirements-dev.txt", "poetry.lock", "pipfile",
        "go.mod", "go.sum", "cargo.toml", "cargo.lock",
        "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
        "gemfile", "gemfile.lock", "composer.json", "composer.lock",
    }
)

_MANIFEST_SUFFIXES = (".csproj", ".fsproj", ".vbproj", ".sln")

#: Path fragments that mark deployment/runtime topology.
_INFRA_SEGMENTS = frozenset({"terraform", "helm", "k8s", "kubernetes", ".github"})
_INFRA_NAMES = frozenset(
    {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "procfile", "makefile"}
)
_INFRA_SUFFIXES = (".tf", ".tfvars")

#: Import / dependency-edge declarations across the languages this plugin
#: supports. Matched against ADDED and REMOVED lines only — a changed import
#: is a changed dependency edge, which is precisely arch-review's subject.
_IMPORT_RE = re.compile(
    r"""^\s*(?:
        import\b            # JS/TS, Python, Java, Go, Kotlin, Swift
      | from\s+\S+\s+import\b
      | export\s+.*\bfrom\b # JS/TS re-export
      | using\s+[A-Z]       # C# namespace import
      | \#include\b         # C/C++
      | use\s+[\w:\\]+      # Rust, PHP
      | require_relative\b  # Ruby
      | package\s+\w        # Java/Go package declaration
    )""",
    re.VERBOSE,
)

#: CommonJS/dynamic imports are rarely at line start — the idiomatic form is
#: `const db = require('./db')` or `await import('./x')`. Searched anywhere in
#: the line rather than anchored, unlike `_IMPORT_RE`.
_INLINE_IMPORT_RE = re.compile(r"\b(?:require|import)\s*\(\s*['\"]")

#: Public-surface declarations. A new or removed public symbol changes what
#: other layers may couple to, even with no import change.
_INTERFACE_RE = re.compile(
    r"""^\s*(?:
        export\b
      | public\s+(?:class|interface|record|enum|struct|static|abstract|sealed|async|\w+\s+\w+\s*\()
      | protected\s+\w
      | internal\s+\w
      | module\.exports\b
      | __all__\s*=
      | declare\s+(?:module|namespace)\b
      | (?:class|interface|trait|protocol)\s+[A-Z]
    )""",
    re.VERBOSE,
)

_ADR_RE = re.compile(r"(^|/)(docs/)?adr/|(^|/)adr-\d|(^|/)\d{4}-.*\.md$", re.IGNORECASE)


def _normalize(path: str) -> str:
    text = str(path or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def classify_path(path: str) -> set:
    """Signals implied by a path alone, independent of its content."""
    name = _normalize(path)
    if not name:
        return set()
    parts = [p.lower() for p in name.split("/") if p]
    base = parts[-1] if parts else ""
    signals = set()
    if base in _MANIFEST_NAMES or base.endswith(_MANIFEST_SUFFIXES):
        signals.add("manifest")
    if base in _INFRA_NAMES or base.endswith(_INFRA_SUFFIXES):
        signals.add("infra")
    if any(seg in _INFRA_SEGMENTS for seg in parts[:-1]):
        signals.add("infra")
    if _ADR_RE.search(name):
        signals.add("adr")
    return signals


def analyze_diff(diff_text: str) -> dict:
    """Extract architectural-impact signals from a unified diff.

    Returns `{"signals": sorted list, "files": [...], "parsed": bool}`.
    `parsed` is False when the input yielded no recognizable diff structure —
    the caller treats that as "assume impact", never as "no impact".
    """
    signals = set()
    files = []
    saw_structure_marker = False
    parsed = False

    current = None
    for raw in (diff_text or "").splitlines():
        if raw.startswith("diff --git "):
            parsed = True
            current = None
            continue
        if raw.startswith(("new file mode", "deleted file mode", "rename from", "rename to", "copy from")):
            signals.add("structure")
            saw_structure_marker = True
            continue
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target != "/dev/null":
                current = target.removeprefix("b/")
                files.append(current)
                signals |= classify_path(current)
            continue
        if raw.startswith("--- "):
            source = raw[4:].strip()
            if source != "/dev/null":
                name = source.removeprefix("a/")
                signals |= classify_path(name)
            continue
        if raw.startswith("@@"):
            parsed = True
            continue
        if not raw or raw[0] not in "+-":
            continue
        if raw.startswith(("+++", "---")):
            continue
        content = raw[1:]
        if _IMPORT_RE.match(content) or _INLINE_IMPORT_RE.search(content):
            signals.add("dependency")
        if _INTERFACE_RE.match(content):
            signals.add("interface")

    _ = saw_structure_marker
    return {"signals": sorted(signals), "files": sorted(set(files)), "parsed": parsed}


def evaluate(diff_text: str, extra_files=()) -> dict:
    """Decide which gated lenses this diff cannot exercise.

    `extra_files` supplements the diff's own file list — useful when the
    caller already has a `--name-only` list and the diff is truncated.

    Returns `{"signals", "hasArchitecturalImpact", "skipLenses", "reason"}`.
    `skipLenses` is empty whenever the gate cannot prove a lens has nothing
    to look at.
    """
    analysis = analyze_diff(diff_text)
    signals = set(analysis["signals"])
    for path in extra_files or ():
        signals |= classify_path(path)

    if not analysis["parsed"]:
        return {
            "signals": sorted(signals),
            "hasArchitecturalImpact": True,
            "skipLenses": [],
            "reason": "diff-not-parseable-assuming-impact",
        }

    skip = sorted(
        lens for lens, required in GATED_LENSES.items() if not (signals & required)
    )
    return {
        "signals": sorted(signals),
        "hasArchitecturalImpact": bool(signals),
        "skipLenses": skip,
        "reason": None if skip else "architectural-signal-present",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--diff-from",
        default="-",
        help="Path to a unified diff; '-' (default) reads stdin.",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=(),
        help="Optional additional changed paths (e.g. from git diff --name-only).",
    )
    args = parser.parse_args(argv)

    try:
        diff_text = (
            sys.stdin.read()
            if args.diff_from == "-"
            else Path(args.diff_from).read_text(encoding="utf-8")
        )
    except OSError:
        diff_text = ""

    print(json.dumps(evaluate(diff_text, args.files), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
