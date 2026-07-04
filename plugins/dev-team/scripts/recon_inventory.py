#!/usr/bin/env python3
"""Python port of scripts/recon-inventory.sh (#615 / #572 Phase 3).

Canonical file enumeration for the RECON envelope's `file_inventory` field
(primitives contract 1.2.0+). Single source of truth for the enumeration
pipeline; invoked both by the codebase-recon agent and by the
evals/codebase-recon/tests/ test harness.

Usage:
    recon_inventory.py <repo-root> [--slug <slug>]
                                    [--force-filesystem-walk]
                                    [--emit-main-inventory-json <path>]

Output:
    stdout: one repo-relative path per line, LC_ALL=C sorted, deduplicated,
            LF-terminated, no blank lines.
    stderr: human-readable progress + `# BROKEN_SYMLINK: <src> -> <dst>`
            markers (one per broken link). Consumers capture these for the
            envelope `notes` array.
    --emit-main-inventory-json <path>: write a JSON fragment suitable for
            splicing into the main RECON envelope:
                { "source": "...", "count": N, "sibling_ref": "recon-<slug>.inventory.txt" }

Exit codes:
    0  success
    2  usage error
    3  repo root not a directory

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple


def _usage() -> None:
    print(
        "Usage: recon-inventory.sh <repo-root> [--slug <slug>]\n"
        "                                       [--force-filesystem-walk]\n"
        "                                       [--emit-main-inventory-json <path>]",
        file=sys.stderr,
    )


def _parse_argv(argv: List[str]):
    root = ""
    slug = ""
    force_fs = False
    emit_main = ""
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--slug":
            slug = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif tok == "--force-filesystem-walk":
            force_fs = True
            i += 1
        elif tok == "--emit-main-inventory-json":
            emit_main = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        elif tok in ("-h", "--help"):
            _usage()
            sys.exit(2)
        elif tok.startswith("--"):
            print(f"unknown flag: {tok}", file=sys.stderr)
            _usage()
            sys.exit(2)
        else:
            if not root:
                root = tok
            else:
                print(f"unexpected positional arg: {tok}", file=sys.stderr)
                _usage()
                sys.exit(2)
            i += 1
    return root, slug, force_fs, emit_main


def _slugify(name: str) -> str:
    """basename → lowercased, [a-z0-9._-] only, no leading/trailing dashes."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9._-]", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return s


def _parse_excludes(path: Path) -> Tuple[List[str], List[str]]:
    """Parse the two-section excludes file into (prefixes, filenames)."""
    prefixes: List[str] = []
    filenames: List[str] = []
    section = ""
    if not path.is_file():
        return prefixes, filenames
    for raw_line in path.read_text().splitlines():
        line = raw_line
        if re.match(
            r"^[[:space:]]*#[[:space:]]*prefix:[[:space:]]*$".replace(
                "[[:space:]]", r"\s"
            ),
            line,
        ):
            section = "prefix"
            continue
        if re.match(
            r"^[[:space:]]*#[[:space:]]*filename:[[:space:]]*$".replace(
                "[[:space:]]", r"\s"
            ),
            line,
        ):
            section = "filename"
            continue
        if re.match(r"^\s*#", line):
            continue
        if not line.strip():
            continue
        entry = line.strip()
        entry = entry.rstrip("/")
        if section == "prefix":
            prefixes.append(entry)
        elif section == "filename":
            filenames.append(entry)
    return prefixes, filenames


def _collect_git(root_abs: Path) -> List[str]:
    """Git branch: `ls-files -z` emits repo-relative paths including
    submodule gitlinks (once, not recursed)."""
    try:
        r = subprocess.run(
            ["git", "-C", str(root_abs), "ls-files", "-z"],
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return []
    if r.returncode != 0:
        return []
    # NUL-delimited output; drop trailing empty split.
    return [line for line in r.stdout.decode(errors="replace").split("\0") if line]


def _collect_fs(root_abs: Path, excludes_file: Path) -> List[str]:
    """Filesystem walk with excludes. Prunes directories whose name matches
    a `# prefix:` entry (anywhere in the tree) and skips filenames matching
    `# filename:` entries."""
    prefixes, filenames = _parse_excludes(excludes_file)
    prefix_set: Set[str] = set(prefixes)
    filename_set: Set[str] = set(filenames)

    out: List[str] = []
    root_str = str(root_abs)
    for dirpath, dirnames, files in os.walk(root_abs):
        # Prune matching directory names in-place so os.walk skips them.
        dirnames[:] = [d for d in dirnames if d not in prefix_set]
        for f in files:
            if f in filename_set:
                continue
            abs_path = os.path.join(dirpath, f)
            # Only include regular files (skip devices, fifos, sockets).
            try:
                st = os.lstat(abs_path)
            except OSError:
                continue
            # Match the .sh's `find -type f`: only include REGULAR files.
            # Symlinks are silently dropped in fs-walk mode (only the
            # git-ls-files branch surfaces committed symlinks, which then
            # go through _resolve_symlinks for BROKEN_SYMLINK logging).
            import stat as st_mod

            if not st_mod.S_ISREG(st.st_mode):
                continue
            rel = os.path.relpath(abs_path, root_str)
            out.append(rel)
    return out


def _resolve_symlinks(root_abs: Path, entries: List[str]) -> List[str]:
    """Substitute each symlink with its resolved real path; drop + log
    broken / outside-repo links."""
    resolved: List[str] = []
    for rel in entries:
        if not rel:
            continue
        abs_path = root_abs / rel
        if abs_path.is_symlink():
            if not abs_path.exists():
                print(f"# BROKEN_SYMLINK: {rel} -> (missing target)", file=sys.stderr)
                continue
            try:
                real = abs_path.resolve()
            except OSError:
                print(f"# BROKEN_SYMLINK: {rel} -> (unresolvable)", file=sys.stderr)
                continue
            try:
                real_rel = real.relative_to(root_abs.resolve())
            except ValueError:
                print(
                    f"# BROKEN_SYMLINK: {rel} -> {real} (outside repo)",
                    file=sys.stderr,
                )
                continue
            resolved.append(str(real_rel))
        else:
            resolved.append(rel)
    return resolved


def main(argv: List[str]) -> int:
    parsed = _parse_argv(argv)
    if not parsed[0]:
        _usage()
        return 2
    root, slug, force_fs, emit_main = parsed

    if not os.path.isdir(root):
        print(f"repo-root is not a directory: {root}", file=sys.stderr)
        return 3

    # Normalize root to an absolute real path so relative computations are
    # stable. bash used `cd "$ROOT" && pwd -P`; Path.resolve() gives the
    # equivalent.
    root_abs = Path(root).resolve()

    if not slug:
        slug = _slugify(root_abs.name)

    # `plugins/dev-team/knowledge/recon-inventory-excludes.txt` — same
    # location as the .sh (`dirname/../knowledge/...`).
    excludes_file = (
        Path(__file__).resolve().parent.parent
        / "knowledge"
        / "recon-inventory-excludes.txt"
    )

    # Decide branch.
    is_git = (root_abs / ".git").is_dir() or (root_abs / ".git").is_file()
    if force_fs or not is_git:
        source = "filesystem-walk"
        raw = _collect_fs(root_abs, excludes_file)
    else:
        source = "git-ls-files"
        raw = _collect_git(root_abs)

    resolved = _resolve_symlinks(root_abs, raw)

    # Sort + dedupe under LC_ALL=C for cross-locale determinism.
    unique = sorted(set(resolved))

    # Emit stdout: the inventory (LF-terminated).
    for entry in unique:
        print(entry)

    # Optionally emit the main-envelope JSON fragment.
    if emit_main:
        count = len(unique)
        payload = (
            f'{{ "source": "{source}", "count": {count}, '
            f'"sibling_ref": "recon-{slug}.inventory.txt" }}\n'
        )
        Path(emit_main).write_text(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
