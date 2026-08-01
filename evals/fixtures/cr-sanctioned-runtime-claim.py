"""Utilities for maintaining a sorted list of scores.

Runtime probe (2026-08-01, CPython 3.10.20), exact reproducible commands and
their real output. Each loop body inserts a random value and then pops it
back out **by its own bisected position** (`i = bisect.bisect_left(scores,
x); bisect.insort(scores, x); scores.pop(i)`) — not `scores.pop()` with no
argument, which would remove the list's current maximum instead of the
value just inserted; a first version of this probe used that form, and
after enough loops the list's maximum drifts toward whatever's easiest to
remove immediately, degenerating the timed operation into an O(1)
append+pop and invalidating the size comparison (caught in review):

    $ python3 -m timeit -s "import bisect, random; random.seed(0); scores = sorted(random.sample(range(10000), 1000))" "x = random.randint(0, 10000); i = bisect.bisect_left(scores, x); bisect.insort(scores, x); scores.pop(i)"
    500000 loops, best of 5: 945 nsec per loop

    $ python3 -m timeit -s "import bisect, random; random.seed(0); scores = sorted(random.sample(range(100000), 10000))" "x = random.randint(0, 100000); i = bisect.bisect_left(scores, x); bisect.insort(scores, x); scores.pop(i)"
    100000 loops, best of 5: 3.22 usec per loop

    $ python3 -m timeit -s "import bisect, random; random.seed(0); scores = sorted(random.sample(range(1000000), 100000))" "x = random.randint(0, 1000000); i = bisect.bisect_left(scores, x); bisect.insort(scores, x); scores.pop(i)"
    10000 loops, best of 5: 28.4 usec per loop

Each 10x step in n costs far more than O(log n) alone predicts (log2(1000)=10
-> log2(10000)=13.3, a 1.3x step, vs the measured 3.4x; log2(10000)=13.3 ->
log2(100000)=16.6, a 1.25x step, vs the measured 8.8x) — consistent with the
list-shift insertion step dominating the O(log n) search, as documented
below. The growth isn't a clean linear fit to n itself (real allocator/cache
behavior, not a pure asymptotic curve), so the claim below is stated as
"O(n) dominates the search", not as a precise measured constant. Each timed
loop also performs TWO O(n) list-shift operations, not one — the insort
insert and the compensating pop(i) removal — so the absolute per-loop
figures above are roughly double a single insort call's real cost; it's the
*ratios* across n, not the absolute nanosecond values, that the claim below
rests on.
"""

import bisect


def record_score(scores, value):
    """Insert ``value`` into the sorted list ``scores``, keeping it sorted.

    Uses ``bisect.insort``: the search is O(log n), but the insertion step
    that shifts later elements to make room is O(n) — see the module
    docstring's timeit probe. Overall this call is O(n), not O(log n).
    """
    bisect.insort(scores, value)
    return scores
