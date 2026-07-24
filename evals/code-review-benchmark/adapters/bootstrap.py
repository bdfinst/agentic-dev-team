"""Auto-provisioning of the Defects4J and BugsJS/bug-dataset homes (#949).

`cli.py` used to require the operator to have already cloned/configured
both dataset homes themselves (`--defects4j-home`/`DEFECTS4J_HOME`,
`--bugsjs-home`/`BUGSJS_HOME`). This module clones (and, for Defects4J,
initializes) whichever home is missing into a repo-local, gitignored cache
(`evals/code-review-benchmark/.cache/`) — so a bare `cli.py --dataset ...`
just works.

Both `ensure_*_home()` functions are no-ops (return the given path
unchanged) when the caller already passed an explicit home — auto-
provisioning only kicks in when nothing was specified, so an explicit but
misconfigured path still fails loudly via the adapter's own `detect()`
rather than being silently overridden.

Never raises — every failure mode (clone, `init.sh`) is caught and folded
into a `None` return, matching every adapter's fail-loudly-and-skip
contract.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .common import run_with_timeout

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
DEFECTS4J_REPO_URL = "https://github.com/rjust/defects4j.git"
BUGSJS_REPO_URL = "https://github.com/BugsJS/bug-dataset.git"
_DEFECTS4J_INIT_MARKER = ".d4j-init-complete"

DEFAULT_RUN_FN = run_with_timeout

# Module-level so tests can monkeypatch it to a nonexistent path and force
# the "not on this machine" branch deterministically, rather than depending
# on whether the real macOS tool happens to exist on whatever host runs the
# suite (#951 — hermetic tests, not host-environment-dependent ones).
JAVA_HOME_TOOL = "/usr/libexec/java_home"


def _clone_if_missing(
    repo_url: str,
    dest: Path,
    run_fn=DEFAULT_RUN_FN,
    timeout: int = 600,
) -> bool:
    """`git clone repo_url dest` unless `dest` already looks populated."""
    if dest.is_dir() and any(dest.iterdir()):
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = run_fn(
            timeout,
            ["git", "clone", repo_url, str(dest)],
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return False
    return proc.returncode == 0


def _resolve_java11_home(run_fn=DEFAULT_RUN_FN, timeout: int = 10) -> str | None:
    """Best-effort discovery of a Java 11 JDK's home (#951).

    Defects4J 3.x requires exactly Java 11 — on a machine whose default
    `java` is newer (or missing entirely), every `defects4j` subprocess
    call fails with an opaque Perl error. This never touches the caller's
    own `JAVA_HOME`/`PATH`; it only *discovers* a path for
    `build_defects4j_env()` to scope onto the subprocess env it builds.

    Tries `/usr/libexec/java_home -v 11` first (macOS — only finds JDKs
    registered under `/Library/Java/JavaVirtualMachines/`), then `brew
    --prefix openjdk@11` (the common case for a keg-only Homebrew install,
    which deliberately isn't registered there). Returns `None` if neither
    resolves — the caller then falls back to the inherited environment.
    """
    if Path(JAVA_HOME_TOOL).is_file():
        try:
            proc = run_fn(
                timeout,
                [JAVA_HOME_TOOL, "-v", "11"],
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except (OSError, ValueError):
            pass

    if shutil.which("brew") is None:
        return None
    try:
        proc = run_fn(
            timeout, ["brew", "--prefix", "openjdk@11"], capture_output=True, text=True
        )
    except (OSError, ValueError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    prefix = Path(proc.stdout.strip())
    mac_home = prefix / "libexec" / "openjdk.jdk" / "Contents" / "Home"
    return str(mac_home) if mac_home.is_dir() else str(prefix)


def _resolve_perl5lib(home: Path | None = None) -> str | None:
    """`~/perl5/lib/perl5` — the `cpanm --local-lib=~/perl5` convention for
    installing Defects4J's own CPAN dependencies (see its `cpanfile`)
    without a system-wide Perl module install."""
    candidate = (home or Path.home()) / "perl5" / "lib" / "perl5"
    return str(candidate) if candidate.is_dir() else None


def build_defects4j_env(
    run_fn=DEFAULT_RUN_FN, perl5_home: Path | None = None
) -> dict[str, str] | None:
    """Merge `JAVA_HOME`/`PATH`/`PERL5LIB` overrides into a copy of the
    current environment, scoped to `defects4j` subprocess calls only.

    Never mutates this process's own environment or the user's shell
    profile — every override is discovery-only (#951). Returns `None`
    (meaning "inherit unchanged") when nothing needed overriding, so
    callers can pass the result straight through as `env=` without a
    conditional. `perl5_home` overrides `_resolve_perl5lib()`'s search root
    (defaults to the real `Path.home()`) — mainly so tests don't depend on
    whatever happens to exist under the real user's home directory.
    """
    java_home = _resolve_java11_home(run_fn=run_fn)
    perl5lib = _resolve_perl5lib(home=perl5_home)
    if java_home is None and perl5lib is None:
        return None

    env = dict(os.environ)
    if java_home is not None:
        env["JAVA_HOME"] = java_home
        env["PATH"] = f"{java_home}/bin:{env.get('PATH', '')}"
    if perl5lib is not None:
        existing = env.get("PERL5LIB")
        env["PERL5LIB"] = f"{perl5lib}:{existing}" if existing else perl5lib
    return env


def ensure_bugsjs_home(
    explicit_home: str | None,
    run_fn=DEFAULT_RUN_FN,
    cache_dir: Path = CACHE_DIR,
) -> str | None:
    """Return a usable BugsJS/bug-dataset home, cloning into the cache if none was given."""
    if explicit_home:
        return explicit_home
    dest = cache_dir / "bugsjs-bug-dataset"
    if not _clone_if_missing(BUGSJS_REPO_URL, dest, run_fn=run_fn):
        return None
    return str(dest)


def ensure_defects4j_home(
    explicit_home: str | None,
    run_fn=DEFAULT_RUN_FN,
    init_timeout: int = 1800,
    cache_dir: Path = CACHE_DIR,
    perl5_home: Path | None = None,
) -> dict[str, Any] | None:
    """Return `{"home": str, "bin": str, "env": Optional[dict]}` for a usable
    Defects4J install.

    When `explicit_home` is given, returns it unchanged with `bin` set to
    the bare `"defects4j"` command name (today's PATH-based lookup) and
    `env: None` (inherit unchanged) — no auto-clone or env resolution over
    an explicit path; assumes the operator already configured their own
    environment. Otherwise clones `rjust/defects4j` into the cache and
    runs its `init.sh` once (skipped on later calls via a marker file —
    `init.sh` is slow and network-heavy), then resolves `env` via
    `build_defects4j_env()` (#951 — Java 11 + Perl CPAN deps discovery).
    The resolved `bin` is always the cache clone's own
    `framework/bin/defects4j` (a committed, already-executable script — no
    build step), never a PATH lookup, since Defects4J needs its project
    repos bootstrapped under *this specific* home directory regardless of
    any other system-wide install.
    """
    if explicit_home:
        return {"home": explicit_home, "bin": "defects4j", "env": None}

    dest = cache_dir / "defects4j"
    if not (dest / "framework" / "projects").is_dir():
        if not _clone_if_missing(DEFECTS4J_REPO_URL, dest, run_fn=run_fn):
            return None

    env = build_defects4j_env(run_fn=run_fn, perl5_home=perl5_home)
    bin_path = dest / "framework" / "bin" / "defects4j"
    marker = dest / _DEFECTS4J_INIT_MARKER
    if not marker.is_file():
        try:
            proc = run_fn(
                init_timeout,
                ["bash", "init.sh"],
                cwd=str(dest),
                capture_output=True,
                text=True,
                env=env,
            )
        except (OSError, ValueError):
            return None
        if proc.returncode != 0 or not bin_path.is_file():
            return None
        marker.write_text("ok\n", encoding="utf-8")

    return {"home": str(dest), "bin": str(bin_path), "env": env}
