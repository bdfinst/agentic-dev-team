#!/usr/bin/env python3
"""stryker_shard_setup.py — auto-configure Stryker mutation shards for any C# repo.

Generic, stdlib-only, cross-platform (macOS, Linux, Windows). Sole runtime
dependency is python3 (>= 3.8) on PATH. Carries no repo-specific literal —
project names, test-library names, and paths all come from the solution file
being parsed and the repo root supplied on the command line, never from this
module.

Parses the solution file, classifies each project as source or test (by name
pattern), pairs each source project with its test projects (case-insensitive
prefix match), then generates:

  * stryker-config.shard-<slug>.json  — one per source project
  * Stryker.sln                        — includes all source + test projects
  * stryker-pipeline.json              — discovered defaults (if missing)

The repo root is taken from ``--repo-root`` or, when omitted, the current
working directory — never a hardcoded path. Run once after adding or removing
projects; the generated files should be committed.

Usage:
  python3 stryker_shard_setup.py                       # auto-discover, write files
  python3 stryker_shard_setup.py --dry-run             # print without writing
  python3 stryker_shard_setup.py --solution Foo.sln    # explicit solution file
  python3 stryker_shard_setup.py --repo-root path/to   # explicit repo root
  python3 stryker_shard_setup.py --update              # overwrite stryker-pipeline.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_TEST_PATTERNS = [".Tests", ".Test", "Tests", "Specs"]
STRYKER_SLN_NAME = "Stryker.sln"
PIPELINE_CONFIG_NAME = "stryker-pipeline.json"

# Matches `Project("{type-guid}") = "Name", "relative\path.csproj"` lines.
_SLN_PROJECT_RE = re.compile(
    r'^Project\("\{[^}]+\}"\)\s*=\s*"([^"]+)",\s*"([^"]+\.csproj)"',
    re.MULTILINE,
)

# Matches the same lines but also captures the project's own GUID (4th field).
_SLN_GUID_RE = re.compile(
    r'^Project\("\{[^}]+\}"\)\s*=\s*"([^"]+)",\s*"[^"]+",\s*"\{([^}]+)\}"',
    re.MULTILINE,
)

_SLN_PROJECT_TYPE_GUID = "9A19103F-16F7-4668-BE54-9A1E7A4F7556"

_SLN_HEADER = (
    "Microsoft Visual Studio Solution File, Format Version 12.00\n"
    "# Visual Studio Version 17\n"
    "VisualStudioVersion = 17.0.0.0\n"
    "MinimumVisualStudioVersion = 10.0.40219.1\n"
)


# ── Repo-relative helpers ────────────────────────────────────────────────────


def _rel_to_root(path: Path, repo_root: Path) -> str:
    """Repo-root-relative POSIX path, falling back to the resolved path."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        rel = path.resolve()
    return rel.as_posix()


def _is_within(path: Path, root: Path) -> bool:
    """Return True iff ``path`` resolves to a location inside ``root``.

    ``Path.is_relative_to`` is 3.9+, so we use ``relative_to`` and catch the
    ``ValueError`` it raises for a path outside ``root`` — a 3.8-compatible
    containment check used to refuse any shard-config write that would escape
    the repo root.
    """
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# ── Pipeline config + solution discovery (inlined — no shared _common) ───────


def load_pipeline_config(repo_root: Path) -> dict:
    """Return parsed stryker-pipeline.json under repo_root, or {} if absent."""
    config_path = repo_root / PIPELINE_CONFIG_NAME
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def discover_solution(repo_root: Path) -> Path:
    """Return the solution file to use.

    Resolution order:
      1. stryker-pipeline.json["solution"] (relative to repo_root)
      2. Alphabetically first *.sln in repo_root, excluding Stryker.sln

    Raises FileNotFoundError, naming how to specify one, when none is found.
    """
    cfg = load_pipeline_config(repo_root)
    configured = cfg.get("solution")
    if configured:
        candidate = repo_root / configured
        if candidate.exists():
            return candidate

    slns = sorted(p for p in repo_root.glob("*.sln") if p.name != STRYKER_SLN_NAME)
    if slns:
        return slns[0]

    raise FileNotFoundError(
        f"No solution file found in {repo_root}. Specify one with "
        f"--solution <path>, add a 'solution' key to {PIPELINE_CONFIG_NAME}, "
        "or ensure a *.sln exists in the repo root."
    )


# ── Solution parsing ─────────────────────────────────────────────────────────


def parse_projects(sln_path: Path) -> list[dict]:
    """Return [{name, path, rel}] for every .csproj entry in the solution."""
    text = sln_path.read_text(encoding="utf-8")
    projects: list[dict] = []
    for name, rel_path in _SLN_PROJECT_RE.findall(text):
        norm = rel_path.replace("\\", "/")
        abs_path = (sln_path.parent / norm).resolve()
        projects.append({"name": name, "path": abs_path, "rel": norm})
    return projects


def parse_guids(sln_path: Path) -> dict[str, str]:
    """Return {project_name: GUID} for an existing sln (empty if absent)."""
    if not sln_path.exists():
        return {}
    text = sln_path.read_text(encoding="utf-8")
    return {name: guid for name, guid in _SLN_GUID_RE.findall(text)}


# ── Classification ───────────────────────────────────────────────────────────


def test_patterns(cfg: dict) -> list[str]:
    return cfg.get("test_project_patterns", DEFAULT_TEST_PATTERNS)


def is_test_project(name: str, patterns: Sequence[str]) -> bool:
    name_lower = name.lower()
    return any(p.lower() in name_lower for p in patterns)


# ── Slug derivation ──────────────────────────────────────────────────────────


def _kebab(text: str) -> str:
    """Insert a hyphen at lower/digit→upper boundaries, then lowercase."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", text).lower()


def _sanitize_slug(text: str) -> str:
    """Reduce a slug to the strict filename-safe charset ``[a-z0-9-]``.

    A slug is derived from a project name in the solution file — untrusted
    input. A hostile name (``Foo/../../evil``) could otherwise smuggle path
    separators or ``..`` into a shard-config filename and escape the repo root
    (path traversal). Any run of out-of-charset characters collapses to a
    single hyphen; leading/trailing hyphens are trimmed.
    """
    return re.sub(r"[^a-z0-9-]+", "-", text).strip("-")


def slug(name: str) -> str:
    """Kebab-case of the last dotted segment, sanitized to ``[a-z0-9-]``.

    e.g. Foo.WebAPI -> web-api, Foo.ApplicationServices -> application-services.
    """
    return _sanitize_slug(_kebab(name.split(".")[-1]))


def _full_slug(name: str) -> str:
    """Kebab-case of the entire dotted name (dots become hyphens), sanitized.

    Used to disambiguate two projects whose last segments collide.
    """
    return _sanitize_slug(_kebab(name).replace(".", "-"))


def assign_slugs(sources: Sequence[dict]) -> dict[str, dict]:
    """Map a unique slug to each source project.

    A bare last-segment slug is used when unique; when two projects share a
    last segment the full dotted name is kebab-cased instead, and a numeric
    suffix is appended as a final guard, so no shard config filename ever
    overwrites another.
    """
    base_counts = Counter(slug(src["name"]) for src in sources)
    assigned: dict[str, dict] = {}
    used: set = set()
    for src in sources:
        base = slug(src["name"])
        candidate = base if base_counts[base] == 1 else _full_slug(src["name"])
        unique = candidate
        suffix = 2
        while unique in used:
            unique = f"{candidate}-{suffix}"
            suffix += 1
        used.add(unique)
        assigned[unique] = src
    return assigned


# ── Pairing ──────────────────────────────────────────────────────────────────


def build_shards(
    sources: Sequence[dict],
    tests: Sequence[dict],
    repo_root: Path,
) -> dict[str, dict]:
    """Return {slug: shard-info} pairing each source with its test projects.

    A source whose name prefix-matches no test project falls back to the full
    set of test projects rather than an empty list. Multiple prefix-matching
    test projects are all paired.
    """
    assigned = assign_slugs(sources)
    all_test_paths = [_rel_to_root(t["path"], repo_root) for t in tests]

    shards: dict[str, dict] = {}
    for shard_slug, src in assigned.items():
        src_lower = src["name"].lower()
        matched = [t for t in tests if t["name"].lower().startswith(src_lower)]
        test_paths = (
            [_rel_to_root(t["path"], repo_root) for t in matched]
            if matched
            else all_test_paths
        )

        src_dir = src["path"].parent
        mutate_pattern = _rel_to_root(src_dir, repo_root) + "/**/*.cs"

        shards[shard_slug] = {
            "source_project": _rel_to_root(src["path"], repo_root),
            "test_projects": test_paths,
            "mutate": [mutate_pattern],
        }
    return shards


# ── Emission ─────────────────────────────────────────────────────────────────


def shard_config(info: dict) -> dict:
    """Build the stryker-config.shard-<slug>.json content for one source."""
    config = {
        "solution": STRYKER_SLN_NAME,
        # `project` tells Stryker which csproj to instrument. Without it,
        # Stryker only instruments the master config's project and silently
        # ignores mutations in every other source project.
        "project": info["source_project"],
        "test-projects": info["test_projects"],
        "mutate": info["mutate"],
        "reporters": ["html", "json", "progress"],
        "coverage-analysis": "off",
        "thresholds": {"high": 80, "low": 10, "break": 0},
    }
    return {"stryker-config": config}


def generate_stryker_sln(
    sources: Sequence[dict],
    tests: Sequence[dict],
    repo_root: Path,
    main_sln: Path,
) -> str:
    """Render a Stryker.sln listing every source and test project."""
    existing_guids = parse_guids(repo_root / STRYKER_SLN_NAME)
    main_guids = parse_guids(main_sln)

    project_lines: list[str] = []
    config_lines: list[str] = []
    for proj in list(sources) + list(tests):
        guid = (
            existing_guids.get(proj["name"])
            or main_guids.get(proj["name"])
            or str(uuid.uuid5(uuid.NAMESPACE_DNS, proj["name"])).upper()
        )
        rel = _rel_to_root(proj["path"], repo_root).replace("/", "\\")
        project_lines.append(
            f'Project("{{{_SLN_PROJECT_TYPE_GUID}}}") = '
            f'"{proj["name"]}", "{rel}", "{{{guid}}}"\nEndProject'
        )
        config_lines.append(
            f"\t\t{{{guid}}}.Debug|Any CPU.ActiveCfg = Debug|Any CPU\n"
            f"\t\t{{{guid}}}.Debug|Any CPU.Build.0 = Debug|Any CPU\n"
            f"\t\t{{{guid}}}.Release|Any CPU.ActiveCfg = Release|Any CPU\n"
            f"\t\t{{{guid}}}.Release|Any CPU.Build.0 = Release|Any CPU"
        )

    return (
        _SLN_HEADER
        + "\n".join(project_lines)
        + "\nGlobal\n"
        + "\tGlobalSection(SolutionConfigurationPlatforms) = preSolution\n"
        + "\t\tDebug|Any CPU = Debug|Any CPU\n"
        + "\t\tRelease|Any CPU = Release|Any CPU\n"
        + "\tEndGlobalSection\n"
        + "\tGlobalSection(ProjectConfigurationPlatforms) = postSolution\n"
        + "\n".join(config_lines)
        + "\n\tEndGlobalSection\nEndGlobal\n"
    )


# ── Main ─────────────────────────────────────────────────────────────────────


def _resolve_solution(args: argparse.Namespace, repo_root: Path) -> Path | None:
    """Return the solution path, or None (after printing an error) on failure."""
    if args.solution:
        sln_path = repo_root / args.solution
        if not sln_path.exists():
            print(
                f"ERROR: Solution file not found: {sln_path}. "
                "Pass an existing path to --solution.",
                file=sys.stderr,
            )
            return None
        return sln_path
    try:
        return discover_solution(repo_root)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Auto-configure Stryker shards from a C# solution file",
    )
    parser.add_argument(
        "--repo-root",
        help="Repo root (defaults to the current working directory)",
    )
    parser.add_argument("--solution", help="Path to .sln file (relative to repo root)")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    parser.add_argument(
        "--update",
        action="store_true",
        help=f"Overwrite {PIPELINE_CONFIG_NAME} shards section",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()
    dry = args.dry_run

    sln_path = _resolve_solution(args, repo_root)
    if sln_path is None:
        return 1
    print(f"Solution: {_rel_to_root(sln_path, repo_root)}")

    all_projects = parse_projects(sln_path)
    if not all_projects:
        print(
            "ERROR: No .csproj entries found in the solution file.",
            file=sys.stderr,
        )
        return 1

    cfg = load_pipeline_config(repo_root)
    patterns = test_patterns(cfg)
    sources = [p for p in all_projects if not is_test_project(p["name"], patterns)]
    tests = [p for p in all_projects if is_test_project(p["name"], patterns)]

    print(f"\nClassified {len(all_projects)} projects:")
    print(f"  Source : {len(sources)}")
    print(f"  Test   : {len(tests)}")

    shards = build_shards(sources, tests, repo_root)

    print("\nShard configs:")
    for shard_slug, info in sorted(shards.items()):
        config_path = repo_root / f"stryker-config.shard-{shard_slug}.json"
        config_data = shard_config(info)
        content = json.dumps(config_data, indent=2) + "\n"
        test_count = len(config_data["stryker-config"]["test-projects"])
        mutate = config_data["stryker-config"]["mutate"][0]
        print(f"  {config_path.name:<45}  mutate={mutate}  tests={test_count}")
        if not dry:
            # Defense in depth against a hostile project name: never write a
            # shard config outside the repo root even if a slug slipped past
            # sanitization.
            if not _is_within(config_path, repo_root):
                print(
                    f"ERROR: refusing to write shard config outside repo root: "
                    f"{config_path.resolve()}",
                    file=sys.stderr,
                )
                return 1
            config_path.write_text(content, encoding="utf-8")

    stryker_sln_content = generate_stryker_sln(sources, tests, repo_root, sln_path)
    print(f"\nStryker.sln: {len(sources)} source + {len(tests)} test projects")
    if not dry:
        (repo_root / STRYKER_SLN_NAME).write_text(
            stryker_sln_content, encoding="utf-8"
        )

    pipeline_config = repo_root / PIPELINE_CONFIG_NAME
    if not pipeline_config.exists() or args.update:
        new_cfg = dict(cfg)
        new_cfg["solution"] = _rel_to_root(sln_path, repo_root)
        new_cfg["test_project_patterns"] = patterns
        new_cfg["shards"] = shards
        action = "Update" if pipeline_config.exists() else "Create"
        print(f"\n{action} {PIPELINE_CONFIG_NAME}")
        if not dry:
            pipeline_config.write_text(
                json.dumps(new_cfg, indent=2) + "\n", encoding="utf-8"
            )
    else:
        print(f"\n{PIPELINE_CONFIG_NAME} already exists — pass --update to overwrite")

    if dry:
        print("\n(dry-run) No files were written.")
    else:
        print("\nDone. Commit the generated files.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
