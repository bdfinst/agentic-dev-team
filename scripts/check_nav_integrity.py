#!/usr/bin/env python3
"""Assert every mkdocs nav entry resolves to an assembled file.

Catches the breakage a deleted or renamed doc leaves behind: a nav entry in
mkdocs.yml that points at a file no longer present in the assembled docs tree.
Run after scripts/assemble-docs.sh. Shared by the link-check workflow's
nav-integrity job and scripts/ci-local.sh so the rule has a single definition.

Exit 0 when every nav entry resolves; exit 1 (listing the offenders) otherwise.
"""
import os
import sys

import yaml

OUT = "_mkdocs_src"
CONFIG = "mkdocs.yml"

# mkdocs.yml carries the !!python/name: tag (e.g. the superfences mermaid fence
# format). SafeLoader rejects it, so register a no-op multi-constructor — this
# script only reads the nav, never those values.
yaml.SafeLoader.add_multi_constructor(
    "tag:yaml.org,2002:python/name:", lambda loader, suffix, node: None
)


def collect_missing(node, missing):
    if isinstance(node, list):
        for item in node:
            collect_missing(item, missing)
    elif isinstance(node, dict):
        for value in node.values():
            collect_missing(value, missing)
    elif isinstance(node, str) and not os.path.exists(os.path.join(OUT, node)):
        missing.append(node)


def main():
    with open(CONFIG) as handle:
        nav = yaml.safe_load(handle).get("nav")
    if not nav:
        print(f"no nav defined in {CONFIG} — nothing to check")
        return 0
    missing = []
    collect_missing(nav, missing)
    if missing:
        print(f"nav entries with no matching file under {OUT}/:")
        for entry in missing:
            print("  -", entry)
        print("\nAssemble first (scripts/assemble-docs.sh); a missing entry means "
              "a deleted/renamed doc or a stale nav reference.")
        return 1
    print("OK: every nav entry resolves to an assembled file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
