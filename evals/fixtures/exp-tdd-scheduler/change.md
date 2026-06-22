# Change: task priorities and task removal

Modify the scheduler so that ready tasks are ordered by **priority first**, then
alphabetically. This changes the tie-break rule used in both `topological_order`
and `ready_tasks`.

## `scheduler/graph.py`

- `add_task(name, priority=0)` — tasks now carry an integer priority,
  defaulting to `0`. Re-adding an existing task **with a new priority updates**
  the stored priority (dependencies are preserved). Auto-created tasks (via
  `add_dependency`) get priority `0`.
- Add `priority(name)` — return the stored priority of `name` (or `0` if the
  task is unknown).
- Add `remove_task(name)` — remove `name` from the graph and remove any
  dependency edges that reference it (both edges where `name` is the dependent
  and edges where `name` is a dependency of another task). Removing an unknown
  task is a no-op. After removal, `name` must not appear in `tasks()` and must
  not appear in any other task's `dependencies(...)`.

## `scheduler/order.py`

Change the selection rule in both `topological_order` and `ready_tasks`: among
the candidate tasks (ready / in-degree zero), choose the one with the
**highest priority** first; ties between equal priorities are broken
**alphabetically** (ascending). The data structure and the result type are
unchanged — only the ordering among simultaneously-available tasks changes.

`detect_cycle` and `CycleError` behavior is unchanged.

## Invariants preserved

- When all tasks share the same priority (e.g. all default `0`),
  `topological_order` and `ready_tasks` produce exactly the same alphabetical
  ordering as before this change.
- A task still always appears after all of its dependencies (priority only
  reorders tasks that are simultaneously available).
- Cycle detection and `CycleError` are unaffected.
