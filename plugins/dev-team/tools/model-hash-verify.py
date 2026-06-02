#!/usr/bin/env python3
"""model-hash-verify — ML model integrity + provenance checker.

Walks a target path for ML model files and verifies each against one of:
  1. A sidecar .sha256 file (same basename + ".sha256" extension).
  2. A top-level models.manifest.json mapping `{ "<path>": "<sha256>" }`.

If a model has neither source of truth, emits a "no-provenance" finding.
If a model's computed hash differs from its declared hash, emits an
"integrity-failure" finding.

Matched file extensions:
    .onnx .safetensors .pt .pth .pkl .joblib .h5 .tflite .gguf .bin

Emits SARIF 2.1.0 on stdout. Shipped alongside the SARIF-first baseline;
the shared parser consumes its output unchanged.

Usage:
    model-hash-verify.py <path> [<path> ...]
    model-hash-verify.py --manifest <manifest.json> <path>
    model-hash-verify.py --help

Exit codes:
    0   successful scan (findings reported via SARIF).
    2   argument or IO error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

MODEL_EXTENSIONS = {
    ".onnx", ".safetensors", ".pt", ".pth", ".pkl", ".joblib",
    ".h5", ".tflite", ".gguf", ".bin",
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    file: str
    line: int
    message: str


def compute_sha256(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def read_sidecar_hash(model_path: Path) -> str | None:
    sidecar = model_path.with_suffix(model_path.suffix + ".sha256")
    if not sidecar.exists():
        return None
    # Either "HASH" or "HASH  filename" shapes
    first = sidecar.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    if not first:
        return None
    return first[0].split()[0].strip().lower()


def load_manifest(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a JSON object of path->sha256")
    return {str(k): str(v).strip().lower() for k, v in raw.items()}


def is_model_file(path: Path) -> bool:
    return path.suffix.lower() in MODEL_EXTENSIONS


def discover_models(targets: list[str]) -> list[Path]:
    out: list[Path] = []
    for t in targets:
        p = Path(t)
        if not p.exists():
            print(f"model-hash-verify: path not found: {t}", file=sys.stderr)
            continue
        if p.is_file() and is_model_file(p):
            out.append(p)
        elif p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file() and is_model_file(sub):
                    out.append(sub)
    return out


def verify_models(models: list[Path], manifest: dict[str, str] | None) -> list[Finding]:
    findings: list[Finding] = []
    for model in models:
        actual = compute_sha256(model)

        sidecar = read_sidecar_hash(model)
        manifest_declared = None
        if manifest:
            key = str(model)
            manifest_declared = manifest.get(key) or manifest.get(model.name)

        declared = sidecar or manifest_declared

        if declared is None:
            findings.append(Finding(
                rule_id="no-provenance",
                severity="warning",
                file=str(model),
                line=1,
                message=(
                    f"Model {model.name} has no hash declaration (no sidecar "
                    f"{model.name}.sha256 and not in manifest). Actual SHA-256: "
                    f"{actual[:12]}..."
                ),
            ))
            continue

        if declared.lower() != actual.lower():
            findings.append(Finding(
                rule_id="integrity-failure",
                severity="error",
                file=str(model),
                line=1,
                message=(
                    f"Model {model.name} hash mismatch. Declared: "
                    f"{declared[:12]}... Actual: {actual[:12]}... "
                    f"(model has been modified since declaration)."
                ),
            ))
    return findings


def sarif_from_findings(findings: list[Finding]) -> dict:
    rules = {
        "no-provenance": "Model file has no declared hash (sidecar or manifest)",
        "integrity-failure": "Model file hash does not match declared value",
    }
    rule_order = list(rules.keys())

    def rule_index(rule_id: str) -> int:
        return rule_order.index(rule_id) if rule_id in rule_order else 0

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "model-hash-verify",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/bdfinst/agentic-dev-team",
                        "rules": [
                            {"id": rid, "shortDescription": {"text": text}}
                            for rid, text in rules.items()
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": f.rule_id,
                        "ruleIndex": rule_index(f.rule_id),
                        "level": f.severity,
                        "message": {"text": f.message},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": f.file},
                                    "region": {"startLine": f.line},
                                }
                            }
                        ],
                    }
                    for f in findings
                ],
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("paths", nargs="+", help="Files or directories to scan.")
    parser.add_argument("--manifest", type=Path, help="Optional manifest.json mapping path -> sha256.")
    args = parser.parse_args()

    manifest: dict[str, str] | None = None
    if args.manifest:
        if not args.manifest.exists():
            print(f"model-hash-verify: manifest not found: {args.manifest}", file=sys.stderr)
            return 2
        try:
            manifest = load_manifest(args.manifest)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"model-hash-verify: manifest is invalid: {e}", file=sys.stderr)
            return 2

    models = discover_models(args.paths)
    findings = verify_models(models, manifest)
    json.dump(sarif_from_findings(findings), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
