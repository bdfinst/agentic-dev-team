# cross-repo-synthesizer — rationale and provenance

## Why this agent exists

Static-analysis findings are per-file. Business-logic-domain-review is
per-repo. But the most consequential security risks often span service
boundaries: a shared credential discovered in three services, a NATS
subject with no auth that reaches a privileged handler, a model-scoring
service that trusts a client that trusts another client.

This agent reads aggregated data from multiple repos and names those
cross-repo attack chains explicitly.

## Chain meaningfulness threshold

A chain is meaningful when ≥ 2 repos are involved AND the chain advances
the attacker's position (gains data, gains execution, gains privilege).
Anything shorter is a single-repo finding; anything that doesn't advance
position is a curiosity, not an attack chain.

## Citation discipline

Every chain cites findings by rule_id + file:line. Chains without live
finding evidence are not emitted. The cross-repo-summary report is only
as trustworthy as its smallest citation; speculative chains undermine the
whole report.

## Why no individual ownership claims

Recommendations name roles ("platform team", "service X maintainers") not
people. Cross-repo work crosses team boundaries; naming individuals
creates accountability friction that the executive report should not be
the source of.
