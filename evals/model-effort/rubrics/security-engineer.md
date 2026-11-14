# Rubric: security-engineer

A good security-engineer answer threat-models the design from the attacker's side: for each finding it names the attacker, the attack path, and the impact, rates severity directly, and pairs it with a concrete remediation. It distinguishes real risks in the design from theoretical ones and does not pad the list or flag controls that are already sound.

## Criteria

- **attacker-path-impact**: Each finding names who the attacker is, how they reach the asset, and what they gain.
- **severity-and-remediation**: Each finding carries an explicit severity and a concrete, actionable remediation.
- **design-level-focus**: Treats the input as a design to change before code exists, with no claims about specific code lines, scans, or test results that do not exist.
- **grounded-no-padding**: Every finding traces to something stated in the design document; does not invent components or list generic checklist items unrelated to the design.
- **highest-severity-summary**: Ends with a one-sentence summary naming what was assessed and the highest-severity finding.
