#!/usr/bin/env python3
"""Broken-reference sensor — a doc names a real repo file by a path that misses it.

A skill, agent, or knowledge file routinely names another file: a markdown link
``[text](../knowledge/x.md)`` or a backtick-quoted path ``knowledge/x.md``. The
runtime that loads these files resolves such a reference RELATIVE TO THE FILE IT
APPEARS IN — so a skill at ``skills/ship/SKILL.md`` that says ``knowledge/x.md``
is asking for ``skills/ship/knowledge/x.md``; if the real file is the plugin-root
``knowledge/x.md`` the reference must be ``../../knowledge/x.md``. When a file is
renamed or moved and a reference is left behind, the link dangles — invisible
until something reads it and fails (e.g. /ship's decision-defaults screen).

A reference is flagged only when BOTH hold:

  * it resolves under NONE of the bases a reader might use — relative to its own
    file, the module root (``plugins/<name>``), the repo root, or with
    ``${CLAUDE_PLUGIN_ROOT}/`` rewritten to the module root; and
  * a real tracked file or directory's path ENDS WITH the reference — i.e. the
    doc is plainly naming a file that exists in the repo, just by the wrong path.

That pair is the precise signature of a misrouted link. The second condition is
what keeps this check SELF-MAINTAINING: it reads the live ``git`` file tree
instead of a hand-kept allowlist, so references to things that are not repo files
— runtime artifacts (``memory/``, ``metrics/``), a consuming project's own tree
(``src/``), planned-but-unbuilt paths, ``knowledge/X.md`` placeholders — match no
real file and are ignored automatically, with nothing to update as the repo
changes.

Exit 0 when every reference resolves or names nothing real; exit 1 with a
per-break report otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# The dev-team plugin's FUNCTIONAL surface — files whose references are read at
# runtime, so a dangling one breaks a real skill/agent run. Descriptive trees
# (docs/, CHANGELOG) and the separate security-assessment plugin are out of scope:
# they carry historical/illustrative paths that are not live references.
SCAN_DIRS = (
    "plugins/dev-team/skills",
    "plugins/dev-team/agents",
    "plugins/dev-team/knowledge",
    "plugins/dev-team/prompts",
)
SCAN_FILES = ("plugins/dev-team/CLAUDE.md",)
SKIP_FILENAMES = ("CHANGELOG.md",)

# Synthetic project trees under here are eval scaffolding, not the repo's own
# structure. Excluding them from the real-file index stops a descriptive path
# (e.g. `.claude/skills/`) from coincidentally matching a fixture and false-firing.
INDEX_EXCLUDE_PREFIXES = (
    "evals/fixtures/",
    # Parity fixtures seed runtime-shape files (e.g. StrykerOutput/…) into a
    # sandbox tree. They are test scaffolding for the bash → python hook
    # migration harness (#574), not references from the repo's own docs.
    "plugins/dev-team/tests/hooks/parity/fixtures/",
)

PATH_EXTS = ("md", "json", "sh", "py", "svg", "tmpl", "txt", "yml", "yaml", "cfg")
_EXT_ALT = "|".join(PATH_EXTS)
_PATHLIKE = re.compile(r"^[\w.\-/]+\.(?:" + _EXT_ALT + r")$")
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_BACKTICK = re.compile(r"`([^`]+)`")
_PLUGIN_ROOT_VAR = "${CLAUDE_PLUGIN_ROOT}/"
_NONLITERAL = re.compile(r"[<>*|]")  # glob / placeholder markers (the plugin-root
# var is stripped before this test, so its ${} is fine)
_MD_HEADING = re.compile(r"^#+\s+(.+)$")  # markdown heading: # Title


def _candidates(line: str):
    # Markdown link targets first; then REMOVE the whole [label](target) spans so a
    # backtick-quoted link label (display text, e.g. `foo/SKILL.md`) is not then
    # re-checked as if it were a path — only the link's target is a real reference.
    for m in _MD_LINK.finditer(line):
        yield m.group(1)
    for m in _BACKTICK.finditer(_MD_LINK.sub(" ", line)):
        yield m.group(1)


def _normalize(ref: str):
    """Return a checkable path (``${CLAUDE_PLUGIN_ROOT}/`` preserved), or None.

    Preserves #anchor fragments if present — anchor validation happens separately.
    """
    ref = ref.strip()
    if not ref:
        return None
    ref = ref.split(" ", 1)[0]  # drop a markdown link title
    if ref.startswith("#"):
        return None
    lower = ref.split("#", 1)[0].lower() if "#" in ref else ref.lower()
    if lower.startswith(("http://", "https://", "mailto:", "tel:")):
        return None
    path_part = ref.split("#", 1)[0]
    if not path_part:
        return None
    if ref.startswith("~") or ref.startswith("/"):
        return None  # home-relative or absolute system paths: not repo references
    body = (
        path_part[len(_PLUGIN_ROOT_VAR) :]
        if path_part.startswith(_PLUGIN_ROOT_VAR)
        else path_part
    )
    if "$" in body or _NONLITERAL.search(body):
        return None  # other shell vars / globs / placeholders: not statically checkable
    is_dir = body.endswith("/")
    if "/" not in body.rstrip("/"):
        return None  # bare filename, not an intra-repo path
    if not is_dir and not _PATHLIKE.match(body):
        return None
    return ref


def _present(base: str, rel: str, is_dir: bool, root: str, tracked: set):
    target = os.path.normpath(os.path.join(base, rel.lstrip("/")))
    if os.path.isdir(target) if is_dir else os.path.exists(target):
        return True
    # Environment-independent fallback: a path that IS a tracked repo entry counts
    # as present even when os.path can't resolve it — e.g. a tracked symlink that a
    # CI checkout leaves unmaterialized (`.claude/evals/fixtures` → `evals/…`),
    # which would otherwise read as dangling on Linux but resolved on macOS.
    return os.path.relpath(target, root) in tracked


def _resolve_path(ref: str, file_dir: str, module_root: str, root: str, tracked: set):
    """Return the resolved path for a reference, or None if unresolvable."""
    is_dir = ref.endswith("/")
    bases = []
    if ref.startswith(_PLUGIN_ROOT_VAR):
        bases = [(module_root, ref[len(_PLUGIN_ROOT_VAR) :])]
    else:
        bases = [(file_dir, ref), (module_root, ref), (root, ref)]

    for base, rel in bases:
        target = os.path.normpath(os.path.join(base, rel.lstrip("/")))
        if os.path.isdir(target) if is_dir else os.path.exists(target):
            return target
        # Check tracked paths as fallback
        rel_target = os.path.relpath(target, root)
        if rel_target in tracked:
            return target
    return None


def _resolves(ref: str, file_dir: str, module_root: str, root: str, tracked: set):
    is_dir = ref.endswith("/")
    if ref.startswith(_PLUGIN_ROOT_VAR):
        return _present(
            module_root, ref[len(_PLUGIN_ROOT_VAR) :], is_dir, root, tracked
        )
    return (
        _present(file_dir, ref, is_dir, root, tracked)
        or _present(module_root, ref, is_dir, root, tracked)
        or _present(root, ref, is_dir, root, tracked)
    )


def _module_root(path: str, root: str):
    rel = os.path.relpath(path, root)
    parts = rel.split(os.sep)
    if len(parts) >= 2 and parts[0] == "plugins":
        return os.path.join(root, parts[0], parts[1])
    return root


def _ref_tail(ref: str):
    """The reference reduced to its meaningful path tail (no var, no ./.. prefix)."""
    body = ref[len(_PLUGIN_ROOT_VAR) :] if ref.startswith(_PLUGIN_ROOT_VAR) else ref
    parts = [p for p in body.strip("/").split("/") if p not in (".", "..")]
    return "/".join(parts)


def _real_file_list(root: str):
    """Tracked files under root (git), or a filesystem walk when not a git repo.

    git is preferred: it is fast and already excludes gitignored runtime artifacts
    (memory/, metrics/ …) so they never count as real files. The walk fallback
    keeps the checker usable on a plain directory (e.g. a test fixture)."""
    try:
        out = subprocess.run(
            ["git", "-C", root, "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        files = [f for f in out.splitlines() if f.strip()]
        if files:
            return files
    except (OSError, subprocess.CalledProcessError):
        pass
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [x for x in dirnames if x not in (".git", "node_modules")]
        for fn in filenames:
            files.append(
                os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/")
            )
    return files


def _tracked_paths(root: str):
    """Every real path (files + their parent dirs) — the resolution authority.

    No exclusions: a reference TO any tracked path (including a synthetic-fixture
    tree or a tracked symlink) must count as resolved."""
    paths = set()
    for f in _real_file_list(root):
        f = f.strip()
        if not f:
            continue
        paths.add(f)
        d = os.path.dirname(f)
        while d:
            paths.add(d)
            d = os.path.dirname(d)
    return paths


def _build_real_index(tracked: set):
    """basename -> real paths, for suffix-matching a dangling ref to a real file.

    Synthetic fixture trees are excluded HERE only (not from resolution) so a
    descriptive path can't coincidentally suffix-match a throwaway fixture."""
    index = {}
    for p in tracked:
        if p.startswith(INDEX_EXCLUDE_PREFIXES):
            continue
        index.setdefault(p.rsplit("/", 1)[-1], set()).add(p)
    return index


def _names_real_file(ref: str, real_index):
    tail = _ref_tail(ref)
    if not tail:
        return False
    last = tail.rsplit("/", 1)[-1]
    for cand in real_index.get(last, ()):
        if cand == tail or cand.endswith("/" + tail):
            return True
    return False


def _gfm_slug(heading: str) -> str:
    """Convert a markdown heading to its GFM anchor slug.

    GFM slug: remove backticks but keep content, lowercase, strip non-word/non-space/non-hyphen,
    collapse consecutive spaces/hyphens to single hyphen, trim leading/trailing hyphens.
    """
    # Remove backticks but keep their content
    s = re.sub(r"`([^`]*)`", r"\1", heading)
    # Lowercase
    s = s.lower()
    # Keep only word chars, spaces, and hyphens
    s = re.sub(r"[^\w\s\-]", "", s)
    # Collapse multiple spaces/hyphens to single hyphen
    s = re.sub(r"[\s\-]+", "-", s)
    # Strip leading/trailing hyphens
    s = s.strip("-")
    return s


def _extract_heading_slugs(path: str) -> set[str]:
    """Extract all GFM heading slugs from a markdown file."""
    slugs = set()
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return slugs
    with fh:
        for line in fh:
            m = _MD_HEADING.match(line.rstrip())
            if m:
                heading_text = m.group(1)
                slug = _gfm_slug(heading_text)
                if slug:
                    slugs.add(slug)
    return slugs


def _check_file(path: str, root: str, real_index, tracked):
    breaks = []
    file_dir = os.path.dirname(path)
    mod_root = _module_root(path, root)
    in_fence = False
    fence_marker = ""
    # Cache for extracted heading slugs (path -> set of slugs)
    slug_cache = {}

    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return breaks  # unreadable (e.g. a broken symlink) — nothing to scan
    with fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.lstrip()
            if in_fence:
                if stripped.startswith(fence_marker):
                    in_fence = False
                continue
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = True
                fence_marker = stripped[:3]
                continue
            for raw in _candidates(line):
                ref = _normalize(raw)
                if ref is None:
                    continue

                # Split ref into path and anchor parts
                path_part, anchor = (ref.split("#", 1) if "#" in ref else (ref, None))

                if _resolves(path_part, file_dir, mod_root, root, tracked):
                    # Path resolves; if there's an anchor, validate it
                    if anchor:
                        # Resolve the actual file path to validate the anchor
                        target_path = _resolve_path(
                            path_part, file_dir, mod_root, root, tracked
                        )
                        if target_path and target_path.endswith(".md"):
                            # Extract heading slugs if not cached
                            if target_path not in slug_cache:
                                slug_cache[target_path] = _extract_heading_slugs(
                                    target_path
                                )
                            slugs = slug_cache[target_path]
                            # Check if anchor matches any heading slug
                            if anchor not in slugs:
                                breaks.append((line_no, ref))
                    continue

                if _names_real_file(path_part, real_index):
                    breaks.append((line_no, ref))
    return breaks


def _iter_md_files(root: str):
    for d in SCAN_DIRS:
        top = os.path.join(root, d)
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [x for x in dirnames if x not in (".git", "node_modules")]
            for fn in sorted(filenames):
                if fn.endswith(".md") and fn not in SKIP_FILENAMES:
                    yield os.path.join(dirpath, fn)
    for f in SCAN_FILES:
        p = os.path.join(root, f)
        if os.path.isfile(p):
            yield p


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=None, help="repo root (default: git toplevel)"
    )
    args = parser.parse_args(argv)

    root = args.root
    if root is None:
        root = (
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            or "."
        )
    root = os.path.abspath(root)

    tracked = _tracked_paths(root)
    real_index = _build_real_index(tracked)

    total = 0
    for path in _iter_md_files(root):
        for line_no, ref in _check_file(path, root, real_index, tracked):
            rel = os.path.relpath(path, root)
            if "#" in ref:
                print(f"{rel}:{line_no}  `{ref}`  anchor does not exist in target file")
            else:
                print(f"{rel}:{line_no}  `{ref}`  names a real file but resolves nowhere")
            total += 1

    if total:
        print(
            f"\n{total} reference error(s): either the path resolves to the wrong place "
            f"or an anchor does not exist. Fix the path (a file-relative path, or "
            f"${{CLAUDE_PLUGIN_ROOT}}/… for a runtime read) or the anchor target.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
