#!/usr/bin/env python3
"""Skill citation lint — preventive drift defense (issue #312).

Reviewer agents can inline normative rules (must/should statements, numeric
thresholds) independently of the canonical skill/knowledge files. When the
canonical file changes, the agent silently keeps enforcing the stale rule. That
drift is invisible until a reviewer and a builder disagree.

This lint makes the dependency explicit and checkable. An agent declares the
canonical sources it derives its rules from in a ``cites:`` frontmatter list::

    ---
    name: complexity-review
    cites: [complexity, object-calisthenics]   # skill names or knowledge files
    ---

For every **normative token** the agent states — a numeric threshold (e.g.
``50``, ``80%``) appearing on a line that carries an RFC-2119 keyword
(MUST/SHOULD/SHALL/REQUIRED/NEVER/ALWAYS) — the lint checks that the token also
appears in at least one cited file. A token present in the agent but absent from
every cited file is flagged with its line number: that is the drift. Thresholds
are the highest-drift-risk, lowest-noise normative element, so the parser keys
on them rather than free-text rule prose.

Phase 1 is **non-blocking** (warnings only, exit 0):

- ``cites:`` present and every normative token backed  -> no warning.
- ``cites:`` present, a token uncited                  -> warning (token + line).
- no ``cites:`` and no normative tokens                -> no warning.
- no ``cites:`` but normative tokens present           -> one advisory warning.

Code fences (``` / ~~~ blocks) and blockquote lines (``>``) are excluded so
illustrative examples are never mistaken for normative rules.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NORMATIVE_RE = re.compile(
    r"\b(MUST NOT|MUST|SHOULD NOT|SHOULD|SHALL|REQUIRED|NEVER|ALWAYS)\b",
    re.IGNORECASE,
)
# A numeric threshold: integer/decimal with optional trailing %. Exclude issue
# refs (#99); version-ish dotted tails are kept whole (40.5). Not preceded by
# '#', '-', or a word char/dot so we don't slice mid-identifier or mid-number.
THRESHOLD_RE = re.compile(r"(?<![\w.#-])\d+(?:\.\d+)?%?")


def parse_frontmatter_cites(text: str) -> list[str] | None:
    """Return the ``cites:`` list, or None when the field is absent.

    Accepts an inline flow list (``cites: [a, b]``) or a block list (``cites:``
    followed by ``  - a`` lines). Avoids a YAML dependency (the repo's bats
    suites already shell to Python without PyYAML guaranteed here).
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = text[3:end]
    lines = fm.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"\s*cites\s*:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1]
            return [t.strip().strip("'\"") for t in inner.split(",") if t.strip()]
        if rest and not rest.startswith("#"):
            # cites: foo  (single scalar)
            return [rest.strip().strip("'\"")]
        # Block list: collect following indented "- item" lines.
        items = []
        for nxt in lines[i + 1:]:
            bm = re.match(r"\s*-\s*(.+)$", nxt)
            if bm:
                items.append(bm.group(1).strip().strip("'\""))
            elif nxt.strip() == "":
                continue
            else:
                break
        return items
    return None


def strip_frontmatter(text: str) -> tuple[str, int]:
    """Return (body, body_start_line) so reported line numbers map to the file."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            after = text.find("\n", end + 1)
            if after != -1:
                before = text[: after + 1]
                return text[after + 1:], before.count("\n") + 1
    return text, 1


def normative_tokens(text: str) -> list[tuple[int, str]]:
    """Extract (line_number, token) for normative tokens in an agent body.

    A token is a numeric threshold on a line that contains an RFC-2119 keyword.
    Fenced code blocks and blockquotes are skipped. Line numbers are 1-based
    within ``text``.
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    fence_marker = ""
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        # Toggle fenced code blocks (``` or ~~~).
        fm = re.match(r"(```+|~~~+)", stripped)
        if fm:
            if not in_fence:
                in_fence, fence_marker = True, fm.group(1)[0]
            elif stripped[0] == fence_marker:
                in_fence = False
            continue
        if in_fence:
            continue
        if stripped.startswith(">"):  # blockquote
            continue
        if not NORMATIVE_RE.search(line):
            continue
        seen_on_line: set[str] = set()
        for tm in THRESHOLD_RE.finditer(line):
            tok = tm.group(0)
            if tok not in seen_on_line:
                seen_on_line.add(tok)
                out.append((idx, tok))
    return out


def resolve_cite(name: str, plugin_root: Path) -> Path | None:
    """Resolve a cites entry to a skill SKILL.md, a knowledge file, or a path."""
    name = name.strip()
    skill = plugin_root / "skills" / name / "SKILL.md"
    if skill.exists():
        return skill
    knowledge = plugin_root / "knowledge" / f"{name}.md"
    if knowledge.exists():
        return knowledge
    direct = (plugin_root / name)
    if direct.exists():
        return direct
    literal = Path(name)
    if literal.exists():
        return literal
    return None


def lint_agent(path: Path, plugin_root: Path) -> list[str]:
    """Return a list of warning strings for one agent file (empty == clean)."""
    text = path.read_text()
    cites = parse_frontmatter_cites(text)
    body, base = strip_frontmatter(text)
    tokens = normative_tokens(body)
    warnings: list[str] = []
    name = path.stem

    if cites is None:
        if tokens:
            warnings.append(
                f"{name}: advisory — states {len(tokens)} normative token(s) "
                f"(e.g. {tokens[0][1]!r} at line {tokens[0][0] + base - 1}) but "
                f"declares no `cites:`; add a cites: list so the rules are "
                f"checked against their canonical source."
            )
        return warnings

    # Concatenate every resolved cited source for substring checks.
    cited_text_parts: list[str] = []
    missing_sources: list[str] = []
    for c in cites:
        resolved = resolve_cite(c, plugin_root)
        if resolved is None:
            missing_sources.append(c)
        else:
            cited_text_parts.append(resolved.read_text())
    cited_text = "\n".join(cited_text_parts)

    for src in missing_sources:
        warnings.append(
            f"{name}: cites unknown source {src!r} (no matching skill/knowledge "
            f"file) — citation cannot be verified."
        )

    for lineno, tok in tokens:
        if tok not in cited_text:
            warnings.append(
                f"{name}:{lineno + base - 1}: normative token {tok!r} is not "
                f"present in any cited source ({', '.join(cites)}) — possible "
                f"drift from the canonical rule."
            )
    return warnings


def discover_agents(plugin_root: Path) -> list[Path]:
    agents_dir = plugin_root / "agents"
    return sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files", nargs="*", help="agent .md files to lint")
    ap.add_argument("--all", action="store_true",
                    help="lint every agent under <plugin-root>/agents/")
    ap.add_argument("--plugin-root", default="plugins/dev-team",
                    help="plugin root holding agents/, skills/, knowledge/")
    args = ap.parse_args(argv)

    plugin_root = Path(args.plugin_root)
    if args.all or not args.files:
        targets = discover_agents(plugin_root)
    else:
        targets = [Path(f) for f in args.files]

    all_warnings: list[str] = []
    for t in targets:
        if not t.exists():
            print(f"  ⚠ {t}: file not found", file=sys.stderr)
            continue
        all_warnings.extend(lint_agent(t, plugin_root))

    if all_warnings:
        print(f"Citation lint — {len(all_warnings)} warning(s) "
              f"(Phase 1: advisory, non-blocking):")
        for w in all_warnings:
            print(f"  ⚠ {w}")
    else:
        print(f"Citation lint OK: {len(targets)} agent(s), no drift warnings.")
    # Phase 1 is intentionally non-blocking — collect signal before hardening.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
