"""`scripts/ci-local.sh` promises CI and the pre-push gate run identical
checks. For shellcheck that was false, and the gap had teeth.

The workflow apt-installed whatever Ubuntu shipped (0.9.0); developers ran
whatever their package manager gave (0.11.0 via Homebrew). Two majors apart,
and they disagree on real findings — 0.9.0 reports SC2015 (`A && B || C is not
if-then-else`) where 0.11.0 cannot report it at all, because upstream retired
the check. A change passed the local gate and failed CI on exactly that.

The fix is the same shape the repo already uses for `PYTHON_CEILING`: declare
the version once, in `ci-local.sh`, and have both sides resolve *that* binary
rather than two that merely share a name. These tests hold the declaration and
the workflow together in both directions, because a pin nothing checks is a
comment.

Why the pin is 0.10.0 rather than the newest release is recorded next to
`SHELLCHECK_VERSION` itself, not duplicated here — a copy of a rationale in
prose is exactly what goes stale.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

CI_LOCAL = REPO_ROOT / "scripts" / "ci-local.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "plugin-tests.yml"

_PIN_RE = re.compile(r'^SHELLCHECK_VERSION="([0-9]+\.[0-9]+\.[0-9]+)"$', re.MULTILINE)


def _declared_version() -> str:
    m = _PIN_RE.search(CI_LOCAL.read_text(encoding="utf-8"))
    assert m, "scripts/ci-local.sh must declare SHELLCHECK_VERSION=\"X.Y.Z\""
    return m.group(1)


def test_ci_local_declares_exactly_one_shellcheck_version():
    text = CI_LOCAL.read_text(encoding="utf-8")
    assert len(_PIN_RE.findall(text)) == 1, (
        "SHELLCHECK_VERSION must be declared exactly once — two declarations "
        "are how a pin drifts from itself."
    )
    assert _declared_version()


def test_the_workflow_does_not_apt_install_shellcheck():
    """apt gives whatever the runner image ships, which is the drift itself.

    This is the assertion that would have caught the original defect: the job
    installed a shellcheck nobody declared, so 'CI and local run identical
    checks' was true of every gate except this one.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in text.splitlines()
        if "apt-get install" in line and "shellcheck" in line
    ]
    assert not offenders, (
        "The workflow apt-installs shellcheck, so CI runs the runner image's "
        "version rather than the pinned SHELLCHECK_VERSION in "
        "scripts/ci-local.sh. Let ci-local.sh resolve it instead:\n  "
        + "\n  ".join(offenders)
    )


def test_no_gate_invokes_a_bare_shellcheck_off_path():
    """A bare `shellcheck ...` in a gate silently reintroduces the drift.

    Comments and the `# shellcheck source=` / `# shellcheck disable=`
    directives are not invocations; neither is the resolver's own version
    probe, which must run the PATH binary to decide whether it is the pinned
    one.
    """
    offenders = []
    for lineno, line in enumerate(CI_LOCAL.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # The word inside a quoted string (a printf message, a URL) is text,
        # not a command. Drop quoted spans before looking for an invocation.
        code = re.sub(r"'[^']*'|\"[^\"]*\"", " ", line)
        if not re.search(r"(?:^|[;&|(`$\s])shellcheck\s", code):
            continue
        # The resolver legitimately probes PATH's shellcheck for its version.
        if "--version" in line or "command -v shellcheck" in line:
            continue
        offenders.append(f"{lineno}: {stripped}")
    assert not offenders, (
        "A gate invokes `shellcheck` from PATH instead of the resolved pinned "
        "binary, so it lints with whatever the developer happens to have:\n  "
        + "\n  ".join(offenders)
    )


def test_the_resolver_rejects_a_mismatched_path_binary():
    """The resolver must compare the FULL version, not merely find a binary.

    `command -v shellcheck` succeeding is what made the old prerequisite check
    useless — it passed on a machine whose shellcheck disagreed with CI's.
    """
    text = CI_LOCAL.read_text(encoding="utf-8")
    assert "_resolve_shellcheck()" in text
    assert '"^version: ${SHELLCHECK_VERSION}$"' in text, (
        "_resolve_shellcheck must match the declared version exactly; a "
        "substring or prefix match would accept 0.10.0x or 0.1.0."
    )


def test_the_prerequisite_check_does_not_merely_require_shellcheck_on_path():
    """Listing shellcheck as a plain prerequisite would re-assert that any
    shellcheck will do — the belief this whole pin exists to correct."""
    text = CI_LOCAL.read_text(encoding="utf-8")
    m = re.search(r"for t in ([a-z0-9 _-]+); do\n\s+command -v", text)
    assert m, "expected the prerequisite tool loop in scripts/ci-local.sh"
    assert "shellcheck" not in m.group(1).split(), (
        "shellcheck is version-pinned, not merely required: a `command -v` "
        "probe passes on a machine whose shellcheck disagrees with CI's. "
        "_resolve_shellcheck handles it instead."
    )


def test_the_resolver_installs_atomically():
    """Both shellcheck gates run CONCURRENTLY in ci-local's pool, so two
    resolvers can install at once against a cold cache.

    Copying straight onto the cached path overwrites the binary the other
    process is executing — `ETXTBSY` on Linux. That is how this failed in CI
    while passing locally, where the cache happened to be warm. And the
    staging name must be unique per PROCESS: `$$` is the *parent* shell's PID,
    identical across the pool's subshells, so both racers picked the same
    staging file and one rename found nothing there.
    """
    text = CI_LOCAL.read_text(encoding="utf-8")
    resolver = text[text.index("_resolve_shellcheck()"):text.index("_shellcheck_or_fail()")]

    assert 'mv -f "$staged" "$cache/shellcheck"' in resolver, (
        "install must be an atomic rename within the cache directory, not a "
        "copy onto the live path"
    )
    assert 'mktemp -- "$cache/.shellcheck-XXXXXX"' in resolver, (
        "the staging name must come from mktemp — `$$` is the parent shell's "
        "PID and collides across concurrent subshells"
    )
    assert 'cp "$tmp/shellcheck-v${SHELLCHECK_VERSION}/shellcheck" "$cache/shellcheck"' not in resolver
    assert ".shellcheck.$$" not in resolver

    # The loser of the race must use the winner's install rather than error.
    tail = resolver[resolver.index("rm -rf \"$tmp\"", resolver.index("mv -f")):]
    assert '[ -x "$cache/shellcheck" ]' in tail, (
        "a resolver that loses the race must fall back to the cached binary a "
        "concurrent one just finished installing"
    )
