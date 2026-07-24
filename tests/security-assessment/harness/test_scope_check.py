"""scope_check.py's is_self_owned() duplicated the CIDR-match loop twice —
once for a literal IP host, once per resolved IP for a hostname. Both should
share one helper. These tests lock the existing accept/reject behavior and
then assert the duplication is gone.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys

import pytest

from _repo_root import REPO_ROOT

MODULE_PATH = (
    REPO_ROOT
    / "plugins"
    / "security-assessment"
    / "harness"
    / "redteam"
    / "lib"
    / "scope_check.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("scope_check", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scope_check"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


scope_check = _load_module()


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1:8080",
        "http://10.1.2.3",
        "http://172.16.0.5",
        "http://192.168.1.1",
        "http://[::1]",
        "http://[fc00::1]",
    ],
)
def test_self_owned_literal_ips_are_accepted(target: str) -> None:
    accepted, _reason = scope_check.is_self_owned(target)
    assert accepted is True


@pytest.mark.parametrize(
    "target",
    [
        "http://8.8.8.8",
        "http://1.1.1.1",
        "http://[2001:4860:4860::8888]",
    ],
)
def test_public_literal_ips_are_rejected(target: str) -> None:
    accepted, reason = scope_check.is_self_owned(target)
    assert accepted is False
    assert "not in self-owned CIDRs" in reason


def test_localhost_hostname_resolves_and_is_accepted() -> None:
    accepted, _reason = scope_check.is_self_owned("http://localhost")
    assert accepted is True


def test_unresolvable_hostname_is_refused_by_default() -> None:
    accepted, reason = scope_check.is_self_owned(
        "http://this-host-should-not-resolve.invalid"
    )
    assert accepted is False
    assert "Could not resolve host" in reason


def test_no_duplicated_cidr_match_loop() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    occurrences = src.count("for net in ALLOWED_CIDRS_V4")
    assert occurrences <= 1, (
        "the CIDR-match loop over ALLOWED_CIDRS_V4 appears more than once; "
        "extract a shared helper"
    )


def test_bare_host_without_scheme_is_treated_as_http() -> None:
    accepted, reason = scope_check.is_self_owned("127.0.0.1")
    assert accepted is True
    assert reason == "127.0.0.1 is in 127.0.0.0/8"


def test_literal_ip_accepted_reason_names_the_matching_cidr() -> None:
    _accepted, reason = scope_check.is_self_owned("http://192.168.1.1")
    assert reason == "192.168.1.1 is in 192.168.0.0/16"


def test_literal_public_ip_rejected_reason_is_exact() -> None:
    _accepted, reason = scope_check.is_self_owned("http://8.8.8.8")
    assert reason == "8.8.8.8 is a public IP; not in self-owned CIDRs."


def test_unresolvable_hostname_reason_is_exact() -> None:
    _accepted, reason = scope_check.is_self_owned(
        "http://this-host-should-not-resolve.invalid"
    )
    assert reason == (
        "Could not resolve host 'this-host-should-not-resolve.invalid'; "
        "refuse by default."
    )


def test_localhost_hostname_accepted_reason_is_exact() -> None:
    _accepted, reason = scope_check.is_self_owned("http://localhost")
    assert reason == "localhost resolves only to self-owned CIDRs."


def test_url_with_no_host_is_refused() -> None:
    target = "http:///justpath"
    accepted, reason = scope_check.is_self_owned(target)
    assert accepted is False
    assert reason == f"Could not parse host from '{target}'."


def test_hostname_resolving_to_public_ip_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(
        scope_check, "_resolve_host_ips", lambda host: ["8.8.8.8"]
    )
    accepted, reason = scope_check.is_self_owned("http://public-mirror.example")
    assert accepted is False
    assert reason == (
        "public-mirror.example resolves to 8.8.8.8 which is outside the "
        "self-owned CIDRs (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, "
        "192.168.0.0/16, ::1)."
    )


def test_hash_artifact_computes_sha256_of_file_contents(tmp_path) -> None:
    artifact = tmp_path / "authorization.md"
    artifact.write_bytes(b"I own this target.\n")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert scope_check.hash_artifact(artifact) == expected


def test_hash_artifact_raises_for_missing_path(tmp_path) -> None:
    missing = tmp_path / "does-not-exist.md"
    with pytest.raises(FileNotFoundError) as exc_info:
        scope_check.hash_artifact(missing)
    assert str(exc_info.value) == f"Self-cert artifact not found: {missing}"


def test_refusal_message_exact_wording() -> None:
    message = scope_check.refusal_message("http://8.8.8.8", "public IP")
    assert message == (
        "SCOPE VIOLATION: target http://8.8.8.8 refused.\n"
        "  public IP\n"
        "\n"
        "  To run against a public target you must pass --self-certify-owned <path>.\n"
        "  The <path> file declares that you own and are authorized to test this\n"
        "  target. Its SHA-256 hash will be logged for audit. Example:\n"
        "\n"
        "      # authorization.md\n"
        "      # I own target-host.example.com and authorize adversarial ML testing\n"
        "      # on 2026-04-21 through 2026-04-22. Signed: <name>, <role>.\n"
        "\n"
        "  Full format: knowledge/redteam-authorization.md (this plugin)."
    )
