## Slices
### Slice A: Foundation
**Depends-on:** none
**Files:** `a.ts`
### Slice B: Left
**Depends-on:** A
**Files:** `b.ts`
### Slice C: Right
**Depends-on:** A
**Files:** `c.ts`
### Slice D: Join
**Depends-on:** B, C
**Files:** `d.ts`
