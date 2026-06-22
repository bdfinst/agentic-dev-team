from scheduler import Graph, topological_order, detect_cycle, ready_tasks, CycleError

# --- Change: priorities reorder simultaneously-available tasks ---

# Higher priority goes first among independent (ready) tasks.
g = Graph()
g.add_task("a", priority=1)
g.add_task("b", priority=5)
g.add_task("c", priority=3)
assert topological_order(g) == ["b", "c", "a"]
assert ready_tasks(g, set()) == ["b", "c", "a"]

# Priority only reorders within a "ready" group; deps still respected.
# diamond: a -> {b,c} -> d, with c higher priority than b.
g = Graph()
g.add_task("b", priority=1)
g.add_task("c", priority=9)
g.add_dependency("b", "a")
g.add_dependency("c", "a")
g.add_dependency("d", "b")
g.add_dependency("d", "c")
assert topological_order(g) == ["a", "c", "b", "d"]
assert ready_tasks(g, {"a"}) == ["c", "b"]

# Equal priority -> alphabetical tie-break.
g = Graph()
g.add_task("c", priority=2)
g.add_task("a", priority=2)
g.add_task("b", priority=2)
assert topological_order(g) == ["a", "b", "c"]

# priority() accessor: stored, updated, default for unknown.
g = Graph()
g.add_task("x", priority=7)
assert g.priority("x") == 7
g.add_task("x", priority=2)  # update preserves task, changes priority
assert g.priority("x") == 2
assert g.priority("unknown") == 0

# Re-adding a task with new priority preserves its dependencies.
g = Graph()
g.add_dependency("t", "dep")
g.add_task("t", priority=4)
assert g.dependencies("t") == ["dep"]
assert g.priority("t") == 4

# remove_task removes the task and all edges referencing it.
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "a")
g.add_dependency("c", "b")
g.remove_task("b")
assert "b" not in g.tasks()
assert g.dependencies("c") == ["a"]  # edge c->b gone, c->a remains
assert g.dependencies("b") == []     # removed task has no deps
g.remove_task("zzz")  # unknown is a no-op
assert g.tasks() == ["a", "c"]

# --- Regression: all-equal priority yields the SAME alphabetical order as Stage 1 ---

# Linear chain (Stage-1 scenario 2) unchanged with default priorities.
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "b")
assert topological_order(g) == ["a", "b", "c"]

# Diamond (Stage-1 scenario 3) unchanged with default priorities.
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "a")
g.add_dependency("d", "b")
g.add_dependency("d", "c")
assert topological_order(g) == ["a", "b", "c", "d"]
assert ready_tasks(g, {"a"}) == ["b", "c"]

# --- Regression: cycle detection unchanged ---

g = Graph()
g.add_dependency("b", "a")
g.add_dependency("a", "b")
assert detect_cycle(g) is not None

g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "b")
g.add_dependency("a", "c")
try:
    topological_order(g)
    raised = False
except CycleError:
    raised = True
assert raised

g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "a")
assert detect_cycle(g) is None

print("OK")
