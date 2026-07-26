"""Content-guard tests for the new
`plugins/dev-team/knowledge/virtual-service-libraries.md` knowledge file
(issue #1435, sub-issue of epic #1431, depends on #1434). Traces to the
(transient) plan file
plans/issue-1435-cd-test-architecture-virtual-service-libraries.md — cite
the issue number alongside the plan path since the plan file is
gitignored/transient (deleted after implementation, per this repo's
CLAUDE.md) and issue #1435 is the durable reference once it's gone.

This file covers Step 1.1 (the new knowledge file's own content: the
per-stack catalog, the preferred/backup framing, the "recommended starting
point, not a mandate" disclaimer, the broker-tooling-is-thinner note, and
the three-valued Resolution order section), Step 1.2 (corrections to the
four existing knowledge files), and Step 1.3 (wiring the preferred/backup
sub-question, existing-tool detection, and the library-backed Story shape
into `cd-test-architecture/SKILL.md`'s Downstream-service branch).

Reuses the `section()`/`grep()`/`collapsed()` helper pattern from
`skill_doc_helpers.py` rather than duplicating it (per this plan's TEST
instruction).
"""

from __future__ import annotations

from skill_doc_helpers import (
    PLUGIN_ROOT,
    cd_test_architecture_downstream_service_branch_section,
    cd_test_architecture_output_section,
    collapsed,
    grep,
    section,
)

KNOWLEDGE_FILE = PLUGIN_ROOT / "knowledge" / "virtual-service-libraries.md"
SKILL = PLUGIN_ROOT / "skills" / "cd-test-architecture" / "SKILL.md"

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


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _downstream_service_branch_section() -> str:
    return cd_test_architecture_downstream_service_branch_section(_skill_text())


def _step_1_section() -> str:
    return section(_skill_text(), r"^### 1\. Inventory", boundary_pattern=r"^### 2\.")


def _build_testcontainers_bullet() -> str:
    return collapsed(
        section(
            _downstream_service_branch_section(),
            r"\*\*Build \(testcontainers\)\*\*",
            boundary_pattern=r"^- \*\*Build \(Fake\)\*\*",
        )
    )


def _build_fake_bullet() -> str:
    return collapsed(
        section(
            _downstream_service_branch_section(),
            r"\*\*Build \(Fake\)\*\*",
            boundary_pattern=r"^- \*\*Document-only\*\*",
        )
    )


def _document_only_bullet() -> str:
    return collapsed(
        section(
            _downstream_service_branch_section(),
            r"\*\*Document-only\*\*",
        )
    )


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


# --- Step 1.3: wire the preferred/backup sub-question into SKILL.md's ---
# --- Downstream-service branch                                        ---


def test_subquestion_answer_grammar_is_three_valued_not_binary():
    sec = collapsed(_downstream_service_branch_section())
    assert grep(r"three-valued, not binary", sec, ignore_case=True)
    assert grep(
        r"accept the recommended virtual-service library", sec, ignore_case=True
    )
    assert grep(r"name a specific different library", sec, ignore_case=True)
    assert grep(r"decline \(hand-rolled Fake, the backup\)", sec, ignore_case=True)


def test_subquestion_is_same_reply_not_followup():
    # Sibling guard to
    # test_cd_test_architecture_step4b.py::test_step_4b_asks_one_three_way_choice_with_no_second_stage,
    # which already guards the *top-level* three-way choice against a
    # reverted two-stage/follow-up-question pattern. This test guards the
    # *sub-question layer* introduced by #1435: it asserts the sub-question
    # is asked in the same reply as the top-level choice, which is
    # consistent with (not a weakening of) that existing test's guarantee —
    # both tests must stay green together; a regression to a follow-up
    # round-trip for either layer should fail its own test.
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r"asked in the same single batched prompt and reply as the "
        r"top-level three-way choice above, never a follow-up round-trip",
        sec,
        ignore_case=True,
    )


def test_subquestion_only_applies_to_build_fake_row():
    # The testcontainers and Document-only bullets carry no sub-question
    # language (no tool-selection grammar, no install/decline framing).
    testcontainers_bullet = _build_testcontainers_bullet()
    document_only_bullet = _document_only_bullet()
    for bullet in (testcontainers_bullet, document_only_bullet):
        assert not grep(r"accept the recommended", bullet, ignore_case=True)
        assert not grep(r"decline \(hand-rolled", bullet, ignore_case=True)
        assert not grep(r"<tool-name>-backed", bullet, ignore_case=True)
    # A volunteered sub-answer on either of those rows is stated to have no
    # effect.
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r"any install/decline preference volunteered for either of those "
        r"rows is ignored, not an error",
        sec,
        ignore_case=True,
    )


def test_ambiguous_sub_answer_defaults_to_install_not_decline():
    sec = collapsed(_downstream_service_branch_section())
    # Positive supporting text for the corrected default.
    assert grep(
        r"an ambiguous or absent sub-answer defaults to \(a\), installing "
        r"the recommended library",
        sec,
        ignore_case=True,
    )
    # Explicit contrast with the unchanged top-level default — both stated
    # in the same section so the two rules read as deliberately different.
    assert grep(
        r"distinct, narrower default rule from the top-level three-way "
        r"choice's own ambiguous-answer default stated above, which "
        r"remains `?Document-only`?, unchanged",
        sec,
        ignore_case=True,
    )


def test_explicit_accept_also_installs_recommended_library():
    # Named, separate regression guard for the explicit-accept path,
    # distinct from the ambiguous-defaults-to-accept test above — a future
    # change to one path must not silently break the other without a
    # failing test.
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r'an operator.s explicit-accept answer.*installs the recommended '
        r"library identically to this ambiguous/absent-answer case",
        sec,
        ignore_case=True,
    )


def test_non_interactive_run_skips_subquestion_defaults_to_document_only():
    # The #1433/#1434 non-interactive rule (skip the whole Step 4b prompt)
    # already applies to the entire prompt this sub-question is appended
    # to; this test asserts the sub-question is not carved out of that
    # rule — it lives in `### 4b.`'s shared intro, read here via the
    # top-level step4b test file's own coverage, and confirmed unaffected
    # by the Downstream-service branch's own local text (no interactive
    # exception is stated for this branch or its sub-question).
    sec = collapsed(_downstream_service_branch_section())
    assert not grep(
        r"even when non-interactive|regardless of --yes|the sub-question "
        r"is still asked",
        sec,
        ignore_case=True,
    )
    step_4b_sec = section(
        _skill_text(), r"^### 4b\.", boundary_pattern=r"^### 5\."
    )
    assert grep(
        r"--yes|DEV_TEAM_AUTO_APPROVE=1|no-TTY|no TTY", step_4b_sec, ignore_case=True
    )
    assert grep(
        r"skip the prompt entirely", step_4b_sec, ignore_case=True
    )


def test_existing_tool_detection_in_step_1_becomes_default():
    sec = collapsed(_step_1_section())
    assert grep(r"existing-tool detection", sec, ignore_case=True)
    assert grep(r"virtual-service-libraries\.md", sec)
    assert grep(
        r"becomes the default recommended tool for that component.s "
        r"`?Build \(Fake\)`? row",
        sec,
        ignore_case=True,
    )
    assert grep(r"with no switch suggested", sec, ignore_case=True)
    assert grep(
        r"inventory-phase data gathering, not a Step 4 recommendation",
        sec,
        ignore_case=True,
    )
    # Not amended into Step 4 itself — this is Step 1 inventory-phase data.
    step4_sec = section(
        _skill_text(),
        r"^### 4\. Recommend the target architecture",
        boundary_pattern=r"^### 4b\.",
    )
    assert not grep(r"existing-tool detection", step4_sec, ignore_case=True)


def test_broker_component_degrades_to_hand_rolled_when_no_library_fits():
    sec = collapsed(_downstream_service_branch_section())
    assert grep(
        r"no protocol-appropriate virtual-service library", sec, ignore_case=True
    )
    assert grep(
        r"this sub-question is not presented at all", sec, ignore_case=True
    )
    assert grep(
        r"defaults to the hand-rolled Fake Story below, with no tool name "
        r"substituted",
        sec,
        ignore_case=True,
    )


def test_tool_named_story_title_and_offgate_mechanism_named():
    bullet = _build_fake_bullet()
    assert grep(
        r"\[<component>\]\s*Add <tool-name>-backed downstream-service double",
        bullet,
    )
    assert grep(
        r"\[<component>\]\s*Add Nock-backed downstream-service double", bullet
    )
    assert grep(
        r"library.s own re-record/diff capability against the real "
        r"dependency",
        bullet,
        ignore_case=True,
    )
    assert grep(
        r"in place of a hand-rolled contract test", bullet, ignore_case=True
    )
    # Negative: guards the round-2 correction from regressing back to the
    # two-off-gate-action framing — the stale first-draft phrasing that
    # described a second, additional off-gate integration test must not
    # reappear.
    assert not grep(
        r"separate out-of-band integration test that validates the double",
        bullet,
        ignore_case=True,
    )
    assert grep(
        r"unchanged in count . still one, not a second, additional "
        r"off-gate test artifact",
        bullet,
        ignore_case=True,
    )


def test_decline_still_proposes_unmodified_hand_rolled_fake_story():
    # Explicit regression guard for the backup path (round-1 review
    # finding: don't leave this to an implicit "full suite still green"
    # assumption).
    bullet = _build_fake_bullet()
    assert grep(
        r"\[<component>\]\s*Add hand-rolled Fake downstream-service double",
        bullet,
    )
    assert grep(r"team-owned thin adapter", bullet, ignore_case=True)
    assert grep(r"test-doubles\.md", bullet)


def test_output_table_cites_tool_in_existing_double_column_no_new_column():
    sec = collapsed(cd_test_architecture_output_section(_skill_text()))
    assert grep(
        r"cite the chosen tool .*in this same `?Double \(to run "
        r"config-free\)`? column",
        sec,
        ignore_case=True,
    )
    assert grep(
        r"no new column or enum value is added for it", sec, ignore_case=True
    )
    # No new `Build/Document status` enum value was introduced.
    assert grep(r"Build \(testcontainers\)", sec)
    assert grep(r"Build \(Fake\)", sec)
    assert grep(r"Document-only", sec)


def test_knowledge_references_bullet_includes_virtual_service_libraries():
    refs_section = section(
        _skill_text(),
        r"^Grounded in these knowledge references",
        boundary_pattern=r"^## ",
    )
    assert grep(r"virtual-service-libraries\.md", refs_section)
    assert grep(
        r"Resolution order", collapsed(refs_section)
    )
