"""AI-friendly repository analyzers for the agent-readiness scanner (issue #2178).

Sibling of scanner.py: one pure function per new `mvp: true` criterion, each
`(root, cfg) -> {score, max, evidence}`. Rubric and evidence anchors live in
`knowledge/ai-friendly-repo-guidelines.md`. Stdlib-only. Thresholds come from
scorecard.yaml (read with `.get()` defaults); nothing here hardcodes scoring
policy beyond a safe fallback when a key is absent.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

GUIDE = "knowledge/ai-friendly-repo-guidelines.md"

# --------------------------------------------------------------------------
# Shared, pruned, memoized directory walk (one traversal per scan).
# --------------------------------------------------------------------------

_WALK_CACHE: dict[tuple[str, tuple[str, ...]], list[tuple[Path, list[str]]]] = {}


def reset_walk_cache() -> None:
    """Drop memoized walks; scan() calls this so repeated scans see fresh state."""
    _WALK_CACHE.clear()


def walk_tree(root: Path, exclude_dirs) -> list[tuple[Path, list[str]]]:
    """Return [(dirpath, filenames)] under root, pruning excluded dirs.

    Never follows directory symlinks (so symlink loops terminate). Sorted for
    deterministic output. Memoized per (root, exclude set) until reset.
    """
    excl = tuple(sorted(set(exclude_dirs or ())))
    key = (str(root), excl)
    hit = _WALK_CACHE.get(key)
    if hit is not None:
        return hit
    excl_set = set(excl)
    out: list[tuple[Path, list[str]]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel == "." else rel + "/"
        # An entry prunes by bare dir name (".git") or root-relative path
        # (".claude/worktrees").
        dirnames[:] = sorted(
            d for d in dirnames if d not in excl_set and prefix + d not in excl_set
        )
        out.append((Path(dirpath), sorted(filenames)))
    _WALK_CACHE[key] = out
    return out


def walk_files(root: Path, exclude_dirs):
    """Yield every file Path under root, honoring the pruned walk."""
    for dirpath, filenames in walk_tree(root, exclude_dirs):
        for name in filenames:
            yield dirpath / name


def _score(n: int, evidence: str) -> dict:
    return {"score": n, "max": 2, "evidence": evidence}


def _na(evidence: str) -> dict:
    """Not applicable: contributes nothing to the category score."""
    return {"score": 0, "max": 0, "evidence": evidence}


def _evidence(found: str, threshold: str, fix: str, anchor: str) -> str:
    return f"found {found}; threshold {threshold}; to fix: {fix} (see {GUIDE}#{anchor})"


def _thresholds(cfg: dict) -> dict:
    th = cfg.get("thresholds")
    return th if isinstance(th, dict) else {}


# Single source for "AI instructions file" discovery; D2 (scanner.py) and D5
# both use it so they can never disagree about which file counts.
INSTRUCTION_FILES = (
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    "AGENTS.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
    "CODING_GUIDELINES.md",
)

DEFAULT_CLAUDE_MD_MAX_LINES = 200
DEFAULT_CLAUDE_MD_HARD_MAX_LINES = 300


def find_instructions_file(root: Path) -> str | None:
    for name in INSTRUCTION_FILES:
        if (root / name).exists():
            return name
    return None


def d5_claude_md_size(root: Path, cfg: dict) -> dict:
    anchor = "layered-context-architecture"
    name = find_instructions_file(root)
    if name is None:
        return _na("no AI-instructions file; not applicable here (see D2)")
    th = _thresholds(cfg)
    soft = th.get("claude_md_max_lines", DEFAULT_CLAUDE_MD_MAX_LINES)
    hard = th.get("claude_md_hard_max_lines", DEFAULT_CLAUDE_MD_HARD_MAX_LINES)
    try:
        with (root / name).open(errors="ignore") as fh:
            n = sum(1 for _ in fh)
    except OSError:
        return _na(f"{name} unreadable; not applicable here (see D2)")
    fix = "move detail into nested CLAUDE.md, .claude/rules/ or on-demand skills"
    if n <= soft:
        return _score(2, _evidence(f"{name} is {n} lines", f"<= {soft} lines", "none needed", anchor))
    if n <= hard:
        return _score(
            1,
            _evidence(
                f"{name} is {n} lines, exceeds {soft}-line ceiling",
                f"<= {soft} lines (hard limit {hard})",
                fix,
                anchor,
            ),
        )
    return _score(
        0,
        _evidence(
            f"{name} is {n} lines, exceeds {soft}-line ceiling and {hard}-line hard limit",
            f"<= {soft} lines (hard limit {hard})",
            fix,
            anchor,
        ),
    )


def _has_content(path: Path) -> bool:
    """True when the file has at least one non-blank, non-heading line."""
    try:
        with path.open(errors="ignore") as fh:
            return any(
                line.strip() and not line.lstrip().startswith("#") for line in fh
            )
    except OSError:
        return False


def d6_layered_context(root: Path, cfg: dict) -> dict:
    anchor = "layered-context-architecture"
    excl = cfg.get("exclude_dirs", [])
    found: list[str] = []
    for path in walk_files(root, excl):
        rel = path.relative_to(root).as_posix()
        nested_md = path.name == "CLAUDE.md" and "/" in rel and rel != ".claude/CLAUDE.md"
        rules_md = rel.startswith(".claude/rules/") and path.suffix == ".md"
        if (nested_md or rules_md) and _has_content(path):
            found.append(rel)
    threshold = "at least 1 non-empty nested CLAUDE.md or .claude/rules/*.md"
    if found:
        shown = ", ".join(found[:3]) + (f" (+{len(found) - 3} more)" if len(found) > 3 else "")
        return _score(2, _evidence(shown, threshold, "none needed", anchor))
    return _score(
        0,
        _evidence(
            "no non-empty nested CLAUDE.md or .claude/rules/*.md",
            threshold,
            "add directory-scoped CLAUDE.md or .claude/rules/*.md files",
            anchor,
        ),
    )


# --------------------------------------------------------------------------
# B5: composite check command present.
# --------------------------------------------------------------------------

DEFAULT_CHECK_TARGETS = ("check", "verify", "ci", "all")
_LINT_RE = re.compile(
    r"(?<![A-Za-z])(?:lint|ruff|eslint|flake8|pylint|golangci|shellcheck|mypy|tsc|clippy)(?![A-Za-z])"
)
_TEST_RE = re.compile(
    r"(?<![A-Za-z])(?:test|pytest|unittest|ctest|gotestsum|tox|nox|jest|vitest|mocha|rspec|phpunit)"
    r"(?![A-Za-z])"
)
# Only task-runner tables count; dependency lists (`all = [...]`) do not.
_TASK_TABLE_RE = re.compile(r"^tool\..*(?:tasks|scripts)$")
_MAKE_FILES = ("Makefile", "makefile", "GNUmakefile", "justfile", "Justfile")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return None


def _recipe_bodies(text: str, names: set[str]) -> list[tuple[str, str]]:
    """Targets/recipes named in `names` with prerequisites + indented body."""
    out: list[tuple[str, str]] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Za-z0-9_.-]+)[^:=\n]*:(?!=)(.*)$", line)
        if not m or m.group(1) not in names:
            continue
        body = [m.group(2)]
        for nxt in lines[i + 1 :]:
            if nxt.strip() and nxt[0] not in " \t":
                break
            body.append(nxt)
        out.append((m.group(1), "\n".join(body)))
    return out


def _package_json_bodies(text: str, names: set[str]) -> list[tuple[str, str]]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return []
    return [
        (k, v) for k, v in scripts.items() if k in names and isinstance(v, str)
    ]


def _pyproject_bodies(text: str, names: set[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    lines = text.splitlines()
    section = ""
    for i, line in enumerate(lines):
        hdr = re.match(r"^\s*\[+([^\]]+)\]+", line)
        if hdr:
            section = hdr.group(1).strip()
            continue
        if not _TASK_TABLE_RE.match(section):
            continue
        m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)$", line)
        if not m or m.group(1) not in names:
            continue
        body = [m.group(2)]
        for nxt in lines[i + 1 : i + 16]:
            if re.match(r"^\s*[\w.\"-]+\s*=", nxt) or nxt.startswith("["):
                break
            body.append(nxt)
        out.append((m.group(1), "\n".join(body)))
    return out


def b5_composite_check_command(root: Path, cfg: dict) -> dict:
    anchor = "deterministic-verification--fast-feedback-loops"
    names = set(cfg.get("check_target_names") or DEFAULT_CHECK_TARGETS)
    ordered = [n for n in DEFAULT_CHECK_TARGETS if n in names]
    shown = "|".join(ordered + sorted(names - set(ordered)))
    threshold = f"a {shown} target whose body has a lint and a test command"
    sources: list[tuple[str, list[tuple[str, str]]]] = []
    for mf in _MAKE_FILES:
        text = _read(root / mf)
        if text is not None:
            sources.append((mf, _recipe_bodies(text, names)))
    text = _read(root / "package.json")
    if text is not None:
        sources.append(("package.json", _package_json_bodies(text, names)))
    text = _read(root / "pyproject.toml")
    if text is not None:
        sources.append(("pyproject.toml", _pyproject_bodies(text, names)))
    partial = None
    for fname, bodies in sources:
        for name, body in bodies:
            lint, test = bool(_LINT_RE.search(body)), bool(_TEST_RE.search(body))
            if lint and test:
                return _score(
                    2,
                    _evidence(
                        f"{fname} target '{name}' runs lint and test",
                        threshold,
                        "none needed",
                        anchor,
                    ),
                )
            if partial is None:
                missing = "test" if lint else "lint" if test else "lint and test"
                partial = (fname, name, missing)
    if partial:
        fname, name, missing = partial
        return _score(
            1,
            _evidence(
                f"{fname} target '{name}' lacks a {missing} command",
                threshold,
                f"make '{name}' run both lint and tests",
                anchor,
            ),
        )
    return _score(
        0,
        _evidence(
            f"no {shown} target in Makefile, justfile, package.json or pyproject.toml",
            threshold,
            "add one command that runs lint and tests together",
            anchor,
        ),
    )


# Merged into scanner.ANALYZERS.
AI_FRIENDLY_ANALYZERS: dict = {
    "D5_claude_md_size": d5_claude_md_size,
    "D6_layered_context": d6_layered_context,
    "B5_composite_check_command": b5_composite_check_command,
}
