# Unit test: codebase-recon equivalence

**Reference counterpart**: `agents/scan-00-codebase-recon.md` (prompt spec)
**Our counterpart**: `plugins/agentic-dev-team/agents/codebase-recon.md` (opus agent)

Asserts that given the same target repo, both agents produce RECON output with
the same key facts — even though the reference emits free-form markdown and
we emit schema-conformant JSON + a markdown narrative.

---

## Inputs

- Target repo: `evals/codebase-recon/fixtures/ts-monorepo/`
- Second target: `evals/codebase-recon/fixtures/polyglot/`

## Outputs compared

| Reference output | Our output |
|---|---|
| `opus_repo_scan_test/repos/ts-monorepo/RECON.md` (prompt manually run) | `memory/recon-ts-monorepo.{md,json}` |

## Equivalence assertions

For each target, both outputs MUST assert:

### Monorepo detection
- **ts-monorepo**: both identify as monorepo with `packages/core` and `packages/api` workspaces.
- **polyglot**: both identify as NOT a monorepo.

### Package manager
- **ts-monorepo**: both identify `npm`.
- **polyglot**: both identify either `npm` or `mixed` (Python + Node present).

### Entry points (minimum set that both must include)
- **ts-monorepo**:
  - `packages/api/src/server.ts` → classified as HTTP server (matching phrase: "app.listen" / "http-server" / "HTTP entry")
  - `packages/core/src/index.ts` → classified as module / library entry / main
- **polyglot**:
  - `backend/app.py` → HTTP server (FastAPI decorator evidence)
  - `scripts/deploy.sh` → CLI / script (shebang evidence)

### Language detection
- **ts-monorepo**: TypeScript dominates.
- **polyglot**: Python + TypeScript + Shell all present.

### Security surface
- **ts-monorepo**: both surface `packages/api/src/routes/auth.ts` as auth-path.
- **polyglot**: both surface `backend/app.py` as having crypto call (hashlib) + outbound network (httpx).

### Git history
- Both tools should note whether a `.env.example` or similar secret-named file
  is present in the current tree. (For fixtures without git init, both may
  return "no git history" — equivalence here is that both handle the
  non-git case gracefully.)

---

## Scoring rubric

| Category | Weight | Pass criterion |
|---|---|---|
| Monorepo detection | 1.0 | Both agree on boolean + same workspaces list |
| Package manager | 0.5 | Both agree within {npm, pnpm, yarn, mixed} |
| Entry points | 2.0 | Both include the minimum set above (false negatives weigh heavy) |
| Language detection | 1.0 | Both include the expected dominant language |
| Security surface | 1.5 | Both include at least 80% of expected auth-paths / crypto-calls |
| Git history handling | 0.5 | Both handle non-git fixture without crashing |

Total weight: 6.5. Equivalence passes at ≥ 85% agreement (5.5+).

---

## Running the test

### Step 1: Capture reference output (one-time per fixture change)

From the reference repo:

```bash
cd /Users/finsterb/Downloads/opus_repo_scan_test-main
mkdir -p repos/
cp -r /path/to/agentic-dev-team/evals/codebase-recon/fixtures/ts-monorepo repos/
# Open Claude Code in that directory; invoke the scan-00 agent per its spec
# against repos/ts-monorepo/. Save the output as results/scans/RECON-ts-monorepo.md.
# Archive under evals/comparative/reference-baseline/<date>/recon-ts-monorepo.md
```

### Step 2: Capture our output

```bash
cd /Users/finsterb/_git-os/agentic-dev-team
# Invoke codebase-recon via Agent dispatch against the same fixture.
# Output lands in memory/recon-ts-monorepo.json + .md
```

### Step 3: Compare

Currently manual — inspect both outputs for each assertion above. Future
automation: add a `score-recon.py` that greps both outputs for the minimum
set of file paths + keywords.

---

## Known divergences (expected, not failures)

1. **Rationale verbosity**: the reference emits prose paragraphs; we emit a
   `rationale` field per entry point. Same semantic content, different format.
2. **Numeric counts**: the reference may emit "5 source files" where we emit
   `languages[0].file_count: 5`. Same fact.
3. **Git-history depth**: the reference looks at full git log; we cap at
   30-day recency + sensitive-file history. Expected divergence on repos
   with long history.
4. **Security surface breadth**: we include `ml_models_loaded` and
   `csp_headers` which the reference doesn't. Our schema is a superset.
