#!/usr/bin/env python3
"""scripts/install-java-static-analysis.py — install a pinned PMD distribution.

Stdlib-only (urllib.request, zipfile) so it runs unchanged on macOS, Linux,
and Windows — no curl, unzip, or Git Bash required (ADR 0014).
"""
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
            ["pmd", "--version"], capture_output=True, text=True
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
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(install_dir)

    bin_dir = install_dir / f"pmd-bin-{PMD_VERSION}" / "bin"
    # zipfile does not preserve the executable bit; restore it (no-op on Windows).
    for entry in bin_dir.iterdir():
        entry.chmod(entry.stat().st_mode | 0o755)

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
