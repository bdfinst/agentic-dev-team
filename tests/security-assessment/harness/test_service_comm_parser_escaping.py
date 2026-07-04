"""Regression test for HTML/Mermaid injection in service-comm-parser.py.

`emit_mermaid()` builds a Mermaid `graph LR` block by interpolating
repo-derived strings (package.json `name`, Kubernetes Service names, NATS
subjects, npm/pip dependency names) directly into Mermaid node labels and
edge labels. Those labels are quoted with literal `"` in the Mermaid source
and rendered as HTML by Mermaid/downstream Markdown->HTML->PDF pipelines
(see plugins/security-assessment/commands/export-pdf.md), so an attacker who
controls one of those repo-derived strings (e.g. a malicious package.json
`name` field in a scanned repo) could break out of the label/quote context
and inject arbitrary HTML/script markup, or Mermaid syntax, into the
downstream report — a plausible HTML injection -> SSRF vector once the
report is rendered to HTML/PDF (weasyprint fetches remote resources
referenced in rendered HTML/CSS by default).

This test proves a crafted repo-derived string can no longer break out of
the Mermaid label/HTML context unescaped.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "plugins"
    / "security-assessment"
    / "harness"
    / "tools"
    / "service-comm-parser.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("service_comm_parser", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register before exec: @dataclass looks up cls.__module__ in
    # sys.modules while the module body is executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scp = _load_module()

MALICIOUS_NAME = '"><img src=x onerror=alert(document.domain)>'


def test_malicious_service_name_is_escaped_in_node_label():
    svc = scp.Service(name=MALICIOUS_NAME, repo="/tmp/evil-repo")
    out = scp.emit_mermaid([svc], [])

    # The raw payload must never appear verbatim in the emitted diagram —
    # i.e. no literal `<` / `>` / `"` markup delimiters from the payload,
    # only their HTML-escaped, inert text form.
    assert MALICIOUS_NAME not in out
    assert "<img src=x onerror=alert(document.domain)>" not in out

    # It must appear HTML-escaped instead.
    assert "&quot;&gt;&lt;img src=x onerror=alert(document.domain)&gt;" in out


def test_malicious_k8s_service_name_is_escaped():
    svc = scp.Service(name="checkout", repo="/tmp/checkout")
    svc.k8s_names.add('"><script>alert(1)</script>')
    out = scp.emit_mermaid([svc], [])

    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_malicious_nats_subject_is_escaped_in_edge_label():
    pub = scp.Service(name="svc-a", repo="/tmp/a")
    sub = scp.Service(name="svc-b", repo="/tmp/b")
    subject = '"><svg onload=alert(1)>'
    pub.publishes.add(subject)
    sub.subscribes.add(subject)

    edges = scp.derive_nats_edges([pub, sub])
    out = scp.emit_mermaid([pub, sub], edges)

    assert "<svg onload=alert(1)>" not in out
    assert "&lt;svg onload=alert(1)&gt;" in out


def test_malicious_dependency_name_is_escaped_in_edge_note():
    all_services = [
        scp.Service(name="svc-a", repo="/tmp/a"),
        scp.Service(name="svc-b", repo="/tmp/b"),
    ]
    edge = scp.Edge(
        src="svc-a",
        dst="svc-b",
        kind="package",
        note='npm dependency: "><iframe src=javascript:alert(1)>',
    )
    out = scp.emit_mermaid(all_services, [edge])

    assert "<iframe src=javascript:alert(1)>" not in out
    assert "&lt;iframe src=javascript:alert(1)&gt;" in out


def test_malicious_name_cannot_break_out_of_unquoted_node_id():
    # Node IDs are emitted unquoted (`node_id["label"]`), so a raw name
    # containing spaces/brackets/quotes could otherwise inject arbitrary
    # Mermaid syntax at the node-id position, not just inside the label.
    svc = scp.Service(name='a"] --> evil["pwned', repo="/tmp/evil")
    out = scp.emit_mermaid([svc], [])
    for line in out.splitlines():
        if line.startswith("  ") and "[" in line and "```" not in line:
            node_id = line.strip().split("[", 1)[0]
            assert all(c.isalnum() or c == "_" for c in node_id), (
                f"unsafe mermaid node id: {node_id!r}"
            )
