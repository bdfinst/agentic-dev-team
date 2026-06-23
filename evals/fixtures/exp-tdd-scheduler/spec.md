# Feature: task scheduler (`scheduler` package)

Implement a task scheduler that resolves execution order from declared
dependencies. The package exposes a `Graph` class plus ordering functions.
All public API is importable directly from `scheduler`:

```python
from scheduler import Graph, topological_order, detect_cycle, ready_tasks, CycleError
```

## Module: `scheduler/graph.py`

### `class Graph`

- `add_task(name)` — register a task by name. Idempotent: registering an
  existing task is a no-op and does not erase its dependencies.
- `add_dependency(task, depends_on)` — declare that `task` runs AFTER
  `depends_on`. If either `task` or `depends_on` is not already present, it is
  **auto-created**. A task may not depend on itself in well-formed input, but
  self-edges (if added) are treated as a cycle by the ordering functions.
- `tasks()` — return all task names as a **sorted list** (ascending, by string
  comparison).
- `dependencies(task)` — return the **direct** dependencies of `task` as a
  **sorted list**. For a task with no dependencies, return `[]`. Querying a
  task that does not exist returns `[]`.

## Module: `scheduler/order.py`

### `topological_order(graph) -> list[str]`

Return a topological ordering of **all** tasks: every task appears exactly
once, and each task appears AFTER all of its dependencies. The ordering is
**deterministic**: it is the order produced by Kahn's algorithm where, at each
step, among all currently-ready tasks (in-degree zero, not yet emitted), the
**alphabetically-smallest** task name is chosen next.

If the graph contains a cycle, raise `CycleError` (defined in `order.py`,
exported from `scheduler`).

### `detect_cycle(graph) -> list[str] | None`

Return one cycle present in the graph as a list of task names, or `None` if the
graph is acyclic (a DAG). When a cycle is returned, the listed names must form
a closed dependency loop (each consecutive pair connected by a dependency edge,
and the last connected back to the first). The exact cycle returned and its
starting point are unspecified; only the presence/absence (`None` vs non-`None`)
and that the names form a real cycle are asserted.

### `ready_tasks(graph, done: set) -> list[str]`

Return the tasks that are runnable given a set of already-completed tasks
`done`: a task is ready when it is **not** itself in `done` and **all** of its
direct dependencies are in `done`. Return the result as a list sorted
**alphabetically** (ascending).

## Deterministic scenarios

1. **Single task.** `g.add_task("a")`; `topological_order(g) == ["a"]`;
   `g.tasks() == ["a"]`; `g.dependencies("a") == []`.
2. **Linear chain order.** `a` -> `b` -> `c` (c depends on b, b depends on a).
   `topological_order(g) == ["a", "b", "c"]`.
3. **Diamond dependency order.** `d` depends on `b` and `c`; `b` and `c` each
   depend on `a`. `topological_order(g) == ["a", "b", "c", "d"]` (b before c by
   alphabetical tie-break).
4. **Alphabetical tie-break with independent tasks.** Three independent tasks
   `c`, `a`, `b` (no dependencies). `topological_order(g) == ["a", "b", "c"]`.
5. **Auto-create unknown dependency.** On an empty graph,
   `g.add_dependency("build", "compile")` auto-creates both;
   `g.tasks() == ["build", "compile"]` and
   `g.dependencies("build") == ["compile"]`.
6. **`dependencies()` accessor.** For `d` depending on `c` and `a`,
   `g.dependencies("d") == ["a", "c"]` (sorted); `g.dependencies("a") == []`;
   `g.dependencies("missing") == []`.
7. **`detect_cycle` finds a cycle.** `a` -> `b` -> `a` (mutual). `detect_cycle(g)`
   is not `None` and the returned names form a real loop.
8. **`detect_cycle` returns None on a DAG.** For the diamond of scenario 3,
   `detect_cycle(g) is None`.
9. **`topological_order` raises `CycleError` on a cycle.** For a 3-cycle
   `a` -> `b` -> `c` -> `a`, `topological_order(g)` raises `CycleError`.
10. **`ready_tasks` given a done-set.** Diamond of scenario 3: with
    `done == {"a"}`, `ready_tasks(g, {"a"}) == ["b", "c"]`; with `done == set()`,
    `ready_tasks(g, set()) == ["a"]`; with `done == {"a", "b", "c"}`,
    `ready_tasks(g, {"a", "b", "c"}) == ["d"]`.
