#!/usr/bin/env python3
"""Resolve a review agent's verification-mode model/effort tier (#1628).

When a fix loop re-dispatches an agent to CONFIRM a fix, the task is far
narrower than discovery — "here is the finding, here is the fix diff:
resolved or not?" — but the dispatch costs the same. An agent may opt in to a
cheaper tier for verification dispatches only, by declaring in its **body**:

    Verify-model: haiku
    Verify-effort: medium

Body declarations, not frontmatter: issue #1333 reserves agent frontmatter
for the official Claude Code sub-agent contract recorded in
`plugins/marketplace-dev/knowledge/agent-contract.json` (a dated snapshot of
upstream docs, not a schema this plugin may extend). `Scope:`, `Cites:`, and
`Enforcement:` follow the same rule. Claude Code silently ignores unknown
frontmatter keys, so a frontmatter typo would also have been invisible; a
body declaration this script parses is checkable.

**Declared, never inferred.** With no opt-in, the returned tier is the
agent's own discovery tier — unchanged. That default is deliberate: #1619
showed some confirmations genuinely need top-tier judgment (the ECMA-402
receiver-binding call), so tiering down is opt-in per agent, never a blanket
rule and never derived from a finding's severity.

Full contract: `knowledge/verification-mode.md`.

Usage:
    python3 verify_tier.py --agent structure-review
    python3 verify_tier.py --all

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# scripts/verify_tier.py -> scripts -> plugin root
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_AGENTS_DIR = _PLUGIN_ROOT / "agents"

_VERIFY_MODEL_RE = re.compile(r"^\s*Verify-model\s*:\s*(\S+)\s*$", re.I)
_VERIFY_EFFORT_RE = re.compile(r"^\s*Verify-effort\s*:\s*(\S+)\s*$", re.I)
_FM_MODEL_RE = re.compile(r"^\s*model\s*:\s*(\S+)\s*$")
_FM_EFFORT_RE = re.compile(r"^\s*effort\s*:\s*(\S+)\s*$")

#: Same closed enums the official contract declares for `model:`/`effort:`
#: (agent-contract.json). A declaration outside these is a typo, not a new
#: tier — reported as an error rather than passed through to a dispatch that
#: would fail at runtime.
VALID_MODELS = frozenset({"sonnet", "opus", "haiku", "fable", "inherit"})
VALID_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


def _split(text: str) -> tuple[str, str]:
    """Return `(frontmatter, body)`. A file without frontmatter is all body."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    after = text.find("\n", end + 1)
    return text[3:end], (text[after + 1 :] if after != -1 else "")


def resolve(text: str, agent: str = "") -> dict:
    """Resolve the verification tier from one agent file's contents.

    Returns `{"agent", "model", "effort", "opted_in", "errors"}`. `model` and
    `effort` are the values to dispatch this agent at in verification mode —
    already falling back to the frontmatter (discovery) values when no opt-in
    is declared, so a caller never needs its own fallback logic.

    An invalid declared value is reported in `errors` and **ignored** for that
    field, which falls back to the discovery tier. Failing closed to the more
    expensive tier is the right direction: a typo must never silently make a
    review cheaper than intended.
    """
    frontmatter, body = _split(text)
    errors = []

    discovery_model = _first(_FM_MODEL_RE, frontmatter) or "inherit"
    discovery_effort = _first(_FM_EFFORT_RE, frontmatter) or "inherit"

    verify_model = _first(_VERIFY_MODEL_RE, body)
    verify_effort = _first(_VERIFY_EFFORT_RE, body)

    if verify_model is not None and verify_model.lower() not in VALID_MODELS:
        errors.append(
            f"Verify-model: {verify_model!r} is not one of {sorted(VALID_MODELS)}"
        )
        verify_model = None
    if verify_effort is not None and verify_effort.lower() not in VALID_EFFORTS:
        errors.append(
            f"Verify-effort: {verify_effort!r} is not one of {sorted(VALID_EFFORTS)}"
        )
        verify_effort = None

    opted_in = verify_model is not None or verify_effort is not None
    return {
        "agent": agent,
        "model": (verify_model or discovery_model).lower(),
        "effort": (verify_effort or discovery_effort).lower(),
        "opted_in": opted_in,
        "errors": errors,
    }


def _first(pattern, text: str):
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            return match.group(1)
    return None


def resolve_agent(name: str, agents_dir: Path | None = None) -> dict:
    path = (agents_dir or _AGENTS_DIR) / f"{name}.md"
    if not path.is_file():
        return {
            "agent": name,
            "model": "inherit",
            "effort": "inherit",
            "opted_in": False,
            "errors": [f"no such agent file: {path}"],
        }
    return resolve(path.read_text(encoding="utf-8"), name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Resolve verification-mode dispatch tiers.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent", help="Agent name (without .md)")
    group.add_argument("--all", action="store_true", help="Every review agent")
    parser.add_argument("--agents-dir", type=Path, default=_AGENTS_DIR)
    args = parser.parse_args(argv)

    if args.agent:
        result = resolve_agent(args.agent, args.agents_dir)
        print(json.dumps(result, sort_keys=True))
        return 1 if result["errors"] else 0

    results = [
        resolve_agent(path.stem, args.agents_dir)
        for path in sorted(args.agents_dir.glob("*-review.md"))
    ]
    print(json.dumps({"agents": results}, sort_keys=True))
    return 1 if any(r["errors"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
