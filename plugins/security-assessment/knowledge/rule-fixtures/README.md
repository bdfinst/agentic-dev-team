# Per-rule semgrep fixtures (#124)

Each of the 36 custom semgrep rules in `../semgrep-rules/*.yaml` ships a
positive and a negative fixture here, under a directory named for the rule id:

```
rule-fixtures/<rule-id>/positive.<ext>   # MUST fire the rule
rule-fixtures/<rule-id>/negative.<ext>   # MUST NOT fire the rule
```

The file extension matches the rule's primary language (`.py`, `.js`, `.java`,
`.sh`, `.conf`, …). Positive fixtures are intentionally vulnerable — they exist
to be detected — so they are excluded from eslint.

## Measurement, not just presence

The repo-level dev tool `scripts/audit-semgrep-fixtures.py` (build/test tooling —
not shipped with the plugin) runs semgrep over these fixtures and
**measures** each rule's real behaviour (the #118 manifest audit only checked
file presence). It records the result in each rule's YAML `metadata`:

- `fp_rate: "<n>"` — measured false-positive rate = (negative fixtures that
  fired) / (negative fixtures). The policy demotes any rule whose `fp_rate`
  exceeds `0.10`.
- `semgrep_status: "parse-error" | "no-fire"` — the rule fires on **nothing**
  (semgrep can't compile it, or its pattern is too literal). These pre-existing
  rule-grammar bugs are pinned in `known-broken-rules.txt` and are #124
  follow-up fixes; they did NOT come from the fixtures.

The CI job (`semgrep-fixtures` in `plugin-tests.yml`) fails on a missing
fixture, a working rule whose negative fires (`fp_rate > 0.10`), a
non-known-broken rule that fires on nothing, or a known-broken entry that has
started working (so the list can't hide a fixed rule).

To re-measure and re-stamp after editing rules or fixtures:

```bash
python3 scripts/audit-semgrep-fixtures.py --write
```
