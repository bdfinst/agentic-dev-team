#!/usr/bin/env python3
"""codebase_recon.py — seven-step codebase reconnaissance harness.

Orchestrates deterministic steps (via deterministic_recon.py) and optional
LLM steps (via `claude -p`) into a schema-validated RECON envelope, then
writes it atomically to the output directory.

Usage:
    python3 scripts/codebase_recon.py <repo-root> [--output-dir <path>]
                                                   [--skip-llm]
                                                   [--inventory-script <path>]

Exit codes:
    0 = pass (artifact written successfully)
    1 = errors (schema failure, inventory failure, etc.)
    2 = warnings
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Allow importing sibling lib modules regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))
from lib.review_result import build_result, main_exit, skipped_llm_warning
from lib import deterministic_recon

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

_SCHEMA_PATH = (
    Path(__file__).parent.parent
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "schemas"
    / "recon-envelope-v1.json"
)


def _load_schema() -> dict:
    """Load the recon envelope schema from disk."""
    with _SCHEMA_PATH.open() as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Step 1: Discover metadata
# ---------------------------------------------------------------------------


def step1_discover_metadata(root: Path) -> dict:
    """Call build_recon() once; all deterministic steps share this result."""
    return deterministic_recon.build_recon(root)


# ---------------------------------------------------------------------------
# Step 2: Enumerate languages
# ---------------------------------------------------------------------------


def step2_enumerate_languages(root: Path, meta: dict) -> list[dict]:
    """Extract language stats from the meta dict produced in step 1."""
    return meta.get("languages", [])


# ---------------------------------------------------------------------------
# Step 3: Identify entry points (LLM or stub)
# ---------------------------------------------------------------------------


def step3_entry_points(
    root: Path, lang_stats: list[dict], skip_llm: bool = False
) -> list[dict]:
    """Identify entry points via LLM or return deterministic stub."""
    if skip_llm:
        # Return an empty list — the schema requires no minimum items.
        # The run() orchestrator will replace this with deterministic entry points
        # from meta if any were found, so no placeholder object is needed.
        return []

    # LLM path: call `claude -p`
    lang_summary = ", ".join(l.get("name", "?") for l in lang_stats[:5]) or "unknown"
    prompt = (
        f"Analyze the repository at {root}. "
        f"Primary languages: {lang_summary}. "
        "List the top entry points as JSON array with objects having: "
        "path (repo-relative), kind (cli|http-server|worker|lambda|cron|test-runner|build-tool|module-index|other), "
        "rationale (string), language (string or null). "
        "Respond with ONLY the JSON array."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, list):
                return data
    except (
        subprocess.SubprocessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        FileNotFoundError,
    ):
        pass
    # Fall back to placeholder on any error
    return [
        {
            "path": ".",
            "kind": "other",
            "rationale": "LLM call failed or unavailable; placeholder only.",
            "language": None,
        }
    ]


# ---------------------------------------------------------------------------
# Step 4: Map architecture (LLM or stub)
# ---------------------------------------------------------------------------


def step4_architecture(
    root: Path, entry_points: list[dict], skip_llm: bool = False
) -> dict:
    """Map architecture via LLM or return deterministic stub from meta."""
    if skip_llm:
        # Return a minimal architecture that satisfies the schema
        return {
            "summary": "[--skip-llm] Architecture mapping skipped; deterministic stub.",
            "layers": [],
            "notable_anti_patterns": [],
        }

    ep_summary = ", ".join(e.get("path", "?") for e in entry_points[:5]) or "unknown"
    prompt = (
        f"Analyze the repository at {root}. "
        f"Known entry points: {ep_summary}. "
        "Describe the architecture as JSON with: "
        "summary (2-4 sentences), "
        "layers (array of objects with name, paths[], purpose), "
        "notable_anti_patterns (array of strings). "
        "Respond with ONLY the JSON object."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                data.setdefault("summary", "")
                data.setdefault("layers", [])
                data.setdefault("notable_anti_patterns", [])
                return data
    except (
        subprocess.SubprocessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        FileNotFoundError,
    ):
        pass
    return {
        "summary": "LLM call failed or unavailable; architecture mapping incomplete.",
        "layers": [],
        "notable_anti_patterns": [],
    }


# ---------------------------------------------------------------------------
# Step 5: Scan security surface (LLM or stub)
# ---------------------------------------------------------------------------


def step5_security_surface(
    root: Path, architecture: dict, skip_llm: bool = False
) -> dict:
    """Scan security surface via LLM or return deterministic stub from meta."""
    if skip_llm:
        return {
            "auth_paths": [],
            "network_egress": [],
            "secrets_referenced": [],
            "crypto_calls": [],
            "ml_models_loaded": [],
            "csp_headers": [],
        }

    arch_summary = architecture.get("summary", "")
    prompt = (
        f"Analyze the repository at {root}. "
        f"Architecture: {arch_summary[:200]}. "
        "Report the security surface as JSON with arrays: "
        "auth_paths, network_egress, secrets_referenced, crypto_calls, "
        "ml_models_loaded, csp_headers. "
        "Each element is a repo-relative file path. "
        "Respond with ONLY the JSON object."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            if isinstance(data, dict):
                for key in (
                    "auth_paths",
                    "network_egress",
                    "secrets_referenced",
                    "crypto_calls",
                    "ml_models_loaded",
                    "csp_headers",
                ):
                    data.setdefault(key, [])
                return data
    except (
        subprocess.SubprocessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        FileNotFoundError,
    ):
        pass
    return {
        "auth_paths": [],
        "network_egress": [],
        "secrets_referenced": [],
        "crypto_calls": [],
        "ml_models_loaded": [],
        "csp_headers": [],
    }


# ---------------------------------------------------------------------------
# Step 6: Probe git history
# ---------------------------------------------------------------------------


def step6_git_history(root: Path, meta: dict) -> dict:
    """Extract git history from the meta dict produced in step 1."""
    return meta.get(
        "git_history",
        {
            "branches": {
                "current": "",
                "main_count": 0,
                "feature_count": 0,
                "names": [],
            },
            "recent_activity": {
                "last_commit_date": "1970-01-01T00:00:00Z",
                "commits_last_30d": 0,
                "authors_last_30d": 0,
            },
            "sensitive_file_history": [],
        },
    )


# ---------------------------------------------------------------------------
# Step 7: Inventory + validate + emit atomically
# ---------------------------------------------------------------------------


def _derive_slug(root: Path) -> str:
    """Derive slug from repo root dir name: lowercase, kebab-safe."""
    import re

    name = root.resolve().name.lower()
    name = re.sub(r"[^a-z0-9._-]", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip("-")
    return name or "repo"


def validate_schema(artifact: dict) -> None:
    """Validate artifact against the recon-envelope-v1 schema.

    Raises jsonschema.ValidationError on failure.
    """
    import jsonschema

    schema = _load_schema()
    jsonschema.validate(instance=artifact, schema=schema)


def write_atomically(path: Path, data: dict) -> None:
    """Write JSON data to path atomically via a temp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(str(tmp_path), str(path))
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def step7_emit(
    root: Path,
    output_dir: Path,
    meta: dict,
    lang_stats: list[dict],
    entry_points: list[dict],
    architecture: dict,
    security: dict,
    history: dict,
    inventory_script: Path | None = None,
) -> tuple[bool, list[dict]]:
    """Run recon_inventory.py, validate schema, write artifact atomically.

    Returns (success: bool, errors: list[dict]).
    """
    errors: list[dict] = []

    # Resolve inventory script path
    if inventory_script is None:
        # Default: look for recon_inventory.py relative to plugin scripts
        inventory_script = (
            Path(__file__).parent.parent
            / "plugins"
            / "dev-team"
            / "scripts"
            / "recon_inventory.py"
        )

    slug = _derive_slug(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / f"recon-{slug}.json"

    # Run recon_inventory.py
    inventory_result = subprocess.run(
        [sys.executable, str(inventory_script), str(root), "--slug", slug],
        capture_output=True,
        text=True,
    )
    if inventory_result.returncode != 0:
        errors.append(
            {
                "severity": "error",
                "confidence": "high",
                "file": "",
                "line": 0,
                "message": f"recon_inventory.py failed (exit {inventory_result.returncode}): {inventory_result.stderr.strip()[:500]}",
                "suggestedFix": "Check that recon_inventory.py is executable and the repo root is valid.",
            }
        )
        return False, errors

    # Assemble artifact from all steps
    artifact: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": meta.get("generated_at", ""),
        "repo": meta.get("repo", {}),
        "entry_points": entry_points,
        "languages": lang_stats,
        "dependencies": meta.get("dependencies", {}),
        "architecture": architecture,
        "security_surface": security,
        "git_history": history,
        "notes": meta.get("notes", []),
    }

    # Schema validation
    try:
        validate_schema(artifact)
    except Exception as exc:
        errors.append(
            {
                "severity": "error",
                "confidence": "high",
                "file": "",
                "line": 0,
                "message": f"Schema validation failed: {exc}",
                "suggestedFix": "Ensure all required fields are present and correctly typed.",
            }
        )
        return False, errors

    # Atomic write
    write_atomically(artifact_path, artifact)
    return True, []


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run(
    root: Path,
    output_dir: Path,
    skip_llm: bool = False,
    inventory_script: Path | None = None,
) -> int:
    """Run all seven steps in sequence; return exit code."""
    warnings: list[dict] = []

    # Step 1: discover metadata (single build_recon call used by steps 2, 6 too)
    meta = step1_discover_metadata(root)

    # Step 2: enumerate languages
    lang_stats = step2_enumerate_languages(root, meta)

    # Step 3: entry points
    entry_points = step3_entry_points(root, lang_stats, skip_llm=skip_llm)

    # Step 4: architecture
    architecture = step4_architecture(root, entry_points, skip_llm=skip_llm)

    # Step 5: security surface
    security = step5_security_surface(root, architecture, skip_llm=skip_llm)

    # Step 6: git history
    history = step6_git_history(root, meta)

    # Augment architecture from deterministic data if LLM skipped/failed
    if skip_llm:
        # Merge deterministic architecture layers into the stub
        det_arch = meta.get("architecture", {})
        if det_arch.get("layers"):
            architecture["layers"] = det_arch["layers"]
        if det_arch.get("summary") and architecture["summary"].startswith(
            "[--skip-llm]"
        ):
            architecture["summary"] = det_arch["summary"]

    # Augment security surface from deterministic grep data if LLM skipped
    if skip_llm:
        det_sec = meta.get("security_surface", {})
        for key in (
            "auth_paths",
            "network_egress",
            "secrets_referenced",
            "crypto_calls",
            "ml_models_loaded",
            "csp_headers",
        ):
            if det_sec.get(key):
                security[key] = det_sec[key]

    # Augment entry points from deterministic data if LLM skipped
    if skip_llm:
        det_ep = meta.get("entry_points", [])
        if det_ep:
            # Replace placeholder with deterministic entry points
            entry_points = det_ep

    # Step 7: inventory + emit
    success, errors = step7_emit(
        root=root,
        output_dir=output_dir,
        meta=meta,
        lang_stats=lang_stats,
        entry_points=entry_points,
        architecture=architecture,
        security=security,
        history=history,
        inventory_script=inventory_script,
    )

    if not success:
        result = build_result(errors, warnings)
        return main_exit(result)

    result = build_result([], warnings, summary=f"RECON written to {output_dir}")
    return main_exit(result)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Codebase reconnaissance harness — seven-step RECON envelope producer.",
    )
    parser.add_argument("repo_root", help="Path to the repository root to scan.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write artifacts (default: memory/recon-<slug>/ relative to CWD).",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM steps 3/4/5; use deterministic data only.",
    )
    parser.add_argument(
        "--inventory-script",
        default=None,
        help="Path to recon_inventory.py (for testing with a fake script).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        print(f"error: repo-root is not a directory: {root}", file=sys.stderr)
        return 2

    # Derive default output dir from CWD + slug
    if args.output_dir is None:
        import re

        name = root.name.lower()
        name = re.sub(r"[^a-z0-9._-]", "-", name)
        name = re.sub(r"-{2,}", "-", name)
        name = name.strip("-") or "repo"
        output_dir = Path.cwd() / "memory" / f"recon-{name}"
    else:
        output_dir = Path(args.output_dir)

    inventory_script = Path(args.inventory_script) if args.inventory_script else None

    return run(
        root=root,
        output_dir=output_dir,
        skip_llm=args.skip_llm,
        inventory_script=inventory_script,
    )


if __name__ == "__main__":
    sys.exit(main())
