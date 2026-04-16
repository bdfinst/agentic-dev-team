# Root-Cause Tracing

## When to Use

The failure involves a wrong value, unexpected state, or incorrect output at the point of use. You can see *what* is wrong but not *why*.

## Technique: Backward Call-Chain Analysis

Start at the symptom — the wrong value, the error, the unexpected state — and trace backward through the call chain.

### Steps

1. **Identify the symptom point.** Where exactly does the wrong value appear? Note the file, line, and variable.
2. **Ask: who set this value?** Find the assignment, return statement, or function call that produced it. Read that code.
3. **Verify the input at that layer.** Is the input to this function/method correct? Add a log or breakpoint to confirm.
   - If the input is **correct** but the output is wrong: the bug is in this layer. Investigate the transformation logic.
   - If the input is **already wrong**: move one layer upstream and repeat from step 2.
4. **Repeat until you find the divergence point** — the first layer where the actual value differs from the expected value. That is your root cause location.

### Key Principle

Symptoms appear downstream of root causes. A wrong value in the UI was produced by a wrong value in the service layer, which was produced by a wrong query, which was produced by a wrong parameter. Always trace upstream — never fix at the symptom.

### Common Divergence Points

- **Data entry**: Wrong default, missing validation, type coercion
- **Data transformation**: Off-by-one, wrong field mapping, null handling
- **Data retrieval**: Stale cache, wrong query filter, missing join
- **Configuration**: Environment-specific value, missing override, wrong precedence

### Anti-Pattern

Do not start by reading the entire codebase looking for "something wrong." Start at the symptom and follow the chain. The call chain is your map.
