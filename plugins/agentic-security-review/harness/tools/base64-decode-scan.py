#!/usr/bin/env python3
"""base64-decode-scan — find base64-encoded credentials in a source tree.

Walks a target directory for text files, extracts quoted base64-pattern
strings, attempts to decode them, and flags decodings that look like
credentials (password-pattern keywords, AWS key prefix, or high entropy).

Emits SARIF 2.1.0. Default target is stdout; --output writes to a file.

Usage:
    base64-decode-scan.py <target-dir>
    base64-decode-scan.py <target-dir> --output findings.sarif
    base64-decode-scan.py <target-dir> --dry-run

Exit codes:
    0  — scan complete, no findings
    1  — scan complete, one or more findings emitted
    2  — argument or IO error
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__"}
SKIP_SUFFIXES = {".pyc", ".class"}
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
BINARY_SNIFF_BYTES = 512

# Quoted base64-pattern strings: length >= 8 of [A-Za-z0-9_+/], with 0–2 '=' padding
B64_STRING_PATTERN = re.compile(r"""['"]([\w+/]{8,}={0,2})['"]""")

PASSWORD_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|key|token|credential|api_key)"
)
AWS_KEY_PATTERN = re.compile(r"AKIA[0-9A-Z]{16}")

ENTROPY_THRESHOLD = 3.5
MIN_DECODED_LEN = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_binary(path: Path) -> bool:
    """Return True if the first BINARY_SNIFF_BYTES don't decode as UTF-8."""
    try:
        with path.open("rb") as f:
            chunk = f.read(BINARY_SNIFF_BYTES)
    except OSError:
        return True
    if b"\x00" in chunk:
        return True
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES


def should_skip_file(path: Path) -> bool:
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def is_printable_ascii(text: str) -> bool:
    return all(32 <= ord(c) < 127 or c in "\t\n\r" for c in text)


def walk_files(root: Path):
    """Yield candidate files under root, skipping binaries and excluded dirs."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if should_skip_dir(entry.name):
                        continue
                    stack.append(entry)
                    continue
                if not entry.is_file():
                    continue
            except OSError:
                continue
            if should_skip_file(entry):
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                print(
                    f"base64-decode-scan: skipping {entry} ({size} bytes > 5MB limit)",
                    file=sys.stderr,
                )
                continue
            if is_binary(entry):
                continue
            yield entry


def scan_file(path: Path) -> list[dict]:
    """Return a list of finding dicts for a single file."""
    findings: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings

    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in B64_STRING_PATTERN.finditer(line):
            encoded = match.group(1)
            try:
                decoded_bytes = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                continue
            try:
                decoded = decoded_bytes.decode("ascii")
            except UnicodeDecodeError:
                # Still check entropy on raw bytes
                entropy = shannon_entropy(decoded_bytes)
                if len(decoded_bytes) >= MIN_DECODED_LEN and entropy > ENTROPY_THRESHOLD:
                    findings.append(
                        _finding(
                            path,
                            lineno,
                            encoded,
                            decoded_bytes.hex()[:8],
                            f"high-entropy ({entropy:.2f})",
                        )
                    )
                continue

            if len(decoded) < MIN_DECODED_LEN or not is_printable_ascii(decoded):
                continue

            matched_pattern: str | None = None
            if PASSWORD_PATTERN.search(decoded):
                matched_pattern = "password-keyword"
            elif AWS_KEY_PATTERN.search(decoded):
                matched_pattern = "AWS access key"
            else:
                entropy = shannon_entropy(decoded_bytes)
                if entropy > ENTROPY_THRESHOLD:
                    matched_pattern = f"high-entropy ({entropy:.2f})"

            if matched_pattern is None:
                continue

            findings.append(_finding(path, lineno, encoded, decoded, matched_pattern))

    return findings


def _finding(
    path: Path, lineno: int, encoded: str, decoded: str, pattern_label: str
) -> dict:
    preview_encoded = encoded[:8]
    preview_decoded = decoded[:4] if isinstance(decoded, str) else decoded
    return {
        "ruleId": "secrets.base64-encoded-credential",
        "level": "warning",
        "message": {
            "text": (
                f"Possible base64-encoded credential: decoded value matches "
                f"{pattern_label} (original: {preview_encoded}...)"
            )
        },
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": path.as_uri()},
                    "region": {"startLine": lineno},
                }
            }
        ],
        "properties": {
            "cwe": "CWE-798",
            "original_encoded": f"{preview_encoded}...",
            "decoded_preview": f"{preview_decoded}...",
        },
    }


def build_sarif(findings: list[dict]) -> dict:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "base64-decode-scan",
                        "version": "1.0.0",
                        "informationUri": "https://github.com/bdfinst/agentic-dev-team",
                        "rules": [
                            {
                                "id": "secrets.base64-encoded-credential",
                                "shortDescription": {
                                    "text": "Base64-encoded value decodes to a probable credential"
                                },
                                "helpUri": "https://cwe.mitre.org/data/definitions/798.html",
                            }
                        ],
                    }
                },
                "results": findings,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Directory to scan.")
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write SARIF output (default: stdout).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print a count of candidate findings without emitting SARIF.",
    )
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists() or not target.is_dir():
        print(
            f"base64-decode-scan: target is not a directory: {args.target}",
            file=sys.stderr,
        )
        return 2

    all_findings: list[dict] = []
    for path in walk_files(target):
        all_findings.extend(scan_file(path))

    if args.dry_run:
        print(f"base64-decode-scan: {len(all_findings)} candidate finding(s)")
        return 1 if all_findings else 0

    sarif = build_sarif(all_findings)
    payload = json.dumps(sarif, indent=2)

    if args.output:
        try:
            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"base64-decode-scan: cannot write output: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(payload)
        sys.stdout.write("\n")

    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
