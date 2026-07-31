#!/usr/bin/env python3
"""install-java-static-analysis.py — install a pinned PMD distribution.

Stdlib-only (urllib.request, zipfile) so it runs unchanged on macOS, Linux,
and Windows — no curl, unzip, or Git Bash required (ADR 0014).
"""
import hashlib
import hmac
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PMD_VERSION = "7.7.0"  # single source of truth for the pin; bump deliberately
                       # (check https://github.com/pmd/pmd/releases)
# SHA-256 of pmd-dist-7.7.0-bin.zip, pinned alongside the version above so the
# two can never drift apart — verified against the published GitHub release
# asset (curl the release URL below, then `shasum -a 256`). Bump together
# with PMD_VERSION.
PMD_SHA256 = "be8bf68f6c1d66984bd9645a93e631b78a1c2f42f5f0f8719082fead67553940"
if len(PMD_SHA256) != 64 or any(c not in "0123456789abcdef" for c in PMD_SHA256):
    # Fail loudly at import time, not at the end of a real download — a
    # malformed pin (wrong length, uppercase, stray whitespace) must never
    # silently degrade into "every install fails checksum" discovered only
    # in the field.
    raise ValueError(f"PMD_SHA256 is not a 64-char lowercase hex digest: {PMD_SHA256!r}")


def main() -> int:
    if shutil.which("java") is None:
        print("java (JDK/JRE) is required but not found.", file=sys.stderr)
        return 1
    # Repo-local by default (run from the repo root): per-repo version
    # reproducibility, no cross-repo version skew. Gitignored, never committed.
    install_dir = Path(
        os.environ.get("PMD_INSTALL_DIR", str(Path.cwd() / ".pmd"))
    )
    local_launcher = (
        install_dir / f"pmd-bin-{PMD_VERSION}" / "bin"
        / ("pmd.bat" if os.name == "nt" else "pmd")
    )
    if local_launcher.exists():
        print(f"pmd already installed: {local_launcher}")
        return 0
    if shutil.which("pmd") is not None:  # PATH fallback (env-override installs)
        version = subprocess.run(
            ["pmd", "--version"], capture_output=True, text=True, check=False
        ).stdout.strip()
        print(f"pmd already installed on PATH: {version}")
        return 0

    install_dir.mkdir(parents=True, exist_ok=True)
    archive = f"pmd-dist-{PMD_VERSION}-bin.zip"
    url = (
        "https://github.com/pmd/pmd/releases/download/"
        f"pmd_releases%2F{PMD_VERSION}/{archive}"
    )

    print(f"Downloading PMD {PMD_VERSION}...")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / archive
        urllib.request.urlretrieve(url, zip_path)

        digest = hashlib.sha256()
        with zip_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        if not hmac.compare_digest(digest.hexdigest(), PMD_SHA256.strip().lower()):
            print(
                f"Downloaded archive checksum mismatch: expected {PMD_SHA256}, "
                f"got {digest.hexdigest()}. Refusing to extract.",
                file=sys.stderr,
            )
            return 1

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(install_dir)

    bin_dir = install_dir / f"pmd-bin-{PMD_VERSION}" / "bin"
    # zipfile does not preserve the executable bit; restore it on the two
    # launchers only (no-op on Windows) rather than every extracted entry.
    for name in ("pmd", "pmd.bat"):
        launcher = bin_dir / name
        if launcher.exists():
            launcher.chmod(launcher.stat().st_mode | 0o755)

    print(f"PMD installed to {bin_dir}")
    print("No PATH change needed: detection probes the repo-local .pmd/ bin "
          "first, then falls back to PATH (per #811).")
    if "PMD_INSTALL_DIR" not in os.environ:
        gitignore = Path(".gitignore")
        if not (gitignore.exists() and ".pmd/" in gitignore.read_text()):
            print("Reminder: add `.pmd/` to this repo's .gitignore — the PMD "
                  "distribution is large and must never be committed.")
    launcher = bin_dir / ("pmd.bat" if os.name == "nt" else "pmd")
    subprocess.run([str(launcher), "--version"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
