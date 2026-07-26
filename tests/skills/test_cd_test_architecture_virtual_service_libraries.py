"""Content-guard tests for the new
`plugins/dev-team/knowledge/virtual-service-libraries.md` knowledge file
(issue #1435, sub-issue of epic #1431, depends on #1434). Traces to the
(transient) plan file
plans/issue-1435-cd-test-architecture-virtual-service-libraries.md — cite
the issue number alongside the plan path since the plan file is
gitignored/transient (deleted after implementation, per this repo's
CLAUDE.md) and issue #1435 is the durable reference once it's gone.

This file covers only Step 1.1 (the new knowledge file's own content: the
per-stack catalog, the preferred/backup framing, the "recommended starting
point, not a mandate" disclaimer, the broker-tooling-is-thinner note, and
the three-valued Resolution order section). Step 1.2 (corrections to the
four existing knowledge files) and Step 1.3 (wiring into
`cd-test-architecture/SKILL.md`) are covered by later, separate test
additions to this same file, per the plan.

Reuses the `section()`/`grep()`/`collapsed()` helper pattern from
`skill_doc_helpers.py` rather than duplicating it (per this plan's TEST
instruction).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, collapsed, grep, section

KNOWLEDGE_FILE = PLUGIN_ROOT / "knowledge" / "virtual-service-libraries.md"

# Step 1.2 targets: the four existing knowledge files whose stale
# pre-merge guidance is corrected to prefer virtual-service libraries.
CSHARP_REFERENCE_FILE = (
    PLUGIN_ROOT / "knowledge" / "references" / "csharp-http-client-testing.md"
)
DOTNET_PROFILE_FILE = PLUGIN_ROOT / "knowledge" / "test-stack-profiles" / "dotnet.md"
NODE_PROFILE_FILE = PLUGIN_ROOT / "knowledge" / "test-stack-profiles" / "node.md"
DJANGO_PROFILE_FILE = PLUGIN_ROOT / "knowledge" / "test-stack-profiles" / "django.md"


def _text() -> str:
    return KNOWLEDGE_FILE.read_text(encoding="utf-8")


def _catalog_section() -> str:
    return section(_text(), r"^## Catalog", boundary_pattern=r"^## ")


def _resolution_order_section() -> str:
    return section(_text(), r"^## Resolution order", boundary_pattern=r"^## ")


def test_file_exists():
    assert KNOWLEDGE_FILE.is_file()


def test_catalog_names_a_tool_per_profiled_backend_stack():
    sec = _catalog_section()
    # dotnet -> WireMock.Net
    assert grep(r"`dotnet`.*WireMock\.Net", sec)
    # node -> Nock
    assert grep(r"`node`.*Nock", sec)
    # spring-boot -> WireMock (not WireMock.Net)
    assert grep(r"`spring-boot`.*WireMock\b(?!\.Net)", sec)
    # go -> a Go-native record-and-replay library (e.g. go-vcr)
    assert grep(r"`go`.*go-vcr", sec)
    # django -> VCR.py (vcrpy)
    assert grep(r"`django`.*VCR\.py", sec)
    assert grep(r"vcrpy", sec, ignore_case=True)


def test_catalog_states_library_is_preferred_hand_rolled_is_backup():
    # Positive supporting text, not an absence check.
    text = collapsed(_text())
    assert grep(
        r"record-and-replay virtual-service library is the \*\*preferred\*\* "
        r"pre-merge double",
        text,
    )
    assert grep(r"hand-rolled Fake is the \*\*backup\*\*", text)


def test_catalog_states_recommended_not_mandate_disclaimer():
    # Matches component-test-patterns.md's existing disclaimer style
    # verbatim: "recommended starting points, not mandates: drop items
    # that don't apply, add what a component clearly needs."
    text = collapsed(_text())
    assert grep(
        r"recommended starting points, not mandates: drop items that "
        r"don't apply, add what a component clearly needs",
        text,
        ignore_case=True,
    )


def test_catalog_states_broker_tooling_is_thinner_not_silently_assumed_equal():
    text = collapsed(_text())
    assert grep(
        r"message-broker virtualization for Event Consumer/Producer "
        r"components has no equally mature per-stack tool",
        text,
        ignore_case=True,
    )
    assert grep(r"Mountebank is the closest general-purpose fallback", text)
    assert grep(
        r"thinner coverage than the HTTP-focused tools above, not an "
        r"equivalent substitute",
        text,
    )


def test_catalog_states_resolution_order():
    # Three-valued precedence: existing-tool detected -> catalog default
    # -> operator override/decline.
    sec = collapsed(_resolution_order_section())
    assert grep(r"\*\*Existing tool detected\*\*", sec)
    assert grep(r"\*\*Catalog default\*\*", sec)
    assert grep(r"\*\*Operator override or decline\*\*", sec)
    existing_idx = sec.index("Existing tool detected")
    catalog_idx = sec.index("Catalog default")
    override_idx = sec.index("Operator override or decline")
    assert existing_idx < catalog_idx < override_idx
    assert grep(r"no switch is suggested", sec, ignore_case=True)


# --- Step 1.2: correct the four existing knowledge files' stale ---
# --- pre-merge guidance (mirrors #1434's                         ---
# --- test_knowledge_files_state_the_universal_out_of_band_rule    ---
# --- "citation must stay true to its source" regression pattern). ---


def test_csharp_reference_states_wiremock_preferred_not_never_in_band():
    text = collapsed(CSHARP_REFERENCE_FILE.read_text(encoding="utf-8"))
    # Positive: WireMock.Net is now named the preferred pre-merge double.
    assert grep(
        r"WireMock\.Net is the \*\*preferred\*\* pre-merge double",
        text,
    )
    # Negative: the old absolute — "never in-band" — no longer applies to
    # WireMock.Net anywhere in the file.
    assert not grep(r"never in-band", text, ignore_case=True)
    # The file's other, still-valid "what to avoid" reasoning about
    # Kestrel-on-a-port is unrelated and untouched by this correction.
    assert grep(
        r"Kestrel on a random port \+ a real HTTP request", text
    )


def test_csharp_reference_does_not_claim_no_socket_in_process_mode():
    text = collapsed(CSHARP_REFERENCE_FILE.read_text(encoding="utf-8"))
    # Positive: names the verified same-process/localhost-only framing.
    assert grep(
        r"same-process, localhost-only, on an ephemeral port, with no "
        r"separately-managed external server",
        text,
    )
    assert grep(
        r"WireMockServer\.Start\(\)`? always binds a real HTTP listener on "
        r"localhost",
        text,
    )
    # Negative: never asserts WireMock.Net itself has/provides/supports an
    # in-process or no-socket transport as an affirmative claim — guards
    # against re-introducing the unverified claim round-2 review caught.
    assert not grep(
        r"WireMock\.Net (has|provides|supports|offers) an? "
        r"(in-process|no-socket|in-memory)",
        text,
        ignore_case=True,
    )


def test_dotnet_profile_no_longer_excludes_wiremock_from_pre_merge_seam():
    text = collapsed(DOTNET_PROFILE_FILE.read_text(encoding="utf-8"))
    # Positive: WireMock.Net now named as the seam's preferred implementation.
    assert grep(
        r"WireMock\.Net is the preferred implementation of that seam",
        text,
    )
    assert grep(
        r"hand-rolled `?StubHttpMessageHandler`? kept as backup", text
    )
    # Negative: the old "not ... WireMock" exclusion is gone.
    assert not grep(r"not\s+WireMock\b", text)


def test_node_profile_states_nock_preferred_msw_kept_as_fallback():
    text = collapsed(NODE_PROFILE_FILE.read_text(encoding="utf-8"))
    assert grep(r"\*\*Nock\*\* . the preferred record-and-replay tool", text)
    assert grep(
        r"\*\*MSW\*\* remains a documented fallback alternative", text
    )


def test_django_profile_states_vcrpy_preferred_responses_kept_as_fallback():
    text = collapsed(DJANGO_PROFILE_FILE.read_text(encoding="utf-8"))
    assert grep(
        r"\*\*VCR\.py\*\* \(`vcrpy`\) for outbound HTTP . the preferred "
        r"record-and-replay tool",
        text,
    )
    assert grep(
        r"`responses`/`httpx` mock remains a documented fallback alternative",
        text,
    )
