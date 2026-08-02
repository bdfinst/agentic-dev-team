"""Tests for scripts/verify_pmd_checksum_pin.py — the network-gated PMD pin verifier.

Hermetic: no test here touches the real network. `urllib.request.urlopen` is
stubbed to serve known local bytes, exercising only the compare-and-report
logic that `.github/workflows/opt-in-tests.yml`'s "PMD checksum verify" job
runs for real against the live release asset (issue #1657).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
from unittest.mock import patch

import pytest

from _repo_root import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "verify_pmd_checksum_pin.py"
INSTALLER = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "install-java-static-analysis.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_pmd_checksum_pin", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, url: str = "https://github.com/pmd/pmd/releases/download/x"):
        super().__init__(data)
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def test_matching_asset_passes(capsys):
    module = _load_module()
    payload = b"pretend pmd zip bytes"
    real_sha256 = hashlib.sha256(payload).hexdigest()

    with (
        patch.object(module, "_load_installer_constants", return_value=("9.9.9-test", real_sha256)),
        patch.object(module, "_check_url_shape_matches_installer", lambda: None),
        patch.object(module.urllib.request, "urlopen", return_value=_FakeResponse(payload)),
    ):
        assert module.main() == 0
    assert "verified" in capsys.readouterr().out


def test_mismatched_asset_fails_loudly(capsys):
    module = _load_module()
    payload = b"pretend pmd zip bytes"
    wrong_sha256 = "0" * 64

    with (
        patch.object(module, "_load_installer_constants", return_value=("9.9.9-test", wrong_sha256)),
        patch.object(module, "_check_url_shape_matches_installer", lambda: None),
        patch.object(module.urllib.request, "urlopen", return_value=_FakeResponse(payload)),
    ):
        assert module.main() == 1
    err = capsys.readouterr().err
    assert "mismatch" in err
    assert wrong_sha256 in err


def test_url_shape_check_passes_against_the_real_installer():
    """The premise check must pass against the real, current installer —
    proving the copied archive/URL template genuinely still matches, not
    just that the function runs without error."""
    module = _load_module()
    module._check_url_shape_matches_installer()  # must not raise


def test_archive_template_check_is_anchored_to_code_not_a_comment(tmp_path):
    """arch-review + ai-provenance-review finding (#1657 closing-pass
    round, 2x corroborated): the original version of this check compared
    the INTERPOLATED archive name against the installer's raw source text —
    which passed only because the installer's own provenance COMMENT
    happens to also contain that literal rendered string
    ('# SHA-256 of pmd-dist-9.9.9-test-bin.zip, ...'), not because the real
    f"pmd-dist-{PMD_VERSION}-bin.zip" assignment matched. That meant the
    check could never detect the installer's actual archive-building code
    changing shape. Prove the fix: an installer whose comment still praises
    the old name, but whose real code now builds a DIFFERENT archive name,
    must fail this check — a bare substring-of-rendered-value check would
    pass here."""
    module = _load_module()
    fake_installer = tmp_path / "install-java-static-analysis.py"
    fake_installer.write_text(
        'PMD_VERSION = "9.9.9-test"\n'
        '# SHA-256 of pmd-dist-9.9.9-test-bin.zip, pinned alongside the version above\n'
        'archive = f"pmd-src-{PMD_VERSION}.zip"\n'  # renamed shape, comment unchanged
        'url = "https://github.com/pmd/pmd/releases/download/pmd_releases%2F" + PMD_VERSION\n',
        encoding="utf-8",
    )
    with (
        patch.object(module, "INSTALLER", fake_installer),
        pytest.raises(AssertionError, match="no longer builds"),
    ):
        module._check_url_shape_matches_installer()


def test_url_template_check_fails_when_the_percent_encoded_fragment_is_gone(tmp_path):
    """Same discrimination proof for the other half of the check: a
    pmd_releases%2F fragment mentioned only in a comment, with the real code
    using a different (broken) tag shape, must fail."""
    module = _load_module()
    fake_installer = tmp_path / "install-java-static-analysis.py"
    fake_installer.write_text(
        'PMD_VERSION = "9.9.9-test"\n'
        '# uses pmd_releases%2F, a percent-encoded slash\n'
        'archive = f"pmd-dist-{PMD_VERSION}-bin.zip"\n'
        'url = "https://github.com/pmd/pmd/releases/download/pmd_releases/" + PMD_VERSION\n',
        encoding="utf-8",
    )
    with (
        patch.object(module, "INSTALLER", fake_installer),
        pytest.raises(AssertionError, match="no longer contains the pmd_releases%2F"),
    ):
        module._check_url_shape_matches_installer()


def test_loads_the_real_installer_constants():
    """Sanity check the loader actually points at the shipped installer and
    resolves real, well-formed constants — a typo in the module path here
    would make both tests above pass against nothing."""
    module = _load_module()
    version, sha256 = module._load_installer_constants()
    assert version
    assert len(sha256) == 64
    assert all(c in "0123456789abcdef" for c in sha256)


def test_loader_does_not_execute_the_installer_module():
    """Security hardening (issue #1657 review finding): the loader must read
    PMD_VERSION/PMD_SHA256 via a static parse, never by importing (and
    therefore executing) the installer — a PR that edits the installer would
    otherwise have its own version of that file's module-level code executed
    by this verifier's CI job."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "exec_module" not in source, (
        "the constant loader must not import/exec the installer module"
    )
    assert "ast.parse" in source and "ast.literal_eval" in source

    # And a live check: a PMD_SHA256 that would fail the installer's own
    # module-level format assertion (see install-java-static-analysis.py's
    # import-time check) must not prevent the loader from reading it, since
    # a static parse never executes that assertion at all.
    installer_source = INSTALLER.read_text(encoding="utf-8")
    assert "PMD_SHA256 is not a 64-char lowercase hex digest" in installer_source, (
        "installer's own import-time assertion moved or was removed — this "
        "test's premise (a static parse skips it) needs re-checking"
    )


def test_https_redirect_downgrade_is_rejected(capsys):
    """If the fetch redirects off https (a scheme downgrade), refuse rather
    than hash whatever arrived over plaintext."""
    module = _load_module()
    payload = b"pretend pmd zip bytes"

    with (
        patch.object(module, "_load_installer_constants", return_value=("9.9.9-test", "0" * 64)),
        patch.object(module, "_check_url_shape_matches_installer", lambda: None),
        patch.object(
            module.urllib.request,
            "urlopen",
            return_value=_FakeResponse(payload, url="http://github.com/pmd/pmd/releases/x"),
        ),
        pytest.raises(AssertionError, match="https"),
    ):
        module.main()
