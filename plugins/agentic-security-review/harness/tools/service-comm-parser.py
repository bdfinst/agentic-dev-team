#!/usr/bin/env python3
"""service-comm-parser — emit a Mermaid diagram of inter-service communication.

Walks a repo for NATS subject declarations, Kubernetes Service manifests, and
package-manager dependency files, infers service-to-service edges, and emits
a Mermaid `graph` block annotated with auth / encryption status per edge.

Output is a Mermaid code block on stdout. Consumers (exec-report-generator,
cross-repo-synthesizer) embed it verbatim — downstream MUST not re-render.

Usage:
    service-comm-parser.py <repo-path> [<repo-path> ...]
    service-comm-parser.py --help

Exit codes:
    0  — Mermaid emitted on stdout (may be empty-ish if nothing found)
    2  — argument or IO error
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# NATS subject declarations — look for client.subscribe("subject") / publish patterns
NATS_PATTERN = re.compile(
    r"(?:subscribe|publish|queueSubscribe|request|respond)\s*\(\s*['\"]([a-zA-Z0-9._*>-]+)['\"]"
)
# NATS connection strings — auth / no-auth inference
NATS_AUTH_PATTERN = re.compile(r"nats://([^@/]+@)?[^/\s'\"]+")

# Kubernetes Service definitions (YAML kind: Service)
K8S_SERVICE_PATTERN = re.compile(
    r"^kind:\s*Service\b[\s\S]*?^metadata:[\s\S]*?^\s*name:\s*([\w-]+)",
    re.MULTILINE,
)

# package.json dependencies / requirements.txt / go.mod — emit service-on-service edges
# if one repo's package references an internal package naming another repo.


@dataclass
class Service:
    name: str
    repo: str
    publishes: set[str] = field(default_factory=set)  # NATS subjects published
    subscribes: set[str] = field(default_factory=set)  # NATS subjects subscribed
    k8s_names: set[str] = field(default_factory=set)  # declared K8s Service names
    nats_auth: bool | None = None  # True if auth'd, False if no-auth, None unknown


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # "nats" | "http" | "package"
    subject: str = ""
    auth: bool | None = None
    note: str = ""


def infer_service_name(repo_path: Path) -> str:
    """Service name = repo name unless package.json `name` field overrides."""
    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, dict) and data.get("name"):
                # Strip scope (@org/) for cleaner diagram nodes
                return str(data["name"]).lstrip("@").split("/", 1)[-1]
        except (json.JSONDecodeError, ValueError):
            pass
    return repo_path.name


def scan_nats(repo_path: Path, service: Service) -> None:
    for src_file in repo_path.rglob("*"):
        if not src_file.is_file():
            continue
        # Only text-ish files
        if src_file.suffix.lower() not in {".py", ".js", ".ts", ".go", ".java", ".scala", ".kt"}:
            continue
        try:
            text = src_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Crude: split by function calls; publish-style verbs go to publishes, subscribe-style to subscribes
        for m in re.finditer(NATS_PATTERN, text):
            subject = m.group(1)
            verb_match = re.search(
                r"(subscribe|publish|queueSubscribe|request|respond)", text[max(0, m.start() - 30): m.start() + 1]
            )
            verb = verb_match.group(1).lower() if verb_match else ""
            if verb in ("subscribe", "queuesubscribe", "respond"):
                service.subscribes.add(subject)
            else:
                service.publishes.add(subject)

        # Auth inference
        auth_matches = NATS_AUTH_PATTERN.findall(text)
        if auth_matches:
            # If any connection string has an @ (user@host), treat as auth-present
            service.nats_auth = any(m for m in auth_matches)


def scan_k8s(repo_path: Path, service: Service) -> None:
    for src_file in repo_path.rglob("*.yaml"):
        try:
            text = src_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in K8S_SERVICE_PATTERN.finditer(text):
            service.k8s_names.add(m.group(1))
    for src_file in repo_path.rglob("*.yml"):
        try:
            text = src_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in K8S_SERVICE_PATTERN.finditer(text):
            service.k8s_names.add(m.group(1))


def scan_package_deps(repo_path: Path, service: Service, all_services: list[Service]) -> list[Edge]:
    """Emit edges where one repo's package.json / requirements.txt references
    another repo's service name as an internal dependency.
    """
    edges: list[Edge] = []
    service_names = {s.name for s in all_services}

    pkg = repo_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            deps = {}
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                deps.update(data.get(key, {}) or {})
            for dep_name in deps:
                # Normalize: drop scope
                normalized = dep_name.lstrip("@").split("/", 1)[-1]
                if normalized in service_names and normalized != service.name:
                    edges.append(Edge(
                        src=service.name,
                        dst=normalized,
                        kind="package",
                        note=f"npm dependency: {dep_name}",
                    ))
        except (json.JSONDecodeError, ValueError):
            pass

    requirements = repo_path / "requirements.txt"
    if requirements.exists():
        try:
            for line in requirements.read_text(encoding="utf-8").splitlines():
                line = line.strip().split("==")[0].split(">=")[0].split("<=")[0]
                if line and line in service_names and line != service.name:
                    edges.append(Edge(
                        src=service.name,
                        dst=line,
                        kind="package",
                        note=f"pip dependency: {line}",
                    ))
        except OSError:
            pass

    return edges


def derive_nats_edges(services: list[Service]) -> list[Edge]:
    """Match subjects between publishers and subscribers."""
    edges: list[Edge] = []
    # Build a subject → list of (service, role) index
    publishers: dict[str, list[str]] = {}
    subscribers: dict[str, list[str]] = {}
    for svc in services:
        for subj in svc.publishes:
            publishers.setdefault(subj, []).append(svc.name)
        for subj in svc.subscribes:
            subscribers.setdefault(subj, []).append(svc.name)

    for subject in set(publishers) | set(subscribers):
        pubs = publishers.get(subject, [])
        subs = subscribers.get(subject, [])
        for p in pubs:
            for s in subs:
                if p == s:
                    continue
                # Auth inference: if either end has nats_auth False and the other unknown, mark as unauth
                pub_svc = next((svc for svc in services if svc.name == p), None)
                sub_svc = next((svc for svc in services if svc.name == s), None)
                auth = None
                if pub_svc and sub_svc:
                    if pub_svc.nats_auth is False or sub_svc.nats_auth is False:
                        auth = False
                    elif pub_svc.nats_auth and sub_svc.nats_auth:
                        auth = True
                edges.append(Edge(src=p, dst=s, kind="nats", subject=subject, auth=auth))
    return edges


def emit_mermaid(services: list[Service], edges: list[Edge]) -> str:
    lines = ["```mermaid", "graph LR"]
    # Nodes
    for svc in services:
        node_id = svc.name.replace("-", "_")
        # Annotate with K8s Services if any
        label = svc.name
        if svc.k8s_names:
            label += f"<br/>k8s: {', '.join(sorted(svc.k8s_names))}"
        lines.append(f'  {node_id}["{label}"]')

    # Edges — dedup; annotate auth / encryption where known
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        src_id = e.src.replace("-", "_")
        dst_id = e.dst.replace("-", "_")
        key = (src_id, dst_id, e.subject)
        if key in seen:
            continue
        seen.add(key)
        if e.kind == "nats":
            auth_tag = "auth" if e.auth is True else ("NO-AUTH" if e.auth is False else "?auth")
            label = f"{e.subject} [{auth_tag}]"
            lines.append(f'  {src_id} -- "{label}" --> {dst_id}')
        elif e.kind == "package":
            lines.append(f'  {src_id} -. "{e.note}" .-> {dst_id}')
        else:
            lines.append(f"  {src_id} --> {dst_id}")

    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Repo paths to scan (one or more).")
    args = parser.parse_args()

    services: list[Service] = []
    for path_arg in args.paths:
        p = Path(path_arg)
        if not p.exists() or not p.is_dir():
            print(f"service-comm-parser: skipping non-directory: {path_arg}", file=sys.stderr)
            continue
        svc = Service(name=infer_service_name(p), repo=str(p))
        scan_nats(p, svc)
        scan_k8s(p, svc)
        services.append(svc)

    if not services:
        print("```mermaid\ngraph LR\n  empty[\"no services detected\"]\n```")
        return 0

    # Compute edges
    edges = derive_nats_edges(services)
    for svc in services:
        svc_path = Path(svc.repo)
        edges.extend(scan_package_deps(svc_path, svc, services))

    print(emit_mermaid(services, edges))
    return 0


if __name__ == "__main__":
    sys.exit(main())
