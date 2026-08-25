#!/usr/bin/env python3
"""One shared context pack for a review panel (#2006).

Every lens in a `/code-review` panel is handed the same changed files and then
reads them itself. Measured across 148 panels of >= 8 agents: **180 MB of Read
volume covering 41.8 MB of unique content — a 4.31x re-read multiplier**, with
one file opened by 38 agents in the worst case. Those panels are 73% of all
review spend.

The multiplier is not only cross-agent duplication. A lens that opens a file,
greps around it, and opens it again pays for it each time, and the panel pays
that per lens. What removes it is giving every lens the same prepared bytes
once, so reading is a single addressed fetch instead of an exploration.

## Why one pack serves nearly the whole panel

Of the 18 review lenses that declare a `Context needs` value, **17 need the
full bodies of the changed files** (13 `full-file`, 4 `project-structure`);
one needs the diff alone. So the union of what the panel needs is: the changed
file list, the diff, and the full bodies — which is exactly this pack. Each
lens reads the section its declaration calls for.

## What this deliberately does NOT do

It does not stop a lens from reading anything else. A lens tracing a caller
into an unchanged file still should, and still can. The pack removes the
*repeated* read of the *same* changed files, which is the measured cost; it is
not a sandbox.

## Truncation is always visible

A pack over its byte cap omits **whole files**, names every one of them in the
pack body and in the manifest, and tells the reader to open those directly.
Silently truncating would hand a lens a file that looks complete and is not —
a finding-shaped hole that reads as "reviewed". Per this repo's rule, a bound
that drops coverage says so out loud.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_LIB_DIR = _PLUGIN_ROOT / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    import artifact_paths  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    # Same guarded-import shape as the sibling scripts in this directory, which
    # is not in ruff.toml's E402 per-file-ignore list.
    artifact_paths = None

#: Default ceiling on the pack body. A pack is read by every lens in the panel,
#: so bytes here are multiplied by the roster size — the cap is what keeps a
#: large diff from costing more shared than it saved duplicated.
DEFAULT_MAX_BYTES = 400_000

#: Files above this size are omitted individually rather than crowding out the
#: rest of the pack. A single generated or vendored file can exceed the whole
#: budget on its own.
DEFAULT_MAX_FILE_BYTES = 60_000

_CATEGORY = "review-context"


def _git(args, cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=str(cwd), capture_output=True, text=True, timeout=60, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def read_file_text(path: Path) -> tuple[str | None, str]:
    """Return (text, reason). `text` is None when the body cannot be included."""
    try:
        if not path.exists():
            return None, "not present in the working tree (deleted or renamed)"
        if path.is_dir():
            return None, "directory"
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"unreadable ({exc.__class__.__name__})"
    if b"\x00" in raw[:8192]:
        return None, "binary"
    try:
        return raw.decode("utf-8"), ""
    except UnicodeDecodeError:
        return None, "not valid UTF-8"


def number_lines(text: str) -> str:
    """Line-numbered body, matching how the Read tool presents a file so a lens
    can cite `file:line` from the pack without re-opening the file to count."""
    lines = text.splitlines()
    width = len(str(len(lines))) if lines else 1
    return "\n".join(f"{str(i).rjust(width)}\t{line}" for i, line in enumerate(lines, 1))


def select_bodies(files, cwd: Path, max_bytes: int, max_file_bytes: int):
    """Include file bodies in the given order until the budget is spent.

    Returns (included, omitted) where each entry is a dict. Selection walks the
    caller's order and skips anything that does not fit, rather than stopping
    at the first oversized file — one huge file must not hide every smaller one
    behind it.
    """
    included, omitted = [], []
    used = 0
    for rel in files:
        text, reason = read_file_text(cwd / rel)
        if text is None:
            omitted.append({"file": rel, "reason": reason})
            continue
        body = number_lines(text)
        size = len(body.encode("utf-8"))
        if size > max_file_bytes:
            omitted.append({"file": rel, "reason": f"exceeds per-file cap ({size} bytes)"})
            continue
        if used + size > max_bytes:
            omitted.append({"file": rel, "reason": "pack byte budget exhausted"})
            continue
        included.append({"file": rel, "body": body, "bytes": size})
        used += size
    return included, omitted


def render_pack(*, changed, diff_text, included, omitted, base_ref) -> str:
    parts = [
        "# Review context pack",
        "",
        (
            "Prepared once for this panel. Read the section your `Context needs` "
            "declaration calls for instead of opening these files individually — "
            "the bodies below are complete and line-numbered, so `file:line` "
            "citations from this pack are accurate."
        ),
        "",
        (
            "You may still open anything NOT listed here (a caller in an unchanged "
            "file, a sibling module). This pack removes the repeated read of the "
            "changed set; it does not limit what you may consult."
        ),
        "",
        "## Changed files",
        "",
    ]
    if changed:
        # A status is optional: the caller may know the paths without knowing
        # how each changed. Claiming "full-repository scope" in that case (the
        # original behavior) tells a lens the diff is empty when it is not.
        parts += [
            f"- `{status}` {path}" if status else f"- {path}"
            for path, status in changed
        ]
    else:
        parts.append("_(no change list — full-repository scope)_")
    parts += ["", "## Diff", ""]
    parts += [f"_(vs `{base_ref}`)_", "", "```diff", diff_text.rstrip("\n") or "(empty)", "```"] \
        if diff_text.strip() else ["_(no diff — full-repository scope)_"]

    parts += ["", "## File bodies", ""]
    if not included:
        parts.append("_(none included — see omissions below)_")
    for entry in included:
        parts += [f"### {entry['file']}", "", "```", entry["body"], "```", ""]

    if omitted:
        parts += [
            "## NOT included in this pack",
            "",
            (
                "These files are part of the change but their bodies are not "
                "above. **Open them directly** — do not treat their absence as "
                "'nothing to review here'."
            ),
            "",
        ]
        parts += [f"- {o['file']} — {o['reason']}" for o in omitted]
        parts.append("")
    return "\n".join(parts) + "\n"


def _pack_dir(cwd: Path) -> Path:
    if artifact_paths is not None:
        return artifact_paths.category_dir(_CATEGORY, cwd)
    return cwd / ".claude" / _CATEGORY


def build(
    *, files, cwd: Path, base_ref: str, max_bytes: int, max_file_bytes: int,
    diff_text: str | None = None, changed=None,
) -> dict:
    ordered = sorted(dict.fromkeys(files))
    if changed is None:
        changed = [(path, "") for path in ordered]
    if diff_text is None:
        diff_text = _git(["-c", "diff.relative=false", "diff", base_ref, "--", *ordered], cwd) \
            if ordered else ""
    included, omitted = select_bodies(ordered, cwd, max_bytes, max_file_bytes)
    text = render_pack(
        changed=changed or [], diff_text=diff_text, included=included,
        omitted=omitted, base_ref=base_ref,
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    out_dir = _pack_dir(cwd)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pack-{digest}.md"
    out_path.write_text(text, encoding="utf-8")

    unique_bytes = sum(e["bytes"] for e in included)
    return {
        "path": str(out_path),
        "pack_bytes": len(text.encode("utf-8")),
        "unique_body_bytes": unique_bytes,
        "files_requested": len(ordered),
        "files_included": [e["file"] for e in included],
        "files_omitted": omitted,
        "complete": not omitted,
        "base_ref": base_ref,
    }


def parse_name_status(lines) -> list[tuple[str, str]]:
    """Parse `git diff --name-status` rows into (path, status) pairs.

    Rename and copy rows carry two paths (`R100\told\tnew`); the NEW path is
    the one that exists on disk and the one findings are cited against, so it
    is the one kept.
    """
    out: list[tuple[str, str]] = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0].strip():
            continue
        status = parts[0].strip()[0].upper()
        path = parts[-1].strip() if status in {"R", "C"} else parts[1].strip()
        if path:
            out.append((path, status))
    return out


def _read_file_list(source: str | None) -> list[str]:
    if not source:
        return []
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Build one shared context pack for a review panel (#2006)."
    )
    parser.add_argument("--files-from", default="-",
                        help="file with one changed path per line, or '-' for stdin")
    parser.add_argument("--name-status-from", default=None,
                        help="file of `git diff --name-status` lines (or '-'), "
                             "so the pack can label each path A/M/D/R/C")
    parser.add_argument("--base", default="HEAD", dest="base_ref")
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    args = parser.parse_args(argv)

    cwd = Path(args.cwd) if args.cwd else Path.cwd()
    changed = parse_name_status(_read_file_list(args.name_status_from)) \
        if args.name_status_from else None
    files = [p for p, _ in changed] if changed else _read_file_list(args.files_from)
    if not files:
        print(json.dumps({"error": "no files given", "path": None}))
        return 1
    manifest = build(
        files=files, cwd=cwd, base_ref=args.base_ref, changed=changed,
        max_bytes=args.max_bytes, max_file_bytes=args.max_file_bytes,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
