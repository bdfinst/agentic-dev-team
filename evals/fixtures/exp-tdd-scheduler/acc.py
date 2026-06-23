from scheduler import Graph, topological_order, detect_cycle, ready_tasks, CycleError

# Scenario 1: single task
g = Graph()
g.add_task("a")
assert topological_order(g) == ["a"]
assert g.tasks() == ["a"]
assert g.dependencies("a") == []

# Scenario 2: linear chain a -> b -> c
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "b")
assert topological_order(g) == ["a", "b", "c"]

# Scenario 3: diamond  a -> {b,c} -> d
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "a")
g.add_dependency("d", "b")
g.add_dependency("d", "c")
assert topological_order(g) == ["a", "b", "c", "d"]

# Scenario 4: alphabetical tie-break, independent tasks
g = Graph()
g.add_task("c")
g.add_task("a")
g.add_task("b")
assert topological_order(g) == ["a", "b", "c"]

# Scenario 5: auto-create unknown dependency
g = Graph()
g.add_dependency("build", "compile")
assert g.tasks() == ["build", "compile"]
assert g.dependencies("build") == ["compile"]

# Scenario 6: dependencies() accessor
g = Graph()
g.add_dependency("d", "c")
g.add_dependency("d", "a")
assert g.dependencies("d") == ["a", "c"]
assert g.dependencies("a") == []
assert g.dependencies("missing") == []

# Scenario 7: detect_cycle finds a cycle  a <-> b
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("a", "b")
cyc = detect_cycle(g)
assert cyc is not None
assert set(cyc) == {"a", "b"}

# Scenario 8: detect_cycle returns None on a DAG (diamond)
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "a")
g.add_dependency("d", "b")
g.add_dependency("d", "c")
assert detect_cycle(g) is None

# Scenario 9: topological_order raises CycleError on a 3-cycle a->b->c->a
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

# Scenario 10: ready_tasks given a done-set (diamond)
g = Graph()
g.add_dependency("b", "a")
g.add_dependency("c", "a")
g.add_dependency("d", "b")
g.add_dependency("d", "c")
assert ready_tasks(g, set()) == ["a"]
assert ready_tasks(g, {"a"}) == ["b", "c"]
assert ready_tasks(g, {"a", "b", "c"}) == ["d"]

print("OK")
