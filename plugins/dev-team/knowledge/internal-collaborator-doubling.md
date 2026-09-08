# Internal-Collaborator Doubling: The Blocker Rule

Reference file for `test-review`, `test-smell-review`, `test-design-advisor`,
the internal-double detector (#2127), and the authoring lane
(`software-engineer`, `qa-engineer`, `/build`, `/test-driven-development`).
This is the **single normative source** for when doubling a collaborator
declared in the project's own first-party source is admissible. Every
consumer cites this file by path; none restates it.

Source: epic #2123.

## The rule

In any test at or below the component layer, **a collaborator declared in
the project's own first-party source stays real.** A double standing in for
one is admissible only when that collaborator matches a blocker below.

There is no test-type exemption. "Solitary unit test" stops being a licence
to double everything and becomes "a unit test whose every double names a
blocker."

## The three blockers (exhaustive)

Each is a property of **the collaborator**, never of the test. A double is
the fallback in all three — making the boundary explicit and injecting it is
preferred.

| # | Blocker | Holds when | Preferred remedy before doubling |
|---|---|---|---|
| **B1** | Out-of-process handle | The collaborator holds or opens a handle beyond this process — socket, DB connection, URL, file handle, broker channel, subprocess | Double the leaf it wraps, not the collaborator |
| **B2** | Ambient state | It reads non-injectable ambient state — clock, RNG/GUID, env, hostname, cwd, locale | Inject a value or port; double only if injection is not yet available |
| **B3** | Prohibitive real cost | Real execution makes the test non-viable at this layer's speed — production-factor KDF, deliberate retry backoff, heavy computation | Parameterize the cost so the real code path still runs |

## Non-reasons (normative, so the rule is falsifiable)

None of the following, alone, is a blocker — doubling on their basis alone
is inadmissible:

- "This test isn't about X" / "I only want this branch"
- "Setup is easier" / "the double was faster to write"
- "The collaborator has its own tests"
- "It's an injected interface" — and the type's name: `*Service`, `*Client`,
  `*Provider`, `*Gateway`, `*Manager`, `*Repository` say nothing about which
  side of a boundary a type sits on
- Forcing an error path that is unreachable through the public interface —
  treat that as evidence the handling is dead or the seam is wrong, not as a
  blocker

## Patching internal functions

Reaching into a module to replace a function (`unittest.mock.patch`,
`vi.spyOn`, monkeypatching a module attribute) is the same defect in a worse
form: it needs no seam, so it applies zero design pressure and couples the
test to the callee's name and location. It is **never** admissible under
B1–B3. Where a blocker genuinely applies, extract the boundary and inject
it.

## The waiver

An admitted double carries an inline comment marker at the double site,
naming the blocker and the reason. Comments are the one mechanism every
stack has, and colocating the waiver with the double is what stops it
drifting from the code it justifies:

```
// double-waiver: B1 — SmtpGateway holds the SMTP socket
var mail = Substitute.For<ISmtpGateway>();

# double-waiver: B2 — reads the system clock
with patch("billing.clock.now") as now:

// double-waiver: B3 — Argon2 at prod work factor (~800ms)
const hasher = vi.mocked(passwordHasher)
```

**Visibility, not sign-off.** The waiver needs no separate approval step.
The author states the blocker; the reviewer challenges it like any other
line of the diff, and `test-smell-review` judges whether the claim is true.
B1 and B2 doubles are common (DB, clock, HTTP), so an approval gate on each
would make the rule a bottleneck rather than a backstop.

## A declaration never exempts

`solitary` and `sociable` both survive as vocabulary, redefined: a
**sociable** unit test uses its real collaborators; a **solitary** unit test
is one whose every double names a blocker. Neither exempts the
internal-collaborator rule, and neither does any other test-type
declaration.

This is worth stating explicitly because "solitary" historically *meant*
the exemption being removed here. Test-type declarations are **descriptive,
never permissive**.

## See also

`test-doubles.md`'s "Common Misuses" table already flags mocking a
collaborator internal to the SUT's own component as a boundary-selection
error; `component-test-patterns.md`'s core principle ("double only the
systems the team doesn't control") gestures at the same idea. This file is
the rule those two already point toward, made unconditional and mechanically
checkable.
