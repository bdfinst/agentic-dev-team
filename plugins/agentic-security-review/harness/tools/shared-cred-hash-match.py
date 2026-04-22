#!/usr/bin/env python3
"""shared-cred-hash-match — cross-repo shared-credential detector.

Walks multiple repos for env-file values, computes SHA-256 hashes, and emits
SARIF findings for hash values that appear in more than one repo. Used by
/cross-repo-analysis to surface credential reuse across services (e.g. the
same API token present in three different microservices).

Emits SARIF 2.1.0 on stdout.

Usage:
    shared-cred-hash-match.py <repo-path> <repo-path> [<repo-path> ...]

Exit codes:
    0  — scan complete (findings reported via SARIF, not exit code)
    2  — argument error (fewer than two repos)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_FILE_PATTERNS = (".env", ".env.local", ".env.development", ".env.staging",
                     ".env.production", ".env.test", ".env.example")
SENSITIVE_KEY_PATTERN = re.compile(
    r"^(?P<key>[A-Z_][A-Z0-9_]*(PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|CREDENTIAL|KEY))\s*=\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Location:
    repo: str
    file: str
    line: int


def is_env_file(path: Path) -> bool:
    return path.name in ENV_FILE_PATTERNS or path.name.startswith(".env.")


def walk_envs(repo_path: Path) -> list[tuple[Path, str, int, str]]:
    """Return [(path, key, line, value), ...]."""
    out: list[tuple[Path, str, int, str]] = []
    for path in repo_path.rglob("*"):
        if not path.is_file() or not is_env_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = SENSITIVE_KEY_PATTERN.match(stripped)
            if not m:
                continue
            value = m.group("value").strip().strip('"').strip("'")
            if not value or value.lower() in {"changeme", "replace-me", "fixme", "xxx"}:
                continue
            out.append((path, m.group("key"), lineno, value))
    return out


def sarif_from_findings(
    matches: dict[str, list[Location]], repo_roots: list[str]
) -> dict:
    """Build SARIF with one result per Location that's part of a shared-hash group."""
    rules = [{"id": "shared-credential", "shortDescription": {"text": "Same secret value appears in multiple repos"}}]
    results = []
    for h, locs in matches.items():
        if len(locs) < 2:
            continue
        # Emit one result per location, citing the shared-hash group
        other_repos = sorted({loc.repo for loc in locs})
        for loc in locs:
            results.append({
                "ruleId": "shared-credential",
                "ruleIndex": 0,
                "level": "error",
                "message": {
                    "text": (
                        f"Secret value (SHA-256 {h[:12]}...) also appears in "
                        f"{len(other_repos) - 1} other repo(s): "
                        f"{', '.join(r for r in other_repos if r != loc.repo)}"
                    )
                },
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": loc.file},
                        "region": {"startLine": loc.line},
                    }
                }],
            })

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "shared-cred-hash-match",
                    "version": "1.0.0",
                    "informationUri": "https://github.com/bdfinst/agentic-dev-team",
                    "rules": rules,
                }
            },
            "results": results,
        }],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Repo paths (two or more).")
    args = parser.parse_args()

    if len(args.paths) < 2:
        print("shared-cred-hash-match: at least 2 repo paths required", file=sys.stderr)
        return 2

    repo_roots = [str(Path(p).resolve()) for p in args.paths]

    # hash -> list[Location]
    hash_map: dict[str, list[Location]] = {}
    for repo_path_str in args.paths:
        repo = Path(repo_path_str)
        if not repo.is_dir():
            print(f"skipping non-directory: {repo}", file=sys.stderr)
            continue
        for path, _key, line, value in walk_envs(repo):
            h = hashlib.sha256(value.encode("utf-8")).hexdigest()
            loc = Location(repo=str(repo.resolve()), file=str(path), line=line)
            hash_map.setdefault(h, []).append(loc)

    sarif = sarif_from_findings(hash_map, repo_roots)
    json.dump(sarif, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
