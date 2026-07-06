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
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .common import run_with_timeout

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
DEFECTS4J_REPO_URL = "https://github.com/rjust/defects4j.git"
BUGSJS_REPO_URL = "https://github.com/BugsJS/bug-dataset.git"
_DEFECTS4J_INIT_MARKER = ".d4j-init-complete"

DEFAULT_RUN_FN = run_with_timeout


def _resolve_java11_home(run_fn=DEFAULT_RUN_FN) -> Optional[str]:
    """Best-effort Java 11 home (#951): `/usr/libexec/java_home -v 11`,
    falling back to `brew --prefix openjdk@11`. macOS-only (Defects4J's
    Perl wrapper resolution issue is specific to Homebrew-installed JDKs);
    `None` on any other platform or when neither probe resolves.
    """
    if sys.platform != "darwin":
        return None
    for argv in (
        ["/usr/libexec/java_home", "-v", "11"],
        ["brew", "--prefix", "openjdk@11"],
    ):
        try:
            proc = run_fn(10, argv, capture_output=True, text=True)
        except (OSError, ValueError):
            continue
        if proc.returncode != 0:
            continue
        out = proc.stdout
        if isinstance(out, bytes):
            out = out.decode("utf-8", errors="replace")
        out = (out or "").strip()
        if out:
            return out
    return None


def resolve_defects4j_env(
    base_env: Optional[Dict[str, str]] = None, run_fn=DEFAULT_RUN_FN
) -> Dict[str, str]:
    """Merge JAVA_HOME (Java 11) and PERL5LIB resolution into a subprocess env (#951).

    Defects4J's Perl wrapper shells out to `java`/`javac` using whatever's
    on `PATH`/`JAVA_HOME`, and needs several CPAN modules installed via
    `cpanm --local-lib=~/perl5`. Resolve both here, scoped to a returned
    env dict passed to defects4j subprocess calls only — never touches
    global process state (no `os.environ` mutation), and falls back to
    the inherited environment unchanged when nothing can be resolved.
    """
    env = dict(base_env if base_env is not None else os.environ)

    java_home = _resolve_java11_home(run_fn=run_fn)
    if java_home:
        env["JAVA_HOME"] = java_home
        env["PATH"] = str(Path(java_home) / "bin") + os.pathsep + env.get("PATH", "")

    perl5lib = Path.home() / "perl5" / "lib" / "perl5"
    if perl5lib.is_dir():
        existing = env.get("PERL5LIB", "")
        env["PERL5LIB"] = str(perl5lib) + (os.pathsep + existing if existing else "")

    return env


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


def ensure_bugsjs_home(
    explicit_home: Optional[str],
    run_fn=DEFAULT_RUN_FN,
    cache_dir: Path = CACHE_DIR,
) -> Optional[str]:
    """Return a usable BugsJS/bug-dataset home, cloning into the cache if none was given."""
    if explicit_home:
        return explicit_home
    dest = cache_dir / "bugsjs-bug-dataset"
    if not _clone_if_missing(BUGSJS_REPO_URL, dest, run_fn=run_fn):
        return None
    return str(dest)


def ensure_defects4j_home(
    explicit_home: Optional[str],
    run_fn=DEFAULT_RUN_FN,
    init_timeout: int = 1800,
    cache_dir: Path = CACHE_DIR,
) -> Optional[Dict[str, Any]]:
    """Return `{"home": str, "bin": str, "env": dict}` for a usable Defects4J install.

    When `explicit_home` is given, returns it unchanged with `bin` set to
    the bare `"defects4j"` command name (today's PATH-based lookup) — no
    auto-clone over an explicit path. Otherwise clones `rjust/defects4j`
    into the cache and runs its `init.sh` once (skipped on later calls via
    a marker file — `init.sh` is slow and network-heavy). The resolved
    `bin` is always the cache clone's own `framework/bin/defects4j` (a
    committed, already-executable script — no build step), never a PATH
    lookup, since Defects4J needs its project repos bootstrapped under
    *this specific* home directory regardless of any other system-wide
    install.

    `env` (#951) is the JAVA_HOME/PERL5LIB-resolved environment from
    `resolve_defects4j_env()` — callers should pass it through to every
    defects4j subprocess call (`checkout`/`describe`/`run_tests`), since
    Defects4J's Perl wrapper needs a real Java 11 + CPAN deps regardless
    of whether the home was auto-cloned or explicit.
    """
    if explicit_home:
        return {
            "home": explicit_home,
            "bin": "defects4j",
            "env": resolve_defects4j_env(run_fn=run_fn),
        }

    dest = cache_dir / "defects4j"
    if not (dest / "framework" / "projects").is_dir():
        if not _clone_if_missing(DEFECTS4J_REPO_URL, dest, run_fn=run_fn):
            return None

    env = resolve_defects4j_env(run_fn=run_fn)
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
