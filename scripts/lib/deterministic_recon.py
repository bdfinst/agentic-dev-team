#!/usr/bin/env python3
"""deterministic_recon — structural reconnaissance without LLM.

Produces a recon envelope conforming (approximately) to
plugins/agentic-dev-team/knowledge/schemas/recon-envelope-v1.json by running
file-system and grep-based heuristics. This is a best-effort stand-in for
the codebase-recon agent when the plugin is not installed; it covers the
structural fields (repo metadata, languages, entry points, security surface
by grep) but produces empty `architecture.notable_anti_patterns` and thin
prose in `architecture.summary` since those need reasoning.

Usage:
    python3 scripts/lib/deterministic_recon.py <target-path> [<output-json>]

Emits JSON to stdout (or to <output-json> if given).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LANGUAGE_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go",
    ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby",
    ".rs": "Rust", ".php": "PHP", ".cs": "C#", ".scala": "Scala",
    ".swift": "Swift", ".sh": "Shell", ".bash": "Shell",
    ".sql": "SQL", ".yml": "YAML", ".yaml": "YAML",
}

ENTRY_POINT_SIGNALS = [
    # (pattern, kind)
    (re.compile(r"^#!/usr/bin/env (?:python3?|bash|sh)"), "cli"),
    (re.compile(r"if __name__ == ['\"]__main__['\"]:"), "cli"),
    (re.compile(r"app\.(listen|run)\s*\("), "http-server"),
    (re.compile(r"uvicorn\.run\s*\("), "http-server"),
    (re.compile(r"@app\.(get|post|put|delete|patch)\s*\("), "http-server"),
    (re.compile(r"@router\.(get|post|put|delete|patch)\s*\("), "http-server"),
    (re.compile(r"server\.listen\s*\("), "http-server"),
    (re.compile(r"exports\.handler\s*="), "lambda"),
]

SECURITY_SURFACE_PATTERNS = {
    "auth_paths": [
        re.compile(r"\b(login|logout|jwt\.sign|jwt\.verify|oauth|passport|authenticat|authoriz|session)\b", re.IGNORECASE),
    ],
    "network_egress": [
        re.compile(r"\b(fetch\(|axios\.|httpx\.|requests\.(get|post|put|delete)|http\.Get\(|URLSession|urllib\.request\.)"),
    ],
    "secrets_referenced": [
        re.compile(r"(process\.env\.[A-Z_]+|os\.environ(?:\.get)?(?:\[|\()|os\.getenv\(|ENV\[)"),
    ],
    "crypto_calls": [
        re.compile(r"\b(crypto\.|hashlib\.|bcrypt|scrypt|argon2|ed25519|AES\.new|Cipher\(|\.encrypt\(|\.decrypt\()"),
    ],
    "ml_models_loaded": [
        re.compile(r"\b(onnx\.load|pickle\.loads?|joblib\.load|torch\.load|AutoModel\.from_pretrained|SafeTensors\.load)\b"),
    ],
}

SENSITIVE_FILE_PATTERNS = [
    re.compile(r"\.env(\.[a-z]+)?$", re.IGNORECASE),
    re.compile(r"\.(pem|key|p12|pfx|crt)$", re.IGNORECASE),
    re.compile(r"credentials?", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"id_(rsa|ed25519|ecdsa|dsa)", re.IGNORECASE),
]


def detect_package_manager(root: Path) -> str:
    has = {
        "npm": (root / "package-lock.json").exists(),
        "pnpm": (root / "pnpm-lock.yaml").exists(),
        "yarn": (root / "yarn.lock").exists(),
        "poetry": (root / "poetry.lock").exists(),
        "pipenv": (root / "Pipfile.lock").exists(),
        "pip": (root / "requirements.txt").exists(),
        "go-modules": (root / "go.mod").exists(),
        "cargo": (root / "Cargo.lock").exists(),
        "maven": (root / "pom.xml").exists(),
        "gradle": (root / "build.gradle").exists() or (root / "build.gradle.kts").exists(),
    }
    present = [k for k, v in has.items() if v]
    if len(present) == 0:
        return "unknown"
    if len(present) == 1:
        return present[0]
    return "mixed"


def detect_monorepo(root: Path) -> tuple[bool, list[str]]:
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data.get("workspaces"), list):
                return True, [str(w) for w in data["workspaces"]]
            if isinstance(data.get("workspaces"), dict):
                packages = data["workspaces"].get("packages", [])
                return True, [str(w) for w in packages]
        except (json.JSONDecodeError, OSError):
            pass
    # Conventional monorepo shape — packages/ + apps/ + services/ dirs present
    has_ws_dirs = [(root / d).is_dir() for d in ("packages", "apps", "services")]
    if sum(has_ws_dirs) >= 1:
        # Not a formal monorepo but has workspace-like structure
        all_workspaces = []
        for d in ("packages", "apps", "services"):
            if (root / d).is_dir():
                for sub in (root / d).iterdir():
                    if sub.is_dir():
                        all_workspaces.append(f"{d}/{sub.name}")
        return bool(all_workspaces), all_workspaces
    return False, []


def walk_source_files(root: Path) -> list[Path]:
    """Walk the tree, skipping common junk directories."""
    skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__",
                 "dist", "build", ".tox", ".mypy_cache", ".ruff_cache",
                 "target", ".next", ".nuxt"}
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in skip_dirs for part in p.parts):
            continue
        out.append(p)
    return out


def enumerate_languages(files: list[Path]) -> list[dict]:
    counts: Counter[str] = Counter()
    for f in files:
        lang = LANGUAGE_BY_EXT.get(f.suffix.lower())
        if lang:
            counts[lang] += 1
    return [
        {"name": name, "file_count": count, "dominant_framework": None}
        for name, count in counts.most_common()
        if count >= 3
    ]


def identify_entry_points(files: list[Path], root: Path) -> list[dict]:
    out: list[dict] = []
    for f in files:
        if f.suffix.lower() not in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb", ".sh"}:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines[:200], start=1):  # check first 200 lines
            for pattern, kind in ENTRY_POINT_SIGNALS:
                if pattern.search(line):
                    rel = str(f.relative_to(root))
                    rationale = f"Pattern match at line {i}: {line.strip()[:80]}"
                    lang = LANGUAGE_BY_EXT.get(f.suffix.lower(), "unknown")
                    # Dedupe on path
                    if not any(ep["path"] == rel for ep in out):
                        out.append({
                            "path": rel,
                            "kind": kind,
                            "rationale": rationale,
                            "language": lang,
                        })
                    break  # one signal per file is enough
    # Package.json main
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            main = data.get("main")
            if main:
                rel = main.lstrip("./")
                if not any(ep["path"] == rel for ep in out):
                    out.append({
                        "path": rel,
                        "kind": "module-index",
                        "rationale": f"Listed as 'main' in package.json",
                        "language": "JavaScript/TypeScript",
                    })
        except (json.JSONDecodeError, OSError):
            pass
    return out


def identify_dependencies(root: Path) -> dict:
    deps: dict[str, list[str]] = {}

    # Python requirements.txt
    req = root / "requirements.txt"
    if req.exists():
        try:
            text = req.read_text(encoding="utf-8")
            pkgs = [line.split("==")[0].split(">=")[0].split("<=")[0].strip()
                    for line in text.splitlines()
                    if line.strip() and not line.strip().startswith("#")]
            _classify_deps(pkgs, deps)
        except OSError:
            pass

    # Node package.json
    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            pkgs = list((data.get("dependencies") or {}).keys())
            _classify_deps(pkgs, deps)
        except (json.JSONDecodeError, OSError):
            pass

    return deps


def _classify_deps(pkgs: list[str], deps: dict):
    """Heuristic classification of deps into web/data/crypto/auth/messaging/ml."""
    buckets = {
        "web": {"express", "fastapi", "flask", "django", "koa", "hapi", "starlette", "sanic", "bottle"},
        "data": {"sqlalchemy", "mongodb", "mongoose", "pg", "mysql2", "redis", "psycopg2", "pymongo", "cassandra-driver"},
        "crypto": {"pycryptodome", "cryptography", "bcrypt", "argon2", "scrypt", "jsonwebtoken", "jose"},
        "auth": {"passport", "pyjwt", "python-jose", "authlib", "jsonwebtoken", "oauth2"},
        "messaging": {"nats-py", "aio-pika", "kafka-python", "pika", "amqplib"},
        "ml": {"onnx", "torch", "tensorflow", "scikit-learn", "joblib", "safetensors"},
    }
    for pkg in pkgs:
        pkg_lower = pkg.lower()
        for bucket, names in buckets.items():
            if pkg_lower in names or any(pkg_lower.startswith(n) for n in names):
                deps.setdefault(bucket, []).append(pkg)
                break
        else:
            deps.setdefault("other_notable", []).append(pkg)


def grep_security_surface(files: list[Path], root: Path) -> dict:
    out: dict[str, list[str]] = {k: [] for k in SECURITY_SURFACE_PATTERNS}
    out["csp_headers"] = []
    for f in files:
        if f.suffix.lower() not in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb"}:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(root))
        for kind, patterns in SECURITY_SURFACE_PATTERNS.items():
            if any(p.search(text) for p in patterns):
                if rel not in out[kind]:
                    out[kind].append(rel)
    return out


def probe_git_history(root: Path) -> dict:
    out: dict[str, Any] = {
        "branches": {"current": "", "main_count": 0, "feature_count": 0, "names": []},
        "recent_activity": {"last_commit_date": "1970-01-01T00:00:00Z", "commits_last_30d": 0, "authors_last_30d": 0},
        "sensitive_file_history": [],
    }
    if not (root / ".git").exists():
        return out

    try:
        branches = subprocess.run(["git", "-C", str(root), "branch", "--list"],
                                  capture_output=True, text=True, timeout=10).stdout.splitlines()
        branch_names = [b.strip().lstrip("* ") for b in branches]
        current = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        out["branches"]["current"] = current
        out["branches"]["names"] = branch_names[:20]
        out["branches"]["main_count"] = sum(1 for b in branch_names if b in ("main", "master", "develop"))
        out["branches"]["feature_count"] = max(0, len(branch_names) - out["branches"]["main_count"])

        last = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%cI"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
        if last:
            out["recent_activity"]["last_commit_date"] = last

        commits = subprocess.run(
            ["git", "-C", str(root), "log", "--since=30 days ago", "--oneline"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        authors = subprocess.run(
            ["git", "-C", str(root), "log", "--since=30 days ago", "--format=%ae"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        out["recent_activity"]["commits_last_30d"] = len(commits)
        out["recent_activity"]["authors_last_30d"] = len(set(a for a in authors if a))

        # Sensitive file history — files ever touched
        tree_files = subprocess.run(
            ["git", "-C", str(root), "log", "--all", "--name-only", "--format="],
            capture_output=True, text=True, timeout=30,
        ).stdout.splitlines()
        for path in set(p for p in tree_files if p):
            for pattern in SENSITIVE_FILE_PATTERNS:
                if pattern.search(path):
                    in_tree = (root / path).exists()
                    out["sensitive_file_history"].append({
                        "path": path,
                        "in_current_tree": in_tree,
                        "appeared_in_history": True,
                        "first_seen_commit": None,
                        "removed_commit": None,
                    })
                    break
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        pass
    return out


def build_architecture(files: list[Path], root: Path) -> dict:
    """Identify layers from directory naming. Summary is thin without LLM."""
    known_layers = ["domain", "core", "adapters", "infrastructure", "ports",
                    "handlers", "routes", "services", "repositories", "models",
                    "controllers", "views", "backend", "frontend", "api", "worker"]
    layer_files: dict[str, list[str]] = {}
    for f in files:
        for layer in known_layers:
            if f"/{layer}/" in str(f) or str(f).startswith(f"{layer}/"):
                rel_dir = str(f.parent.relative_to(root))
                layer_files.setdefault(layer, [])
                if rel_dir not in layer_files[layer]:
                    layer_files[layer].append(rel_dir)
                break

    layers = [
        {"name": k, "paths": sorted(set(v))[:5], "purpose": ""}
        for k, v in layer_files.items() if len(v) >= 1
    ]

    # Summary is deterministic but thin
    summary_parts = []
    if layers:
        layer_names = [l["name"] for l in layers]
        summary_parts.append(f"Code organized into {len(layers)} identifiable layer(s): {', '.join(layer_names)}.")
    else:
        summary_parts.append("No conventional layer structure detected.")

    return {
        "summary": " ".join(summary_parts) + " [Deterministic recon — LLM narrative skipped.]",
        "layers": layers,
        "notable_anti_patterns": [],  # Requires LLM
    }


def build_recon(root: Path) -> dict:
    root = root.resolve()
    files = walk_source_files(root)
    monorepo, workspaces = detect_monorepo(root)

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repo": {
            "name": root.name,
            "root": str(root),
            "package_manager": detect_package_manager(root),
            "monorepo": monorepo,
            "workspaces": workspaces,
            "vcs": {
                "kind": "git" if (root / ".git").exists() else "none",
                "remote_host": None,
                "default_branch": None,
            },
        },
        "entry_points": identify_entry_points(files, root),
        "languages": enumerate_languages(files),
        "dependencies": identify_dependencies(root),
        "architecture": build_architecture(files, root),
        "security_surface": grep_security_surface(files, root),
        "git_history": probe_git_history(root),
        "notes": ["Deterministic recon produced by scripts/lib/deterministic_recon.py. No LLM reasoning applied; semantic fields (architecture.summary prose, notable_anti_patterns) are omitted or minimal."],
    }


def main() -> int:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("usage: deterministic_recon.py <target-path> [<output-json>]", file=sys.stderr)
        return 2

    target = Path(sys.argv[1])
    if not target.is_dir():
        print(f"error: target is not a directory: {target}", file=sys.stderr)
        return 2

    recon = build_recon(target)

    if len(sys.argv) == 3:
        out_path = Path(sys.argv[2])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            json.dump(recon, f, indent=2)
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        json.dump(recon, sys.stdout, indent=2)
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
