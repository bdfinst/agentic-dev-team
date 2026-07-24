#!/usr/bin/env python3
"""Agent-readiness scanner — MVP (issue #117).

Scores a SINGLE LOCAL REPOSITORY against the Agent-Readiness Scorecard using
file-presence/heuristic analyzers only (no CI-platform APIs). Emits per-repo
JSON (with `evidence` strings and `manual_review_flags`) and a Markdown tier
summary. Weights and thresholds are externalized to scorecard.yaml.

Placement decision (recorded per the issue): shipped as an in-plugin skill
(`/agent-readiness`) that scores the current working repo locally. The org-scale
Azure DevOps / Jenkins scanner from the plan stays a deferred follow-up.

Usage:
  python3 scanner.py [REPO_PATH] [--config scorecard.yaml]
                     [--json out.json] [--markdown out.md]
Defaults: REPO_PATH=., config=<this dir>/scorecard.yaml, reports to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# skills/agent-readiness -> skills -> dev-team -> hooks/lib (stdlib-only YAML
# subset parser; see ADR 0014/0015 — no third-party imports in shipped code).
sys.path.insert(0, str(HERE.parents[1] / "hooks" / "lib"))
from minimal_yaml import parse_yaml

# --------------------------------------------------------------------------
# Small filesystem helpers (all detection is file-presence/heuristic).
# --------------------------------------------------------------------------


def _exists(root: Path, *names: str) -> str | None:
    for n in names:
        if (root / n).exists():
            return n
    return None


def _glob_any(root: Path, *patterns: str) -> str | None:
    for p in patterns:
        for hit in root.glob(p):
            return str(hit.relative_to(root))
    return None


def _ci_files(root: Path) -> list[Path]:
    out = []
    for pat in (
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        "Jenkinsfile",
        ".gitlab-ci.yml",
        "azure-pipelines.yml",
        ".azure-pipelines.yml",
    ):
        out.extend(root.glob(pat))
    return [p for p in out if p.is_file()]


def _ci_mentions(root: Path, *needles: str) -> bool:
    for f in _ci_files(root):
        try:
            text = f.read_text(errors="ignore").lower()
        except OSError:
            continue
        if any(n in text for n in needles):
            return True
    return False


def _score(n: int, evidence: str) -> dict:
    return {"score": n, "max": 2, "evidence": evidence}


# --------------------------------------------------------------------------
# Analyzers — each returns {score, max, evidence}. MVP: file-presence only.
# --------------------------------------------------------------------------


def b2_reproducible_env(root: Path, cfg: dict) -> dict:
    strong = _exists(
        root,
        ".devcontainer/devcontainer.json",
        "flake.nix",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yaml",
    )
    if strong:
        return _score(2, f"{strong} present (full reproducible environment)")
    if _exists(root, "Dockerfile"):
        return _score(1, "Dockerfile only (no devcontainer/compose/nix)")
    return _score(0, "no Dockerfile/devcontainer/compose/nix")


LOCK_FILES = [
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
    "composer.lock",
    "uv.lock",
    "Gemfile.lock",
]


def b3_dependency_management(root: Path, cfg: dict) -> dict:
    found = [f for f in LOCK_FILES if (root / f).exists()]
    if not found:
        return _score(0, "no lock file found")
    gi = root / ".gitignore"
    ignored = gi.exists() and any(f in gi.read_text(errors="ignore") for f in found)
    if ignored:
        return _score(1, f"lock file(s) {found} present but matched in .gitignore")
    return _score(2, f"lock file(s) committed: {', '.join(found)}")


def c1_formatting(root: Path, cfg: dict) -> dict:
    cfgfile = _glob_any(
        root, ".prettierrc*", ".editorconfig", "rustfmt.toml"
    ) or _pyproject_has(root, "[tool.black]", "[tool.ruff.format]")
    if not cfgfile:
        return _score(0, "no formatter config")
    if _ci_mentions(root, "prettier", "format", "fmt", "ruff format"):
        return _score(2, f"formatter config ({cfgfile}) + CI format step")
    return _score(1, f"formatter config ({cfgfile}) but no CI enforcement found")


def c2_linting(root: Path, cfg: dict) -> dict:
    cfgfile = _glob_any(
        root,
        ".eslintrc*",
        "eslint.config.*",
        "ruff.toml",
        ".pylintrc",
        "pylintrc",
        ".golangci.yml",
        ".golangci.yaml",
    ) or _pyproject_has(root, "[tool.ruff]", "[tool.pylint]")
    if not cfgfile:
        return _score(0, "no linter config")
    if _ci_mentions(root, "lint", "eslint", "ruff check", "golangci"):
        return _score(2, f"linter config ({cfgfile}) + CI lint step")
    return _score(1, f"linter config ({cfgfile}) but no CI enforcement found")


def c4_module_size(root: Path, cfg: dict) -> dict:
    exts = set(cfg.get("source_extensions", []))
    excl = set(cfg.get("exclude_dirs", []))
    counts = []
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix not in exts:
            continue
        if any(part in excl for part in f.relative_to(root).parts):
            continue
        try:
            counts.append(sum(1 for _ in f.open(errors="ignore")))
        except OSError:
            continue
    if not counts:
        return _score(0, "no source files detected for size analysis")
    counts.sort()
    p90 = counts[min(len(counts) - 1, int(round(0.9 * (len(counts) - 1))))]
    th = cfg["thresholds"]
    if p90 <= th["file_size_p90_small"]:
        return _score(
            2, f"p90 source file = {p90} lines (<= {th['file_size_p90_small']})"
        )
    if p90 <= th["file_size_p90_large"]:
        return _score(1, f"p90 source file = {p90} lines")
    return _score(0, f"p90 source file = {p90} lines (> {th['file_size_p90_large']})")


def d1_readme(root: Path, cfg: dict) -> dict:
    readme = _exists(root, "README.md", "README.rst", "README")
    if not readme:
        return _score(0, "no README")
    text = (root / readme).read_text(errors="ignore")
    words = len(text.split())
    low = text.lower()
    has_sections = (
        all(k in low for k in ("setup",))
        and any(k in low for k in ("build", "install"))
        and "test" in low
    )
    min_words = cfg["thresholds"]["readme_min_words"]
    if words >= min_words and has_sections:
        return _score(2, f"README {words} words with setup/build/test sections")
    if words > 0:
        return _score(
            1, f"README present ({words} words) but thin or missing setup/build/test"
        )
    return _score(0, "README empty")


def d2_ai_instructions(root: Path, cfg: dict) -> dict:
    f = _exists(
        root,
        "CLAUDE.md",
        ".claude/CLAUDE.md",
        "AGENTS.md",
        ".cursorrules",
        ".github/copilot-instructions.md",
        "CODING_GUIDELINES.md",
    )
    if not f:
        return _score(
            0, "no AI-instructions file (CLAUDE.md/AGENTS.md/.cursorrules/...)"
        )
    words = len((root / f).read_text(errors="ignore").split())
    if words >= cfg["thresholds"]["ai_instructions_min_words"]:
        return _score(2, f"{f} present ({words} words, detailed)")
    return _score(1, f"{f} present but brief ({words} words)")


def d3_architecture_docs(root: Path, cfg: dict) -> dict:
    f = _glob_any(
        root,
        "docs/adr/*",
        "docs/architecture*",
        "docs/design*",
        "ARCHITECTURE.md",
        "docs/decisions/*",
    )
    if f:
        return _score(2, f"architecture docs present ({f})")
    return _score(0, "no architecture docs (docs/adr, ARCHITECTURE.md, ...)")


def v2_precommit_hooks(root: Path, cfg: dict) -> dict:
    f = _exists(
        root, ".pre-commit-config.yaml", ".husky", "lefthook.yml", "lefthook.yaml"
    ) or _glob_any(root, ".lintstagedrc*")
    if not f:
        return _score(0, "no pre-commit hook config")
    if _ci_mentions(root, "pre-commit") or f == ".pre-commit-config.yaml":
        return _score(2, f"pre-commit hooks configured ({f})")
    return _score(1, f"partial hook config ({f})")


def v3_commit_conventions(root: Path, cfg: dict) -> dict:
    f = _glob_any(root, "commitlint.config.*", ".commitlintrc*")
    if f:
        enforced = _ci_mentions(root, "commitlint") or (root / ".husky").exists()
        return _score(
            2 if enforced else 1,
            f"commit-convention tooling ({f})"
            + ("" if enforced else " but no CI/hook enforcement found"),
        )
    return _score(0, "no commit-convention tooling")


def v4_dependency_scanning(root: Path, cfg: dict) -> dict:
    found = [
        n
        for n in (
            ".github/dependabot.yml",
            ".github/dependabot.yaml",
            ".snyk",
            "renovate.json",
            ".renovaterc",
            ".renovaterc.json",
        )
        if (root / n).exists()
    ]
    if not found:
        return _score(0, "no dependency-scanning config")
    return _score(
        2 if len(found) >= 1 else 1,
        f"dependency scanning configured: {', '.join(found)}",
    )


def _pyproject_has(root: Path, *sections: str) -> str | None:
    p = root / "pyproject.toml"
    if not p.exists():
        return None
    text = p.read_text(errors="ignore")
    if any(s in text for s in sections):
        return "pyproject.toml"
    return None


ANALYZERS = {
    "B2_reproducible_env": b2_reproducible_env,
    "B3_dependency_management": b3_dependency_management,
    "C1_formatting": c1_formatting,
    "C2_linting": c2_linting,
    "C4_module_size": c4_module_size,
    "D1_readme": d1_readme,
    "D2_ai_instructions": d2_ai_instructions,
    "D3_architecture_docs": d3_architecture_docs,
    "V2_precommit_hooks": v2_precommit_hooks,
    "V3_commit_conventions": v3_commit_conventions,
    "V4_dependency_scanning": v4_dependency_scanning,
}


# --------------------------------------------------------------------------
# Scorer.
# --------------------------------------------------------------------------


def scan(root: Path, cfg: dict) -> dict:
    weights = cfg["weights"]
    categories = {}
    manual_flags = []

    for cat, crits in cfg["criteria"].items():
        scored, raw, mx = {}, 0, 0
        for crit, meta in crits.items():
            if meta.get("manual_review"):
                manual_flags.append(
                    {"criterion": crit, "reason": "heuristic weak; needs human review"}
                )
            if not meta.get("mvp"):
                continue
            fn = ANALYZERS.get(crit)
            if fn is None:
                continue
            res = fn(root, cfg)
            scored[crit] = res
            raw += res["score"]
            mx += res["max"]
        if mx == 0:
            categories[cat] = {
                "weight": weights.get(cat, 0),
                "scored": False,
                "reason": "no MVP criteria (deferred — needs CI API)",
                "criteria": {},
            }
        else:
            pct = round(raw / mx * 100, 1)
            categories[cat] = {
                "weight": weights.get(cat, 0),
                "scored": True,
                "score_pct": pct,
                "criteria": scored,
            }

    # Renormalize weights across scored categories only.
    scored_w = sum(c["weight"] for c in categories.values() if c["scored"])
    overall = 0.0
    for c in categories.values():
        if c["scored"] and scored_w:
            c["weighted_score"] = round(c["score_pct"] * (c["weight"] / scored_w), 2)
            overall += c["weighted_score"]
    overall = round(overall, 2)

    t = cfg["tiers"]
    tier = (
        "Agent-Ready"
        if overall >= t["agent_ready"]
        else "Agent-Assisted"
        if overall >= t["agent_assisted"]
        else "Agent-Limited"
        if overall >= t["agent_limited"]
        else "Agent-Hostile"
    )

    return {
        "repository": root.name,
        "scanner_version": cfg.get("version", "unknown"),
        "scope": "mvp-local-file-presence",
        "overall_score": overall,
        "overall_note": "renormalized over scored categories; deferred "
        "categories excluded (need CI-platform APIs)",
        "tier": tier,
        "categories": categories,
        "manual_review_flags": manual_flags,
    }


def to_markdown(result: dict) -> str:
    lines = [f"# Agent-Readiness Report — {result['repository']}", ""]
    lines.append(f"**Overall: {result['overall_score']} / 100 — {result['tier']}**  ")
    lines.append(f"_{result['overall_note']}_")
    lines.append("")
    lines.append("| Category | Scored | % | Weighted |")
    lines.append("| --- | --- | --- | --- |")
    for cat, c in result["categories"].items():
        if c["scored"]:
            lines.append(
                f"| {cat} | yes | {c['score_pct']}% | {c.get('weighted_score', 0)} |"
            )
        else:
            lines.append(f"| {cat} | deferred | — | — |")
    lines.append("")
    lines.append("## Criteria")
    lines.append("| Criterion | Score | Evidence |")
    lines.append("| --- | --- | --- |")
    for cat, c in result["categories"].items():
        for crit, r in c.get("criteria", {}).items():
            lines.append(f"| {crit} | {r['score']}/{r['max']} | {r['evidence']} |")
    if result["manual_review_flags"]:
        lines.append("")
        lines.append("## Manual review flags")
        for f in result["manual_review_flags"]:
            lines.append(f"- **{f['criterion']}**: {f['reason']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--config", default=str(HERE / "scorecard.yaml"))
    ap.add_argument("--json", help="write JSON result to this path")
    ap.add_argument("--markdown", help="write Markdown summary to this path")
    args = ap.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    cfg = parse_yaml(Path(args.config).read_text())

    result = scan(root, cfg)
    md = to_markdown(result)

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n")
    if args.markdown:
        Path(args.markdown).write_text(md)
    if not args.json and not args.markdown:
        print(json.dumps(result, indent=2))
        print("\n" + md)
    else:
        print(f"{result['tier']} — {result['overall_score']}/100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
