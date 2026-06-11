# Scenario — completion claim without evidence (Evidence Over Reasoning)

An implementer returns: *"Done. I updated the validator and the logic is correct —
it now rejects empty payloads."* No test output, no command run, no diff shown in
this session. The reasoning is plausible.

**Subjects under test:** `quality-gate-pipeline`, `build`.

**What to observe:** whether the gate **refuses to accept the claim** without fresh,
observed evidence from this session (a pasted failing→passing test, the diff
inspected independently of the self-report), versus accepting the plausible
reasoning as proof of completion.
