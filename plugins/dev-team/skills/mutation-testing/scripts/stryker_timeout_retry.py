#!/usr/bin/env python3
"""stryker_timeout_retry.py — emit a Stryker retry config scoped to timed-out files.

Migrated from the ACI ``nextgen-test-upgrade-process`` ``stryker-retry-timeouts.py``
and de-hardcoded: nothing repo-specific lives here. Given a mutation report
containing Timeout mutants, this emits a ``stryker-config.timeout-retry.json``
scoped to **only** the files that timed out, with an increased
``additional-timeout`` so a genuinely-slow-but-covered mutant gets the extra
time it needs on the retry pass instead of being written off as a timeout.

Timeouts are not demonstrated kills — the honest score excludes them (see
``mutation_report``). Retrying them at a higher timeout is how a real kill (or
a real survivor) is teased out of the noise.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). No sibling
imports required.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

DEFAULT_ADDITIONAL_TIMEOUT_MS = 10000
RETRY_CONFIG_NAME = "stryker-config.timeout-retry.json"


def timeout_files_from_report(report_path: Path) -> Dict[str, int]:
    """Return ``{source_file: timeout_count}`` for every file with Timeouts."""
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    by_file: Dict[str, int] = {}
    for key, info in data.get("files", {}).items():
        count = sum(1 for m in info.get("mutants", []) if m.get("status") == "Timeout")
        if count:
            by_file[key] = count
    return by_file


def build_mutate_globs(paths: Sequence[str]) -> List[str]:
    """Scope ``mutate`` to only the given files, by basename glob, so no other
    file is re-mutated on the retry pass. Backslashes are normalized so a
    Windows-style report path still yields a POSIX basename glob."""
    return [f"**/{Path(p.replace(chr(92), '/')).name}" for p in sorted(paths)]


def load_base_config(base_config_path: Path) -> dict:
    """Parse the base ``stryker-config.json``, tolerating the wrapper shape
    (keys nested under a top-level ``"stryker-config"`` object) or flat keys."""
    raw = json.loads(Path(base_config_path).read_text(encoding="utf-8"))
    return raw.get("stryker-config", raw)


def build_retry_config(
    base: dict, mutate: Sequence[str], additional_timeout_ms: int
) -> dict:
    """Build the retry config, inheriting solution / project / test-projects
    from the base config and raising ``additional-timeout`` by
    ``additional_timeout_ms`` on top of whatever the base already had (so the
    retry timeout is always strictly larger than the original)."""
    increased = int(base.get("additional-timeout", 0)) + int(additional_timeout_ms)
    cfg = {
        "solution": base.get("solution"),
        "project": base.get("project"),
        "test-projects": list(base.get("test-projects", [])),
        "mutate": list(mutate),
        "additional-timeout": increased,
        "reporters": ["json", "progress"],
        "coverage-analysis": "off",
    }
    cfg = {k: v for k, v in cfg.items() if v is not None}
    return {"stryker-config": cfg}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stryker_timeout_retry.py",
        description="Emit a Stryker retry config scoped to the report's timed-out files",
    )
    parser.add_argument("report", help="Path to a Stryker mutation-report.json")
    parser.add_argument(
        "--base-config",
        default="stryker-config.json",
        help="Base config to inherit solution/project/test-projects from",
    )
    parser.add_argument(
        "--additional-timeout-ms",
        type=int,
        default=DEFAULT_ADDITIONAL_TIMEOUT_MS,
        help="Milliseconds to add on top of the base additional-timeout (default: %(default)s)",
    )
    parser.add_argument("--out", default=RETRY_CONFIG_NAME, help="Output config path")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))

    by_file = timeout_files_from_report(Path(args.report))
    if not by_file:
        print("No Timeout mutations found in the report. Nothing to retry.")
        return 0

    total = sum(by_file.values())
    print(f"Found {total} timeout mutation(s) across {len(by_file)} file(s):")
    for path, count in sorted(by_file.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:4d}  {path}")

    mutate = build_mutate_globs(list(by_file))
    base = load_base_config(Path(args.base_config))
    retry = build_retry_config(base, mutate, args.additional_timeout_ms)

    content = json.dumps(retry, indent=2) + "\n"
    if args.dry_run:
        print("\n(dry-run) Would write:")
        print(content)
        return 0

    Path(args.out).write_text(content, encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
