#!/usr/bin/env python3
"""verify_pmd_checksum_pin.py — confirm PMD_SHA256 matches the real release asset.

`plugins/dev-team/scripts/install-java-static-analysis.py` pins `PMD_SHA256`
by hand at authoring time (curl the release asset, `shasum -a 256`, paste the
result). `test_checksum_mismatch_refuses_to_extract` proves the installer's
*rejection* path works against a synthetic tampered archive, but nothing in
the hermetic test suite ever re-fetches the real, currently-published PMD
release and checks the pin against it — so a typo in the pin, or PMD
re-publishing the same version tag with different bytes, would only surface
as every user's `/project-init` Java lane failing in the field.

Network-gated by design (issue #1657): downloads the real
`pmd-dist-<PMD_VERSION>-bin.zip` from the pinned GitHub release URL and
asserts its SHA-256 equals the installer's `PMD_SHA256`. Run by the "PMD
checksum verify" job in `.github/workflows/opt-in-tests.yml` (path-filtered
on the installer changing, plus the workflow's existing weekly schedule so an
upstream re-publish is caught even with no local change) — not part of the
default hermetic `ci-local.sh` gate, which never touches the network.

Per this repo's CLAUDE.md rule: "Verify a runtime property by exercising it
at runtime," not by comment.
"""

from __future__ import annotations

import ast
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "install-java-static-analysis.py"

#: Fetch timeout in seconds — bounds a hung connection instead of relying
#: solely on the calling CI job's own overall timeout-minutes.
_FETCH_TIMEOUT_SECONDS = 60


def _load_installer_constants() -> tuple[str, str]:
    """Read PMD_VERSION/PMD_SHA256 from the installer via a static AST parse,
    not by importing (and therefore executing) the module.

    The installer is a plugin-shipped script, but this verifier's CI job is
    triggered by `pull_request` with a path filter that includes the
    installer itself — so a PR whose whole purpose is to edit that file would
    otherwise cause CI to execute the PR's own version of it at import scope
    (its module-level PMD_SHA256 format assertion already runs there today).
    Two string constants don't need an execution sink; parsing the source
    removes that class of risk entirely, and is the deterministic-over-
    inference choice CLAUDE.md asks for regardless.
    """
    tree = ast.parse(INSTALLER.read_text(encoding="utf-8"), filename=str(INSTALLER))
    found: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ("PMD_VERSION", "PMD_SHA256"):
                found[target.id] = ast.literal_eval(node.value)
    missing = {"PMD_VERSION", "PMD_SHA256"} - found.keys()
    assert not missing, f"{INSTALLER} is missing module-level constant(s): {sorted(missing)}"
    return found["PMD_VERSION"], found["PMD_SHA256"]


def _archive_template_present(tree: ast.AST) -> bool:
    """True if `tree` contains an f-string shaped like
    ``f"pmd-dist-{PMD_VERSION}-bin.zip"`` — checked structurally (an
    f-string node with a `PMD_VERSION`-referencing interpolation between the
    two literal segments), not by a raw substring search. A substring search
    for the rendered name (e.g. ``"pmd-dist-<version>-bin.zip"``) would also
    match the unrelated provenance *comment* a few lines above the real
    assignment, which contains that exact rendered string too — passing
    regardless of what the actual archive-building code says (caught in
    review, issue #1657's closing pass)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        constants = [v.value for v in node.values if isinstance(v, ast.Constant)]
        has_version_ref = any(
            isinstance(v, ast.FormattedValue)
            and isinstance(v.value, ast.Name)
            and v.value.id == "PMD_VERSION"
            for v in node.values
        )
        if (
            has_version_ref
            and any("pmd-dist-" in c for c in constants)
            and any("-bin.zip" in c for c in constants)
        ):
            return True
    return False


def _url_template_present(tree: ast.AST) -> bool:
    """True if `tree` contains the deliberately percent-encoded
    ``pmd_releases%2F`` release-tag fragment as an actual string literal in
    code — not merely mentioned in a comment (comments aren't nodes in the
    parsed AST at all, so this can't accidentally match one)."""
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "pmd_releases%2F" in node.value
        for node in ast.walk(tree)
    )


def _check_url_shape_matches_installer() -> None:
    """The archive-name and release-tag shape verify_pmd_checksum_pin.py
    builds are copied from `install-java-static-analysis.py`, not imported
    from it (`_load_installer_constants` deliberately never executes that
    file — see its docstring). If the installer's own URL-building code ever
    changes shape, this verifier would otherwise silently keep hashing an
    asset no `/project-init` run actually downloads. Fail loudly instead:
    parse the installer's AST and assert it still contains the exact
    template structure this copy assumes.
    """
    tree = ast.parse(INSTALLER.read_text(encoding="utf-8"), filename=str(INSTALLER))
    assert _archive_template_present(tree), (
        'install-java-static-analysis.py no longer builds f"pmd-dist-{PMD_VERSION}'
        '-bin.zip" in its actual code — its release-URL shape changed; '
        "verify_pmd_checksum_pin.py's copy of that shape needs updating to match "
        "before this check means anything"
    )
    assert _url_template_present(tree), (
        "install-java-static-analysis.py no longer contains the pmd_releases%2F "
        "release-tag fragment as a string literal in its actual code — its "
        "release-URL shape changed; verify_pmd_checksum_pin.py's copy needs updating"
    )


def main() -> int:
    version, expected_sha256 = _load_installer_constants()
    archive = f"pmd-dist-{version}-bin.zip"
    _check_url_shape_matches_installer()
    # %2F is a deliberately percent-encoded slash: the real PMD release tag is
    # literally "pmd_releases/{version}" (a slash inside one path segment),
    # not two path segments — do not "fix" this to a literal "/".
    url = f"https://github.com/pmd/pmd/releases/download/pmd_releases%2F{version}/{archive}"

    print(f"Downloading {archive} from the real release URL...")
    digest = hashlib.sha256()
    with urllib.request.urlopen(
        url, timeout=_FETCH_TIMEOUT_SECONDS
    ) as response:
        assert response.url.startswith("https://"), f"redirected off https: {response.url}"
        for chunk in iter(lambda: response.read(65536), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()

    if actual_sha256 != expected_sha256:
        print(
            f"PMD_SHA256 pin mismatch for {archive}:\n"
            f"  installer pin : {expected_sha256}\n"
            f"  real asset    : {actual_sha256}\n"
            "Either install-java-static-analysis.py's PMD_SHA256 has a typo, or "
            f"PMD re-published pmd_releases/{version} with different bytes. Every "
            "downstream /project-init Java lane will hard-fail until this is fixed.",
            file=sys.stderr,
        )
        return 1

    print(f"PMD_SHA256 pin verified against the real {archive}: {actual_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
