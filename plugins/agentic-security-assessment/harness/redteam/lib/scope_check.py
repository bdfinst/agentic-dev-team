"""scope_check — enforce self-owned-target-only scope for the red-team harness.

By default, targets must be localhost + RFC1918 + ::1. Public hostnames and
IPs are refused unless the operator passes --self-certify-owned <path>; the
artifact's SHA-256 is logged for audit.
"""
from __future__ import annotations

import hashlib
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

# Self-owned CIDR allowlist
ALLOWED_CIDRS_V4 = [
    ipaddress.IPv4Network("127.0.0.0/8"),   # loopback
    ipaddress.IPv4Network("10.0.0.0/8"),     # RFC1918
    ipaddress.IPv4Network("172.16.0.0/12"),  # RFC1918
    ipaddress.IPv4Network("192.168.0.0/16"), # RFC1918
]
ALLOWED_CIDRS_V6 = [
    ipaddress.IPv6Network("::1/128"),   # loopback
    ipaddress.IPv6Network("fc00::/7"),  # unique local addresses
]


class ScopeViolation(Exception):
    """Raised when a target resolves outside the self-owned allowlist and no
    self-certification has been provided."""


def _resolve_host_ips(host: str) -> list[str]:
    try:
        info = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    return sorted({i[4][0] for i in info})


def is_self_owned(target_url: str) -> tuple[bool, str]:
    """Return (accepted, reason).

    Accepted when every resolved IP falls in an allowlist CIDR. Reason is a
    human-readable explanation for the refusal message when accepted is False.
    """
    parsed = urlparse(target_url if "://" in target_url else f"http://{target_url}")
    host = parsed.hostname
    if not host:
        return False, f"Could not parse host from '{target_url}'."

    # Literal IP
    try:
        ip = ipaddress.ip_address(host)
        if isinstance(ip, ipaddress.IPv4Address):
            for net in ALLOWED_CIDRS_V4:
                if ip in net:
                    return True, f"{host} is in {net}"
        else:
            for net in ALLOWED_CIDRS_V6:
                if ip in net:
                    return True, f"{host} is in {net}"
        return False, f"{host} is a public IP; not in self-owned CIDRs."
    except ValueError:
        pass

    # Hostname — resolve
    ips = _resolve_host_ips(host)
    if not ips:
        return False, f"Could not resolve host {host!r}; refuse by default."
    for ip_str in ips:
        ip = ipaddress.ip_address(ip_str)
        matched = False
        if isinstance(ip, ipaddress.IPv4Address):
            for net in ALLOWED_CIDRS_V4:
                if ip in net:
                    matched = True
                    break
        else:
            for net in ALLOWED_CIDRS_V6:
                if ip in net:
                    matched = True
                    break
        if not matched:
            return False, (
                f"{host} resolves to {ip} which is outside the self-owned "
                f"CIDRs (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, ::1)."
            )
    return True, f"{host} resolves only to self-owned CIDRs."


def hash_artifact(path: str | Path) -> str:
    """Compute SHA-256 of the self-cert artifact for the audit log."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Self-cert artifact not found: {path}")
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def refusal_message(target_url: str, reason: str) -> str:
    """Exact-wording refusal printed when scope is violated and no self-cert."""
    return (
        f"SCOPE VIOLATION: target {target_url} refused.\n"
        f"  {reason}\n"
        f"\n"
        f"  To run against a public target you must pass --self-certify-owned <path>.\n"
        f"  The <path> file declares that you own and are authorized to test this\n"
        f"  target. Its SHA-256 hash will be logged for audit. Example:\n"
        f"\n"
        f"      # authorization.md\n"
        f"      # I own target-host.example.com and authorize adversarial ML testing\n"
        f"      # on 2026-04-21 through 2026-04-22. Signed: <name>, <role>.\n"
        f"\n"
        f"  Full format: knowledge/redteam-authorization.md (this plugin)."
    )
