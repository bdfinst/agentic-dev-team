# System test design: orders

## Scope

- Mode: --overlap-only
- orders: named
- Evidence: orders had no coverage or mutation evidence (static-judgment: missing)
- Alias map: none
- External boundaries: none
- Commit: abc1234

## Current test architecture

No findings.

## Test-double validation

No findings.

## Overlap and misplacement

Pairs reported: 20 of the pairs found in module src/m.py (capped at 20; the rest are not shown).

| Test | Behavior | Also asserted by | Owning type | Action |
|---|---|---|---|---|
| tests/unit/test_m.py::test_f0 | f0 | tests/component/test_m_api.py::test_f0 | unit | trim the component test |
| tests/unit/test_m.py::test_f1 | f1 | tests/component/test_m_api.py::test_f1 | unit | trim the component test |
| tests/unit/test_m.py::test_f2 | f2 | tests/component/test_m_api.py::test_f2 | unit | trim the component test |
| tests/unit/test_m.py::test_f3 | f3 | tests/component/test_m_api.py::test_f3 | unit | trim the component test |
| tests/unit/test_m.py::test_f4 | f4 | tests/component/test_m_api.py::test_f4 | unit | trim the component test |
| tests/unit/test_m.py::test_f5 | f5 | tests/component/test_m_api.py::test_f5 | unit | trim the component test |
| tests/unit/test_m.py::test_f6 | f6 | tests/component/test_m_api.py::test_f6 | unit | trim the component test |
| tests/unit/test_m.py::test_f7 | f7 | tests/component/test_m_api.py::test_f7 | unit | trim the component test |
| tests/unit/test_m.py::test_f8 | f8 | tests/component/test_m_api.py::test_f8 | unit | trim the component test |
| tests/unit/test_m.py::test_f9 | f9 | tests/component/test_m_api.py::test_f9 | unit | trim the component test |
| tests/unit/test_m.py::test_f10 | f10 | tests/component/test_m_api.py::test_f10 | unit | trim the component test |
| tests/unit/test_m.py::test_f11 | f11 | tests/component/test_m_api.py::test_f11 | unit | trim the component test |
| tests/unit/test_m.py::test_f12 | f12 | tests/component/test_m_api.py::test_f12 | unit | trim the component test |
| tests/unit/test_m.py::test_f13 | f13 | tests/component/test_m_api.py::test_f13 | unit | trim the component test |
| tests/unit/test_m.py::test_f14 | f14 | tests/component/test_m_api.py::test_f14 | unit | trim the component test |
| tests/unit/test_m.py::test_f15 | f15 | tests/component/test_m_api.py::test_f15 | unit | trim the component test |
| tests/unit/test_m.py::test_f16 | f16 | tests/component/test_m_api.py::test_f16 | unit | trim the component test |
| tests/unit/test_m.py::test_f17 | f17 | tests/component/test_m_api.py::test_f17 | unit | trim the component test |
| tests/unit/test_m.py::test_f18 | f18 | tests/component/test_m_api.py::test_f18 | unit | trim the component test |
| tests/unit/test_m.py::test_f19 | f19 | tests/component/test_m_api.py::test_f19 | unit | trim the component test |

### Layer overlap (trim, not remove)

- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f0 + tests/component/test_m_api.py::test_f0 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f1 + tests/component/test_m_api.py::test_f1 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f2 + tests/component/test_m_api.py::test_f2 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f3 + tests/component/test_m_api.py::test_f3 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f4 + tests/component/test_m_api.py::test_f4 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f5 + tests/component/test_m_api.py::test_f5 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f6 + tests/component/test_m_api.py::test_f6 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f7 + tests/component/test_m_api.py::test_f7 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f8 + tests/component/test_m_api.py::test_f8 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f9 + tests/component/test_m_api.py::test_f9 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f10 + tests/component/test_m_api.py::test_f10 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f11 + tests/component/test_m_api.py::test_f11 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f12 + tests/component/test_m_api.py::test_f12 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f13 + tests/component/test_m_api.py::test_f13 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f14 + tests/component/test_m_api.py::test_f14 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f15 + tests/component/test_m_api.py::test_f15 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f16 + tests/component/test_m_api.py::test_f16 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f17 + tests/component/test_m_api.py::test_f17 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f18 + tests/component/test_m_api.py::test_f18 | severity suggestion; candidate; confirm with coverage before trimming
- [evidence: static-judgment; evidence-confidence: low; basis: missing] Cross-Layer Overlap | tests/unit/test_m.py::test_f19 + tests/component/test_m_api.py::test_f19 | severity suggestion; candidate; confirm with coverage before trimming

## Contract-test findings

No findings.

## Test improvements

No findings.

## Open questions

No findings.

Recommendations only; no tests were changed.
