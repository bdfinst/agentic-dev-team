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
    cd_test_architecture_build_fake_bullet,
    cd_test_architecture_build_testcontainers_bullet,
    cd_test_architecture_document_only_bullet,
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
    return cd_test_architecture_build_testcontainers_bullet(_skill_text())


def _build_fake_bullet() -> str:
    return cd_test_architecture_build_fake_bullet(_skill_text())


def _document_only_bullet() -> str:
    return cd_test_architecture_document_only_bullet(_skill_text())


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


def test_mountebank_fallback_reason_is_stated_not_bare_assertion():
    # Fix 3(a) (ai-provenance-review, warning): "Mountebank is the closest
    # general-purpose fallback" was asserted with no stated basis. Pin the
    # one-clause reason added.
    text = collapsed(_text())
    assert grep(
        r"Mountebank is the closest general-purpose fallback . via its "
        r"generic TCP protocol support, though it has no native "
        r"AMQP/Kafka/MQTT protocol",
        text,
    )


def test_go_row_commits_to_go_vcr_as_concrete_default():
    # Fix 3(b): the `go` row was a category-plus-example, not a concrete
    # catalog default, while the Resolution order section's step 2 promises
    # "the catalog's default for the detected stack" — nothing concrete to
    # resolve to for `go` under the old hedged wording. Commit to `go-vcr`,
    # matching how the other four rows commit to a specific tool.
    sec = _catalog_section()
    assert grep(r"\|\s*`go`\s*\|\s*`go-vcr`\s*\|", sec)
    assert not grep(r"e\.g\.\s*`go-vcr`", sec, ignore_case=True)
    assert not grep(
        r"A Go-native record-and-replay library", sec, ignore_case=True
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


def test_operator_can_name_different_library():
    # Fix 8 (spec-compliance-review): the plan's Gherkin scenario "Operator
    # names a specific different library" (an operator answers "Build
    # (Fake), install WireMock" for a component whose default was a
    # different tool) had no dedicated test — only the three-valued
    # grammar's presence was checked
    # (test_sub_question_answer_grammar_is_three_valued_not_binary), not
    # that an explicit override actually takes precedence over the
    # recommended default. Distinct from the explicit-accept
    # (test_explicit_accept_also_installs_recommended_library) and
    # ambiguous-default (test_ambiguous_sub_answer_defaults_to_install_not_decline)
    # cases already covered.
    sec = collapsed(_resolution_order_section())
    assert grep(r"\*\*Operator override or decline\*\*", sec)
    assert grep(
        r"the operator names a different library \(used instead of 1 or "
        r"2\)",
        sec,
        ignore_case=True,
    )
    # The Downstream-service branch's sub-question grammar and Story shape
    # both name the override path distinctly from the default/accept paths.
    downstream_sec = collapsed(_downstream_service_branch_section())
    assert grep(r"named override", downstream_sec, ignore_case=True)
    assert grep(
        r"naming the concrete tool chosen", downstream_sec, ignore_case=True
    )


# --- Step 1.2: correct the four existing knowledge files' stale ---
# --- pre-merge guidance (mirrors #1434's                         ---
# --- test_knowledge_files_state_the_universal_out_of_band_rule    ---
# --- "citation must stay true to its source" regression pattern). ---


def _csharp_wiremock_section() -> str:
    # Scoped to the "## WireMock.Net — the preferred pre-merge double when
    # installed" section only (ai-provenance-review suggestion, Fix 5): the
    # whole-file absence checks below were broader than intended — narrowing
    # to this section means a legitimate unrelated future use of "never
    # in-band" or the round-2 regression phrasing elsewhere in the file
    # (e.g. about MockServer or Kestrel) can't false-fail these guards.
    # section() must run on the raw (line-structured) text before
    # collapsing — collapsing first destroys the line boundaries the
    # start/boundary patterns match against.
    return collapsed(
        section(
            CSHARP_REFERENCE_FILE.read_text(encoding="utf-8"),
            r"^## WireMock\.Net",
            boundary_pattern=r"^## What to avoid",
        )
    )


def _dotnet_wiremock_paragraph() -> str:
    # Scoped to the Notes paragraph carrying the WireMock.Net seam
    # discussion (Fix 5) rather than the whole (short) file. Same
    # section-before-collapse ordering as `_csharp_wiremock_section` above.
    return collapsed(
        section(
            DOTNET_PROFILE_FILE.read_text(encoding="utf-8"),
            r"\*\*Notes\.\*\*",
            boundary_pattern=r"\*\*BDD\.\*\*",
        )
    )


def test_csharp_reference_states_wiremock_preferred_not_never_in_band():
    text = collapsed(CSHARP_REFERENCE_FILE.read_text(encoding="utf-8"))
    # Positive: WireMock.Net is now named the preferred pre-merge double.
    assert grep(
        r"WireMock\.Net is the \*\*preferred\*\* pre-merge double",
        text,
    )
    # Negative: the old absolute — "never in-band" — no longer applies to
    # WireMock.Net anywhere in its own section.
    wiremock_sec = _csharp_wiremock_section()
    assert wiremock_sec.strip() != ""
    assert not grep(r"never in-band", wiremock_sec, ignore_case=True)
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
    # Scoped to the WireMock.Net section (Fix 5).
    wiremock_sec = _csharp_wiremock_section()
    assert wiremock_sec.strip() != ""
    assert not grep(
        r"WireMock\.Net (has|provides|supports|offers) an? "
        r"(in-process|no-socket|in-memory)",
        wiremock_sec,
        ignore_case=True,
    )


def test_csharp_reference_scopes_no_sockets_claim_to_hand_rolled_stub():
    # Fix 1 (ai-provenance-review, FAIL): the opening thesis's "no sockets,
    # no ports, no Kestrel" framing must describe the hand-rolled
    # StubHttpMessageHandler specifically, not the HttpMessageHandler seam
    # universally — WireMock.Net now also fills that seam via a real
    # loopback socket.
    text = collapsed(CSHARP_REFERENCE_FILE.read_text(encoding="utf-8"))
    assert grep(
        r"hand-rolled stub implementation of that seam \(below\) makes the "
        r"HTTP layer a pure function of inputs: no sockets, no ports, no "
        r"Kestrel",
        text,
    )
    assert grep(
        r"WireMock\.Net .* fills the same seam through a real loopback "
        r"HTTP server instead",
        text,
    )


def test_csharp_reference_reconciles_wiremock_loopback_vs_kestrel_anti_pattern():
    # Fix 1: the file's own "what to avoid" anti-pattern list flags
    # "Kestrel on a random port + a real HTTP request" — functionally the
    # same shape as WireMock.Net's own default self-host mechanism. This
    # test pins the honest, verifiable distinction added to reconcile the
    # two, without asserting anything about DNS/network-stack avoidance
    # that can't be verified.
    sec = _csharp_wiremock_section()
    assert grep(
        r"applies to the hand-rolled `?StubHttpMessageHandler`?, not to "
        r"this seam universally",
        sec,
    )
    assert grep(
        r"the actual network path is a real loopback HTTP request, not an "
        r"in-memory interception",
        sec,
    )
    assert grep(
        r"purpose-built stub tooling — request/response matching and "
        r"expectation configuration are its entire job", sec
    )
    assert grep(
        r"launched and torn down within the same test process lifecycle, "
        r"with no separately-managed external server or container to "
        r"configure",
        sec,
    )
    assert grep(
        r"a real loopback socket is being traded for that purpose-built "
        r"tooling and faster iteration than hand-rolling a host", sec
    )
    assert grep(
        r"not for the absence of sockets, DNS, or the network stack, "
        r"which this file does not claim WireMock\.Net avoids", sec
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
    # Negative: the old "not ... WireMock" exclusion is gone. Scoped to the
    # Notes paragraph (Fix 5) rather than the whole file.
    para = _dotnet_wiremock_paragraph()
    assert para.strip() != ""
    assert not grep(r"not\s+WireMock\b", para)


def test_dotnet_profile_states_loopback_http_request_not_in_memory_interception():
    # Fix 1: dotnet.md's "it doesn't replace the seam" claim was misleading
    # — corrected to state the same configuration point is used to point
    # the client at WireMock.Net's server URL, with the resulting call
    # being a real loopback HTTP request, cross-referencing
    # csharp-http-client-testing.md for the full reasoning.
    para = _dotnet_wiremock_paragraph()
    assert grep(
        r"same `?IHttpClientFactory`?/`?ConfigurePrimaryHttpMessageHandler`? "
        r"configuration point is used to point the client at WireMock\.Net.s "
        r"server URL",
        para,
    )
    assert grep(
        r"the resulting call is a real loopback HTTP request, not an "
        r"in-memory interception",
        para,
    )
    assert grep(r"csharp-http-client-testing\.md", para)


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


def test_sub_question_answer_grammar_is_three_valued_not_binary():
    sec = collapsed(_downstream_service_branch_section())
    assert grep(r"three-valued, not binary", sec, ignore_case=True)
    assert grep(
        r"accept the recommended virtual-service library", sec, ignore_case=True
    )
    assert grep(r"name a specific different library", sec, ignore_case=True)
    assert grep(r"decline \(hand-rolled Fake, the backup\)", sec, ignore_case=True)


def test_sub_question_is_same_reply_not_followup():
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


def test_sub_question_only_applies_to_build_fake_row():
    # The testcontainers and Document-only bullets carry no sub-question
    # language (no tool-selection grammar, no install/decline framing).
    testcontainers_bullet = _build_testcontainers_bullet()
    document_only_bullet = _document_only_bullet()
    for bullet in (testcontainers_bullet, document_only_bullet):
        # Positive companion (Fix 11): prove extraction actually reached
        # real bullet content for *this* variable before negating it — an
        # extraction failure specifically on `bullet` would otherwise go
        # undetected by the negatives below, which check a non-empty-string
        # vacuously.
        assert bullet.strip() != ""
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


def test_non_interactive_run_skips_sub_question_defaults_to_document_only():
    # The #1433/#1434 non-interactive rule (skip the whole Step 4b prompt)
    # already applies to the entire prompt this sub-question is appended
    # to; this test asserts the sub-question is not carved out of that
    # rule — it lives in `### 4b.`'s shared intro, read here via the
    # top-level step4b test file's own coverage, and confirmed unaffected
    # by the Downstream-service branch's own local text (no interactive
    # exception is stated for this branch or its sub-question).
    sec = collapsed(_downstream_service_branch_section())
    # Positive companion (Fix 11): prove `sec` is actually the sub-question's
    # own section (non-empty, on-topic) before negating it below — the
    # negatives previously had their only positive companion on a different
    # variable (`step_4b_sec`), so an extraction failure on `sec` itself
    # would have gone undetected.
    assert sec.strip() != ""
    assert grep(r"sub-question", sec, ignore_case=True)
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
    # Positive companion (Fix 11): prove `step4_sec` itself was actually
    # extracted (non-empty, reaches its own header) before negating it —
    # the prior version's only positive assertions were against `sec`
    # (Step 1's section), a different variable than the one being negated.
    assert grep(r"Recommend the target architecture", step4_sec)
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


def test_tool_named_story_title_and_off_gate_mechanism_named():
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


def test_offgate_mechanism_falls_back_to_hand_rolled_when_no_re_record_diff():
    # Fix 4 (ai-provenance-review, warning): the off-gate mechanism swap had
    # an undefined fallback branch — nothing stated what happens when the
    # chosen tool has no re-record/diff capability. Pin the corrected
    # fallback sentence: reverts to the hand-rolled provider-contract
    # verification described earlier in the same bullet, still one
    # artifact, not a second one.
    bullet = _build_fake_bullet()
    assert grep(
        r"when the chosen library has no re-record/diff capability, the "
        r"companion action reverts to the hand-rolled provider-contract "
        r"verification described earlier in this bullet",
        bullet,
        ignore_case=True,
    )
    assert grep(
        r"still one artifact, not a second one", bullet, ignore_case=True
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


# --- Fix 9 (security-review): credential-scrubbing guidance for recorded ---
# --- artifacts (cassettes/stub mappings)                                 ---


def _recorded_artifacts_section() -> str:
    return collapsed(
        section(
            _text(),
            r"^## Recorded artifacts contain real traffic",
            boundary_pattern=r"^## ",
        )
    )


def test_recorded_artifacts_scrubbing_section_exists():
    sec = _recorded_artifacts_section()
    assert sec.strip() != ""
    assert grep(
        r"treat every recorded artifact as potentially secret-bearing "
        r"until reviewed",
        sec,
        ignore_case=True,
    )
    assert grep(r"deployment-pipeline\.md", sec)
    assert grep(r"Secrets are not in version control", sec)
    assert grep(r"Configuration management", sec)


def test_recorded_artifacts_section_names_a_filtering_hook_per_tool():
    sec = _recorded_artifacts_section()
    assert grep(r"filter_headers", sec)
    assert grep(r"filter_query_parameters", sec)
    assert grep(r"before_record_response", sec)
    assert grep(r"before-save hook", sec, ignore_case=True)
    assert grep(r"manually redact", sec, ignore_case=True)
    assert grep(r"response transformers", sec, ignore_case=True)
    assert grep(r"body-capture limits", sec, ignore_case=True)


def test_recorded_artifacts_section_recommends_non_prod_target():
    sec = _recorded_artifacts_section()
    assert grep(
        r"record against a non-prod instance of the dependency, using "
        r"non-prod credentials",
        sec,
        ignore_case=True,
    )
