#!/usr/bin/env python3
# build_knowledge_index.py — single-process knowledge index builder.
#
# Replaces the shell+jq+awk+python-per-section pipeline. Forks once
# instead of ~300 times per build. Output is byte-identical to what
# the previous `jq -s 'add'` pipeline produced, so the freshness gate
# does not trip across the rewrite.
#
# Modes:
#   default    rebuild the index file in place
#   --check    diff a fresh build against the on-disk index; exit non-
#              zero with a unified diff on stderr if they differ
#
# Env vars (TEST-ONLY injection seams — do not document as user-facing):
#   KNOWLEDGE_INDEX_CORPUS_ROOTS  override the corpus root
#   KNOWLEDGE_INDEX_OUTPUT        override the output path

import difflib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — path resolution mirrors the shell wrapper's defaults.
# ---------------------------------------------------------------------------

ABBREVS = {
    "e.g",
    "i.e",
    "etc",
    "vs",
    "Mr",
    "Mrs",
    "Ms",
    "Dr",
    "Jr",
    "Sr",
    "St",
    "No",
    "cf",
}
MAX_SUMMARY_LEN = 240
ELLIPSIS = "…"


def _resolve_paths():
    script_dir = Path(__file__).resolve().parent
    plugin_dir = script_dir.parent.parent
    roots = os.environ.get("KNOWLEDGE_INDEX_CORPUS_ROOTS", str(plugin_dir))
    output = os.environ.get(
        "KNOWLEDGE_INDEX_OUTPUT", str(plugin_dir / "knowledge" / "index.json")
    )
    return Path(roots), Path(output)


# ---------------------------------------------------------------------------
# Slugify — matches the shell `_slugify` exactly:
#   lowercase | strip non [a-z0-9 -] | spaces→hyphens | collapse hyphens | trim
# ---------------------------------------------------------------------------

_SLUG_DROP_RE = re.compile(r"[^a-z0-9 \-]+")
_SLUG_SPACE_RE = re.compile(r" +")
_SLUG_DASH_RE = re.compile(r"-+")


def slugify(text: str) -> str:
    s = text.lower()
    s = _SLUG_DROP_RE.sub("", s)
    s = _SLUG_SPACE_RE.sub("-", s)
    s = _SLUG_DASH_RE.sub("-", s)
    return s.strip("-")


# ---------------------------------------------------------------------------
# First-sentence extraction — operational boundary rule from the spec.
# Logic mirrors the previous heredoc Python exactly so AC7a stays green.
# ---------------------------------------------------------------------------


def first_sentence(text: str) -> str:
    text = text.lstrip()
    i = 0
    end = None
    while i < len(text):
        ch = text[i]
        if ch in ".!?":
            after = text[i + 1] if i + 1 < len(text) else ""
            if not (after == "" or after.isspace()):
                i += 1
                continue
            if i >= 1 and text[i - 1].isupper():
                prev2 = text[i - 2] if i - 2 >= 0 else ""
                if prev2 == "" or prev2.isspace() or prev2 == ".":
                    i += 1
                    continue
            j = i - 1
            while j >= 0 and not text[j].isspace():
                j -= 1
            token = text[j + 1 : i]
            if token in ABBREVS:
                i += 1
                continue
            end = i + 1
            break
        i += 1

    if end is not None:
        return text[:end]
    if len(text) <= MAX_SUMMARY_LEN:
        return text
    cut = text[:MAX_SUMMARY_LEN].rstrip()
    last_ws = cut.rfind(" ")
    if last_ws > 0:
        cut = cut[:last_ws]
    return cut + ELLIPSIS


# ---------------------------------------------------------------------------
# Section extraction — replicates the awk first pass + the backfill pass.
#
# Rules (must match shell):
#   - Code fences (```...```) are skipped wholesale; only prose outside
#     fenced blocks is considered.
#   - `## ` is an H2; `### ` is an H3; both are indexed.
#   - `# ` (H1) resets collection; `#### ` (H4+) closes the enclosing body
#     but emits nothing for the H4.
#   - Body is the first non-blank line under the header. A leading bullet
#     marker (`- `, `* `, `+ `) is stripped.
#   - Empty bodies are backfilled from the next non-empty body in source
#     order (cascades through child sections).
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```")
_H4_PLUS_RE = re.compile(r"^#{4,} ")
_H3_RE = re.compile(r"^### (.+)$")
_H2_RE = re.compile(r"^## (.+)$")
_H1_RE = re.compile(r"^# ")
_BULLET_RE = re.compile(r"^[ \t]*[-*+][ \t]+")


def extract_sections(path: Path) -> list:
    """Returns [(header, body), ...] in source order, with backfill applied."""
    rows = []  # each (header, body) — body may start empty
    header = None
    body = ""
    collecting = False
    in_code = False

    def flush():
        nonlocal header, body
        if header is not None:
            rows.append((header, body))
            header = None
            body = ""

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")
            if _FENCE_RE.match(line):
                in_code = not in_code
                continue
            if in_code:
                continue
            if _H4_PLUS_RE.match(line):
                flush()
                collecting = False
                continue
            m3 = _H3_RE.match(line)
            if m3:
                flush()
                header = m3.group(1)
                collecting = True
                body = ""
                continue
            m2 = _H2_RE.match(line)
            if m2:
                flush()
                header = m2.group(1)
                collecting = True
                body = ""
                continue
            if _H1_RE.match(line):
                flush()
                collecting = False
                continue
            if collecting and not body and line.strip():
                stripped = _BULLET_RE.sub("", line, count=1)
                body = stripped
    flush()

    # Backfill empty bodies from the next non-empty body in source order.
    for i in range(len(rows)):
        if not rows[i][1].strip():
            for j in range(i + 1, len(rows)):
                if rows[j][1].strip():
                    rows[i] = (rows[i][0], rows[j][1])
                    break

    return rows


# ---------------------------------------------------------------------------
# Per-file section objects with slug + header disambiguation.
# ---------------------------------------------------------------------------


def file_entry(rows: list) -> "dict":
    """Build the {header: {summary, anchor}} mapping for one file.

    Preserves source order, applies GitHub-style slug disambiguation
    (`overview` / `overview-1` / `overview-2`) and parallel header-key
    disambiguation (`Overview (2)`, `Overview (3)`) so JSON keys remain
    unique even when the source has duplicate H2/H3 headers.
    """
    out = {}
    slug_seen = {}  # base_slug → count seen so far
    header_seen = {}  # raw header → count seen so far
    for header, body in rows:
        if not header:
            continue
        base = slugify(header)
        n = slug_seen.get(base, 0)
        anchor = base if n == 0 else f"{base}-{n}"
        slug_seen[base] = n + 1

        hc = header_seen.get(header, 0)
        key = header if hc == 0 else f"{header} ({hc + 1})"
        header_seen[header] = hc + 1

        out[key] = {"summary": first_sentence(body), "anchor": anchor}
    return out


# ---------------------------------------------------------------------------
# Corpus discovery — must match the shell's LC_ALL=C sorted order.
# ---------------------------------------------------------------------------


def discover_files(roots: Path) -> list:
    paths = []
    knowledge = roots / "knowledge"
    if knowledge.is_dir():
        paths.extend(
            p for p in knowledge.iterdir() if p.is_file() and p.suffix == ".md"
        )
    skills = roots / "skills"
    if skills.is_dir():
        for child in skills.iterdir():
            if not child.is_dir():
                continue
            skill = child / "SKILL.md"
            if skill.is_file():
                paths.append(skill)
    # Sort with C locale semantics: codepoint order on absolute path.
    paths.sort(key=lambda p: str(p))
    return paths


# ---------------------------------------------------------------------------
# Output — byte-identical to `jq -s 'add'` of per-file objects:
# 2-space indent, ": " separator, no trailing newline.
# ---------------------------------------------------------------------------


def build_index_text(roots: Path) -> str:
    index = {}
    for path in discover_files(roots):
        rel = path.relative_to(roots)
        # The roots env var may point at the plugin dir; reattach the
        # plugin prefix so keys are repo-relative.
        rel_key = f"plugins/dev-team/{rel.as_posix()}"
        rows = extract_sections(path)
        if not rows:
            continue
        index[rel_key] = file_entry(rows)
    # jq's `add` output ends with a trailing newline; preserve that so
    # the freshness gate stays byte-identical across the rewrite.
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Atomic publish — never truncate the live index in place.
#
# The index is read by other tooling (and, under parallel test runs, by
# concurrent readers). A plain truncate-then-stream write exposes a window in
# which a reader observes an empty or partial file. Writing to a sibling temp
# file in the same directory and renaming it over the destination makes the
# publish atomic: every reader sees either the whole old file or the whole new
# file, never a half-written one. os.replace is an atomic rename on POSIX.
# ---------------------------------------------------------------------------


def _atomic_write(output: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(
        dir=str(output.parent), prefix=f".{output.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, output)
    except BaseException:
        # Don't leave a partial temp file behind if the write/rename failed.
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Entry points — write mode and --check.
# ---------------------------------------------------------------------------


def main(argv: list) -> int:
    roots, output = _resolve_paths()
    mode = argv[1] if len(argv) > 1 else "write"

    actual = build_index_text(roots)

    if mode == "--check":
        if not output.exists():
            sys.stderr.write(f"[knowledge-index] index file missing: {output}\n")
            return 1
        expected = output.read_text(encoding="utf-8")
        if actual == expected:
            return 0
        diff = difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=str(output),
            tofile="<fresh build>",
        )
        sys.stderr.writelines(diff)
        return 1

    if mode in ("write", ""):
        output.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(output, actual)
        return 0

    sys.stderr.write(f"Unknown mode: {mode}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
