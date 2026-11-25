#!/usr/bin/env python3
"""Rank agent ``## Detect`` bullets as lint-rule conversion candidates.

Builds a census of every Detect bullet in ``agents/*.md`` and
``templates/agents/*.md``, scores how mechanical each one reads, and maps it to
an existing ESLint rule through ``knowledge/lint-rule-catalog.json``. No model
is called: the output is a pure function of the files and logs it reads, so it
is byte-identical across runs.

Usage:
    python3 lint_candidates.py [--plugin-root DIR] [--catalog FILE]
                               [--format json|markdown]

Stdlib only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from detect_bullets import TAG_PATTERN, detect_bullets

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = _PLUGIN_ROOT / "knowledge" / "lint-rule-catalog.json"
CENSUS_DIRS = ("agents", "templates/agents")

TAG_SCORES = {"MECHANICAL": 1.0, "JUDGMENT": 0.0}
UNTAGGED = "untagged"

# Signals that a bullet states a checkable fact: backticked code, a numeric
# threshold, "never", or glob/regex text.
_POSITIVE = re.compile(
    r"`[^`]+`"
    r"|\b\d+\b"
    r"|\bnever\b"
    r"|\*\*?/[\w*./-]*|\*\.\w+|\\[dwsDWS]\+?|\[\^?\w-\w\][+*?]?|\.\*",
    re.IGNORECASE,
)
# Signals that a bullet asks for judgment.
_NEGATIVE = re.compile(
    r"\b(?:appropriate|meaningful|clear|too many|consider|opportunity)\b",
    re.IGNORECASE,
)


class CatalogEntry(NamedTuple):
    pattern: str
    rule: str
    rung: str


@dataclass(frozen=True)
class Bullet:
    agent: str
    file: str
    line: int
    tag: str
    text: str
    score: float
    rule: str | None
    rung: str | None


def mechanical_signal(text: str, tags: list[str]) -> float:
    """Score in [0, 1] for how mechanical a bullet is.

    One tag decides the score. Zero or several tags fall back to the token
    balance: positive tokens minus negative tokens, clamped.
    """
    if len(tags) == 1:
        return TAG_SCORES[tags[0]]
    balance = len(_POSITIVE.findall(text)) - len(_NEGATIVE.findall(text))
    return float(max(0, min(1, balance)))


def load_catalog(path: Path) -> list[CatalogEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CatalogEntry(e["pattern"], e["rule"], e["rung"]) for e in data["entries"]]


def lookup_catalog(text: str, entries: list[CatalogEntry]) -> CatalogEntry | None:
    """Return the first entry whose pattern matches ``text``, or ``None``."""
    for entry in entries:
        if re.search(entry.pattern, text, re.IGNORECASE):
            return entry
    return None


def _clean(text: str) -> str:
    """Drop tags and the list marker; collapse whitespace to single spaces."""
    without_tags = TAG_PATTERN.sub("", text)
    return " ".join(without_tags.split()).removeprefix("- ")


def parse_bullets(
    agent: str, rel_file: str, markdown: str, catalog: list[CatalogEntry]
) -> list[Bullet]:
    """Census one agent file's Detect bullets (pure; no IO)."""
    bullets = []
    for raw in detect_bullets(markdown):
        text = _clean(raw.text)
        hit = lookup_catalog(text, catalog)
        bullets.append(
            Bullet(
                agent=agent,
                file=rel_file,
                line=raw.line,
                tag=raw.tags[0] if len(raw.tags) == 1 else UNTAGGED,
                text=text,
                score=mechanical_signal(text, raw.tags),
                rule=hit.rule if hit else None,
                rung=hit.rung if hit else None,
            )
        )
    return bullets


def read_census(plugin_root: Path, catalog: list[CatalogEntry]) -> list[Bullet]:
    bullets: list[Bullet] = []
    for sub in CENSUS_DIRS:
        for path in sorted((plugin_root / sub).glob("*.md")):
            rel = path.relative_to(plugin_root).as_posix()
            bullets.extend(
                parse_bullets(path.stem, rel, path.read_text(encoding="utf-8"), catalog)
            )
    return bullets


def _census_key(b: Bullet) -> tuple:
    return (b.agent, b.text, b.file, b.line)


def build_report(bullets: list[Bullet]) -> dict:
    ordered = sorted(bullets, key=_census_key)
    return {
        "frequency_available": False,
        "candidates": [
            {
                "agent": b.agent,
                "file": b.file,
                "line": b.line,
                "rule": b.rule,
                "rung": b.rung,
                "score": b.score,
                "tag": b.tag,
                "text": b.text,
            }
            for b in ordered
        ],
    }


def render_json(report: dict) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def render_markdown(report: dict) -> str:
    lines = [
        "# Lint candidate census",
        "",
        "| agent | tag | score | rule | rung | bullet |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in report["candidates"]:
        text = c["text"].replace("|", "\\|")
        lines.append(
            f"| {c['agent']} | {c['tag']} | {c['score']} "
            f"| {c['rule'] or '-'} | {c['rung'] or '-'} | {text} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plugin-root", type=Path, default=_PLUGIN_ROOT)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)

    catalog = load_catalog(args.catalog)
    report = build_report(read_census(args.plugin_root, catalog))
    render = render_json if args.format == "json" else render_markdown
    sys.stdout.write(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
