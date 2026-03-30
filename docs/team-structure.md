# Team Organization

## Team Agents

```mermaid
graph TD
    CO[Orchestrator] --> SE[Software Engineer]
    CO --> DS[Data Scientist]
    CO --> AR[Architect]
    CO --> QA[QA/SQA Engineer]
    CO --> UX[UI/UX Designer]
    CO --> PM[Product Manager]
    CO --> TW[Technical Writer]
    CO --> SecE[Security Engineer]
    CO --> DO[DevOps/SRE Engineer]
    CO --> KC[Knowledge Capture]
    CO --> ADR[ADR Author]

    SE <--> QA
    SE <--> AR
    SE <--> UX
    DS <--> SE
    PM <--> CO
    AR <--> SE
    TW <--> PM
    TW <--> SE
    SecE <--> AR
    SecE <--> QA
    DO <--> AR
    DO <--> SE
    DO <--> SecE
    KC <--> SE
    ADR <--> AR
```

## Review Agent Dispatch (Phase 3 Inline Checkpoints)

The orchestrator selects review agents based on what changed in each unit of work.

```mermaid
flowchart LR
    CO[Orchestrator\nModel Routing] -->|All changes| R0[spec-compliance-review\nsonnet]
    R0 -->|pass| QUALITY[Quality Gate]
    R0 -->|fail| FB

    QUALITY -->|JS/TS functions| R1[complexity-review\nhaiku]
    QUALITY -->|JS/TS functions| R2[naming-review\nhaiku]
    QUALITY -->|JS/TS functions| R3[js-fp-review\nsonnet]
    QUALITY -->|Test files| R4[test-review\nsonnet\n← QA delegates]
    QUALITY -->|API / auth| R5[security-review\nopus]
    QUALITY -->|Domain logic| R6[domain-review\nopus]
    QUALITY -->|UI components| R7[a11y-review\nsonnet]
    QUALITY -->|All changes| R8[structure-review\nsonnet]

    R1 & R2 & R3 & R4 & R5 & R6 & R7 & R8 --> AGG{Aggregate\nFindings}
    AGG -->|pass / warn| CONT([Continue])
    AGG -->|fail| FB[Correction Context\n→ Coding Agent]
    FB -->|max 2 iterations| AGG
    FB -->|still fail after 2| HU([Escalate to Human])
```
