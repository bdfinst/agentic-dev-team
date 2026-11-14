# Context

- PayGate is a third-party provider. They publish no contract-testing support
  and will not run our consumer tests.
- PayGate offers a sandbox environment with test card numbers.
- Nobody has tested what happens on a provider 5xx or a timeout; the 5xx
  branch has never executed in any test.
- The team wants these tests in the pre-merge gate.
