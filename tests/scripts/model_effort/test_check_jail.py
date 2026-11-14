"""The macOS check jail: preference writes refused, Mach services and signals denied by default."""

from __future__ import annotations

import shutil
import subprocess
import sys

import _model_effort_support  # noqa: F401  (puts the harness on sys.path first)
import pytest
from model_effort import check_jail

PREFERENCE_DENIAL = "(deny user-preference-write)\n"
MACH_DEFAULT_DENIAL = "(deny mach-lookup)\n"
SIGNAL_DENIAL = "(deny signal)\n"
SAME_SANDBOX_SIGNALS = "(allow signal (target same-sandbox))\n"


def _sandbox_exec_jail() -> check_jail.CheckJail:
    jail = check_jail.candidate_jail()
    if jail is None or jail.tool != check_jail.SANDBOX_EXEC:
        pytest.skip("needs sandbox-exec")
    return jail


class TestProfile:
    def test_the_profile_refuses_preference_writes(self, tmp_path):
        assert PREFERENCE_DENIAL in check_jail.sandbox_exec_profile([tmp_path])

    def test_the_profile_denies_every_mach_service_but_an_allowlist(self, tmp_path):
        profile = check_jail.sandbox_exec_profile([tmp_path])

        assert MACH_DEFAULT_DENIAL in profile
        assert profile.index(MACH_DEFAULT_DENIAL) < profile.index("(allow mach-lookup")
        for service in (
            "com.apple.coreservices.launchservicesd",
            "com.apple.coreservices.appleevents",
            "com.apple.dnssd.service",
        ):
            assert f'"{service}"' not in profile


    def test_the_profile_denies_signals_outside_the_jail(self, tmp_path):
        profile = check_jail.sandbox_exec_profile([tmp_path])

        assert SIGNAL_DENIAL in profile
        assert profile.index(SIGNAL_DENIAL) < profile.index(SAME_SANDBOX_SIGNALS)


class TestProbe:
    def test_the_probe_fails_a_profile_that_allows_signals_to_any_process(
        self, monkeypatch
    ):
        jail = _sandbox_exec_jail()
        real_profile = check_jail.sandbox_exec_profile
        monkeypatch.setattr(
            check_jail,
            "sandbox_exec_profile",
            lambda writable: real_profile(writable).replace(SIGNAL_DENIAL, ""),
        )

        assert check_jail.probe(jail) is False

    def test_the_probe_fails_a_profile_that_allows_preference_writes(self, monkeypatch):
        jail = _sandbox_exec_jail()
        real_profile = check_jail.sandbox_exec_profile
        monkeypatch.setattr(
            check_jail,
            "sandbox_exec_profile",
            lambda writable: real_profile(writable).replace(PREFERENCE_DENIAL, ""),
        )

        assert check_jail.probe(jail) is False

    def test_a_failed_preference_probe_leaves_no_domain_behind(self, monkeypatch):
        jail = _sandbox_exec_jail()
        real_profile = check_jail.sandbox_exec_profile
        monkeypatch.setattr(
            check_jail,
            "sandbox_exec_profile",
            lambda writable: real_profile(writable).replace(PREFERENCE_DENIAL, ""),
        )

        check_jail.probe(jail)

        read = subprocess.run(
            ["/usr/bin/defaults", "read", check_jail.PREFERENCE_PROBE_DOMAIN, "probe"],
            capture_output=True,
            check=False,
        )
        assert read.returncode != 0


SIGNALS_OWN_CHILD = (
    "import subprocess, sys\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "child.terminate()\n"
    "sys.exit(0 if child.wait(timeout=20) != 0 else 1)\n"
)
TIMES_OUT_OWN_CHILD = (
    "import subprocess, sys\n"
    "try:\n"
    "    subprocess.run([sys.executable, '-c', 'import time; time.sleep(60)'], timeout=1)\n"
    "except subprocess.TimeoutExpired:\n"
    "    sys.exit(0)\n"
    "sys.exit(1)\n"
)


class TestToolsStillRun:
    @pytest.mark.parametrize(
        "argv",
        [
            [sys.executable, "-c", "import os, pwd; pwd.getpwuid(os.getuid())"],
            ["git", "init", "-q", "repo"],
            [sys.executable, "-c", SIGNALS_OWN_CHILD],
            [sys.executable, "-c", TIMES_OUT_OWN_CHILD],
            [sys.executable, "-m", "pytest", "--version"],
            ["node", "-e", "require('child_process').execSync('true')"],
            ["npx", "--version"],
        ],
        ids=[
            "user-lookup",
            "git",
            "signal-own-child",
            "timeout-kills-own-child",
            "pytest",
            "node-child-process",
            "npx",
        ],
    )
    def test_a_command_that_needs_an_allowed_service_runs(self, tmp_path, argv):
        jail = _sandbox_exec_jail()
        if shutil.which(argv[0]) is None:
            pytest.skip(f"{argv[0]} not installed")

        completed = subprocess.run(
            jail.wrap(argv, tmp_path, tmp_path),
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
