#!/usr/bin/env python3
"""Rank agent ``## Detect`` bullets as lint-rule conversion candidates.

Builds a census of every Detect bullet in ``agents/*.md`` and
``templates/agents/*.md``, scores how mechanical each one reads, and maps it to
an existing ESLint rule through ``knowledge/lint-rule-catalog.json``. No model
is called: the output is a pure function of the files and logs it reads, so it
is byte-identical across runs.

Inputs, read when present (a missing input yields a census-only report):
    <project-root>/.claude/metrics/review-findings.jsonl
        One JSON object per line with ``lens`` and ``category``.
    <project-root>/.dev-team-reports/code-review/raw/*.json
        Findings with ``agent``, ``file``, ``category``, ``message``: one
        object, a list of objects, or an object with a ``findings`` (else
        ``issues``) list.
A line or finding missing its agent or category, or a file that is not valid
JSON, is skipped and counted.

Usage:
    python3 lint_candidates.py [--plugin-root DIR] [--project-root DIR]
                               [--catalog FILE] [--format json|markdown]

Stdlib only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PLUGIN_ROOT / "scripts" / "lib"))
sys.path.insert(0, str(_PLUGIN_ROOT / "skills" / "code-review" / "scripts"))

from detect_bullets import TAG_PATTERN, detect_bullets
from finding_signature import finding_agent, finding_category

DEFAULT_CATALOG = _PLUGIN_ROOT / "knowledge" / "lint-rule-catalog.json"
CENSUS_DIRS = ("agents", "templates/agents")

FINDINGS_LOG = Path(".claude/metrics/review-findings.jsonl")
RAW_DIR = Path(".dev-team-reports/code-review/raw")
# A review agent's own result keys its list `issues`; a section artifact keys it
# `findings`. `findings` wins when both are lists, as in consolidate.py.
RAW_FINDINGS_KEYS = ("findings", "issues")
UNTAGGED = "untagged"


@dataclass(frozen=True)
class Thresholds:
    """The numbers that decide a bullet's score and a group's file count."""

    mechanical_score: float = 1.0  # a [MECHANICAL] tag
    judgment_score: float = 0.0  # a [JUDGMENT] tag
    score_floor: int = 0  # untagged token balance is clamped to
    score_ceiling: int = 1  # [score_floor, score_ceiling]
    unfiled_file_count: int = 1  # files credited to findings that name no file


THRESHOLDS = Thresholds()

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


def mechanical_signal(
    text: str, tags: list[str], thresholds: Thresholds = THRESHOLDS
) -> float:
    """Score in [0, 1] for how mechanical a bullet is.

    One tag decides the score. Zero or several tags fall back to the token
    balance: positive tokens minus negative tokens, clamped.
    """
    if tags == ["MECHANICAL"]:
        return thresholds.mechanical_score
    if tags == ["JUDGMENT"]:
        return thresholds.judgment_score
    balance = len(_POSITIVE.findall(text)) - len(_NEGATIVE.findall(text))
    return float(max(thresholds.score_floor, min(thresholds.score_ceiling, balance)))


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


class Finding(NamedTuple):
    agent: str
    category: str
    file: str | None


@dataclass(frozen=True)
class Findings:
    items: list[Finding]
    skipped: int
    present: bool  # at least one input file exists


def _normalize_file(value: object) -> str | None:
    text = str(value or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text or None


def _log_findings(path: Path) -> tuple[list[Finding], int, bool]:
    if not path.is_file():
        return [], 0, False
    items: list[Finding] = []
    skipped = 0
    # Bytes, decoded per line: one undecodable line must not abort the log.
    for line in path.read_bytes().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line.decode("utf-8"))
        except ValueError:  # JSONDecodeError and UnicodeDecodeError
            skipped += 1
            continue
        row = row if isinstance(row, dict) else {}
        lens, category = row.get("lens"), row.get("category")
        if not lens or not category:
            skipped += 1
            continue
        items.append(Finding(str(lens), str(category), None))
    return items, skipped, True


def _raw_entries(payload: object) -> list[object]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in RAW_FINDINGS_KEYS:
            if isinstance(payload.get(key), list):
                return payload[key]
    return [payload]


def _raw_findings(raw_dir: Path) -> tuple[list[Finding], int, bool]:
    paths = sorted(raw_dir.glob("*.json")) if raw_dir.is_dir() else []
    items: list[Finding] = []
    skipped = 0
    for path in paths:
        try:
            entries = _raw_entries(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            skipped += 1
            continue
        for entry in entries:
            agent = finding_agent(entry) if isinstance(entry, dict) else ""
            category = finding_category(entry) if isinstance(entry, dict) else ""
            if not agent or not category:
                skipped += 1
                continue
            items.append(Finding(agent, category, _normalize_file(entry.get("file"))))
    return items, skipped, bool(paths)


def read_findings(project_root: Path) -> Findings:
    log_items, log_skipped, log_present = _log_findings(project_root / FINDINGS_LOG)
    raw_items, raw_skipped, raw_present = _raw_findings(project_root / RAW_DIR)
    return Findings(
        log_items + raw_items, log_skipped + raw_skipped, log_present or raw_present
    )


def _squash(text: str) -> str:
    """Lowercase and reduce runs of non-alphanumerics to single spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


class Tally:
    """Occurrences and distinct files for one group of findings."""

    def __init__(self) -> None:
        self.occurrences = 0
        self.files: set[str] = set()

    def add(self, finding: Finding) -> None:
        self.occurrences += 1
        if finding.file:
            self.files.add(finding.file)

    def merge(self, other: Tally) -> None:
        self.occurrences += other.occurrences
        self.files |= other.files

    def distinct_files(self, thresholds: Thresholds = THRESHOLDS) -> int:
        if self.files:
            return len(self.files)
        return thresholds.unfiled_file_count if self.occurrences else 0


def group_findings(items: list[Finding]) -> dict[tuple[str, str], Tally]:
    groups: dict[tuple[str, str], Tally] = defaultdict(Tally)
    for finding in items:
        groups[(finding.agent, finding.category)].add(finding)
    return groups


def join_groups(
    ordered: list[Bullet], groups: dict[tuple[str, str], Tally]
) -> tuple[list[Tally], list[dict]]:
    """Tally per bullet (parallel to ``ordered``) plus the groups that matched none.

    A group joins the first bullet of its agent, in census order, whose text
    contains the group's category.
    """
    tallies = [Tally() for _ in ordered]
    unmatched = []
    for (agent, category), tally in sorted(groups.items()):
        keyword = _squash(category)
        index = next(
            (
                i
                for i, b in enumerate(ordered)
                if keyword and b.agent == agent and keyword in _squash(b.text)
            ),
            None,
        )
        if index is None:
            unmatched.append(
                {
                    "agent": agent,
                    "category": category,
                    "distinct_files": tally.distinct_files(),
                    "occurrences": tally.occurrences,
                }
            )
        else:
            tallies[index].merge(tally)
    return tallies, unmatched


def _census_key(b: Bullet) -> tuple:
    return (b.agent, b.text, b.file, b.line)


def _candidate(b: Bullet) -> dict:
    return {
        "agent": b.agent,
        "file": b.file,
        "line": b.line,
        "rule": b.rule,
        "rung": b.rung,
        "score": b.score,
        "tag": b.tag,
        "text": b.text,
    }


def build_report(bullets: list[Bullet], findings: Findings | None = None) -> dict:
    ordered = sorted(bullets, key=_census_key)
    if findings is None or not findings.present:
        return {
            "candidates": [_candidate(b) for b in ordered],
            "frequency_available": False,
            "skipped": findings.skipped if findings else 0,
        }
    tallies, unmatched = join_groups(ordered, group_findings(findings.items))
    ranked = []
    for bullet, tally in zip(ordered, tallies):
        files = tally.distinct_files()
        entry = _candidate(bullet)
        entry.update(
            distinct_files=files,
            occurrences=tally.occurrences,
            rank=files * tally.occurrences * bullet.score,
        )
        ranked.append(entry)
    # Stable sort over census order (agent, bullet text) breaks rank ties.
    ranked.sort(key=lambda c: -c["rank"])
    return {
        "candidates": ranked,
        "frequency_available": True,
        "skipped": findings.skipped,
        "unmatched": unmatched,
    }


def render_json(report: dict) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _cell(value: object) -> str:
    """One markdown table cell: newlines collapsed, pipes escaped."""
    return " ".join(str(value).split()).replace("|", "\\|")


def _row(*cells: object) -> str:
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _markdown_row(position: int, c: dict, frequency: bool) -> str:
    cells = [position, c["agent"], c["tag"], c["score"]]
    if frequency:
        cells += [c["distinct_files"], c["occurrences"], c["rank"]]
    cells += [c["rule"] or "-", c["rung"] or "-", c["text"]]
    return _row(*cells)


def render_markdown(report: dict) -> str:
    frequency = report["frequency_available"]
    headers = ["#", "agent", "tag", "score"]
    if frequency:
        headers += ["files", "occurrences", "rank"]
    headers += ["rule", "rung", "bullet"]
    lines = [
        "# Lint candidates" if frequency else "# Lint candidate census",
        "",
        f"Skipped inputs: {report['skipped']}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines += [
        _markdown_row(i, c, frequency) for i, c in enumerate(report["candidates"], 1)
    ]
    unmatched = report.get("unmatched") or []
    if unmatched:
        lines += [
            "",
            "## Unmatched finding groups",
            "",
            "| agent | category | files | occurrences |",
            "| --- | --- | --- | --- |",
        ]
        lines += [
            _row(u["agent"], u["category"], u["distinct_files"], u["occurrences"])
            for u in unmatched
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plugin-root", type=Path, default=_PLUGIN_ROOT)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)

    # Bullet text carries non-ASCII (arrows); a legacy console encoding such as
    # Windows cp1252 would raise UnicodeEncodeError before any output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    catalog = load_catalog(args.catalog)
    report = build_report(
        read_census(args.plugin_root, catalog), read_findings(args.project_root)
    )
    render = render_json if args.format == "json" else render_markdown
    sys.stdout.write(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
