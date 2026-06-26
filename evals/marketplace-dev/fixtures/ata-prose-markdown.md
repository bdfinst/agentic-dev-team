# Use-case: abstraction-leak reviewer

We want a capability that reads a changed source file and judges whether its
public interface leaks implementation details — infrastructure types surfacing
in a domain API, transport concerns bleeding into business logic, names that
expose how rather than what. It produces a prose explanation of each leak, why
it matters for this domain, and a suggested boundary.

The answer depends on reading the code's intent and the surrounding domain
language; two reasonable reviewers might disagree on borderline cases. There is
no single mechanical rule that decides "this abstraction leaks."
