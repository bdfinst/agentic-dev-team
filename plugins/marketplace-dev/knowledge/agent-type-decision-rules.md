# Agent Type Decision Rules — markdown vs script

The single source of truth for deciding whether a plugin capability should be a
**markdown** unit (an LLM-interpreted `.md` agent or `SKILL.md` that Claude reads
and reasons over) or a **script** unit (a deterministic `*.sh` / `*.py` helper the
plugin executes). Two entry points read this file:

- **`/agent-type-advisor`** — forward-looking: recommends a type for a prose
  use-case, or audits an existing agent/skill file for a mismatch.
- **`plugin-best-practices-review`** — retrospective: flags a shipped unit whose
  type contradicts these rules.

Keep both honest by citing **rule IDs** (`R1`–`R10`) from this file rather than
restating the reasoning. When the matrix changes, change it here once.

---

## Core distinction

| | **markdown** (LLM unit) | **script** (deterministic unit) |
|---|---|---|
| Runs by | Claude reading and reasoning | the shell / interpreter |
| Cost | tokens per invocation | free (no model call) |
| Output | varies with phrasing/context | identical for identical input |
| Strength | judgment, synthesis, NL understanding | speed, reproducibility, gating |
| Tests | eval fixtures (graded, fuzzy) | unit tests (exact assertions) |

The guiding question: **does this task need judgment, or is it mechanical?**
Judgment → markdown. Mechanical → script. The rules below make the boundary
precise and name the tie-breakers.

---

## Decision rules

### Prefer **script** when…

- **R1 — Deterministic check.** The same input must always yield the same
  output. Field presence, format/schema validation, pattern matching, and
  version-sync checks are reproducible by definition; an LLM only adds variance.
- **R2 — Mechanical transformation.** A well-defined text/file transform
  (regex substitution, JSON/YAML edit, templated file generation) has one
  correct result. A script is the specification; markdown is a paraphrase of it.
- **R3 — Merge / CI gate.** Anything that blocks a merge must be model-free,
  fast, and flake-free so the result is reproducible and auditable. Gating logic
  belongs in a script wired into CI, not in an agent that may answer differently
  on a re-run.
- **R4 — High-frequency / hot path.** Work that runs on every commit, every PR,
  or in a tight loop should not spend tokens or model latency each time. If it
  can be a script, it should be.
- **R5 — Expressible as a query.** If the logic reduces to a regex, an AST walk,
  a `jq` filter, or a table lookup, it is mechanical — reserve the model for what
  genuinely cannot be expressed that way.

### Prefer **markdown** when…

- **R6 — Semantic judgment.** The task requires understanding intent, design
  quality, naming, or domain meaning — things with no single mechanical answer.
  "Is this abstraction leaky?" is judgment; "does this field exist?" is not.
- **R7 — Synthesis or natural-language output.** Producing prose, explanations,
  reviews, recommendations, or summaries from unstructured input is an LLM task.
- **R8 — Context-adaptive routing.** Orchestration that inspects a situation and
  decides *what to do next* — dispatching agents, selecting skills, adapting to
  the repo — needs reasoning a fixed script cannot encode.
- **R9 — Open-ended / under-specified input.** When the input space is too varied
  to enumerate (arbitrary code, free-form requests), markdown handles the long
  tail a script's branches never will.

### Hybrid

- **R10 — Split mechanical from judgment.** When a task has both a deterministic
  detection step and a judgment step, do the detection in a **script** and the
  triage/explanation in **markdown** (e.g., a script enumerates surviving
  mutants or lint hits; an agent classifies and explains them). The value of the
  LLM is the triage, not the enumeration. A unit that does *only* enumeration but
  ships as markdown is a mismatch under R1; one that does *only* triage but ships
  as a script is a mismatch under R6.

---

## Applying the rules to an existing file

A unit's **observable behavior** decides its type, not its file extension:

1. Identify the unit's job from its body (what does it actually produce?).
2. If the job is purely mechanical (R1–R5) but the unit is markdown → it should
   be a **script** (recommend `CHANGE`).
3. If the job needs judgment (R6–R9) but is implemented as a rigid,
   no-reasoning script → it should be **markdown** (recommend `CHANGE`).
4. If the body interleaves mechanical enumeration with genuine judgment, R10
   applies — the mechanical half should be extracted to a script, but a markdown
   unit that *delegates* enumeration to a script it calls is already correct
   (recommend `KEEP`).
5. Otherwise the type matches the job → `KEEP`.

A review agent (JSON output, deterministic-looking checks) is still legitimately
**markdown** when its checks require reading code and exercising judgment a regex
cannot (R6) — the JSON shape is an output contract, not evidence of a mechanical
task. Do not flag a judgment-bearing review agent as "should be a script" on the
strength of its structured output alone.

---

## Confidence

Report a confidence level with every recommendation:

- **high** — the job sits squarely in one column; ≥2 rules point the same way and
  none point the other.
- **medium** — the dominant rules point one way but a secondary rule pulls the
  other (e.g., judgment task that also runs in CI), or the file's job is only
  partly determinable from its body.
- **low** — genuinely mixed (R10 territory) or the input is too vague to classify;
  state what additional detail would raise confidence.
