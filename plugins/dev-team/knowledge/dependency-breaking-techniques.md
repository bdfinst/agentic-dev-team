# Dependency-Breaking Techniques

Reference file for the `legacy-code` skill, the `test-design-advisor` skill, and the `test-smell-review` agent. When code can't be placed in a test harness, you need a **seam** — a place to substitute a collaborator or behavior without rewriting the code. This is the full catalog of behavior-preserving moves that *create* such a seam, so you can get legacy code under test before changing it.

Source: Michael Feathers, *Working Effectively with Legacy Code* (2005), Ch. 25 *Dependency-Breaking Techniques* (plus the Sprout/Wrap moves from Ch. 6). Language-agnostic; some techniques are specific to a language family and are marked.

Core principle: **break the smallest dependency that gets the code under test, and preserve behavior while doing it.** Every break is temporary scaffolding — once tests exist, refactor toward a real design (constructor injection, ports). Prefer the lowest-risk technique that works; reach for `Extract Method` first when nothing else presents a seam.

See `legacy-code` (the procedure: Legacy Code Change Algorithm, seam types, characterization tests), `legacy-test-strategy.md` (where to test — effect reasoning, pinch points), and `testability-patterns.md` (the *target* design these scaffold toward).

---

## How to choose

```
What is blocking the test?
├─ A collaborator created INSIDE the class/method
│   ├─ created in the constructor → Parameterize Constructor / Supersede Instance Variable
│   ├─ created in a method        → Parameterize Method / Extract and Override Factory Method
│   └─ obtained via a call        → Extract and Override Call / Extract and Override Getter
│
├─ A concrete TYPE you can't substitute
│   └─ Extract Interface / Extract Implementer, then Subclass and Override Method
│
├─ A GLOBAL / singleton / static
│   └─ Encapsulate Global References · Replace Global Reference with Getter ·
│      Introduce Static Setter · Introduce Instance Delegator
│
├─ The class is too big / method too long to instantiate or run
│   └─ Sprout Method/Class · Wrap Method/Class · Break Out Method Object · Expose Static Method
│
├─ A parameter you can't construct or sense through
│   └─ Adapt Parameter · Primitivize Parameter · Pull Up Feature · Push Down Dependency
│
└─ Procedural / compiled / interpreted language with few OO seams
    └─ Link Substitution · Replace Function with Function Pointer ·
       Definition Completion · Template Redefinition · Text Redefinition
```

---

## The catalog

### Add behavior without touching the untested code (Ch. 6)

| Technique | What it does | Seam | Risk |
|-----------|-------------|------|------|
| **Sprout Method** | Put new behavior in a new method, call it from the existing one | object | low |
| **Sprout Class** | Put new behavior (needing its own state/logic) in a new class, call into it | object | low–med |
| **Wrap Method** | Rename the original, add a new method that calls it plus the new behavior | object | low |
| **Wrap Class** | A new class (decorator) wraps the original; callers see the new behavior transparently | object | medium |

### Break a created/obtained collaborator

| Technique | What it does | Seam | Risk |
|-----------|-------------|------|------|
| **Parameterize Constructor** | Move a constructor-created dependency to a constructor parameter | object | low |
| **Parameterize Method** | Pass in an object a method creates internally, rather than `new`-ing it | object | low |
| **Extract and Override Call** | Move a problem call into its own method, override it in a test subclass | object | low |
| **Extract and Override Factory Method** | Move `new` out of a constructor into an overridable factory method | object | medium |
| **Extract and Override Getter** | Serve a dependency through a getter, override it to return a fake (C++ where factory-method override is unsafe) | object | medium |
| **Supersede Instance Variable** | Add a setter to replace an instance variable built in the constructor (when override isn't viable) | object | medium |

### Substitute a type

| Technique | What it does | Seam | Risk |
|-----------|-------------|------|------|
| **Extract Interface** | Pull an interface off a concrete class so a fake can implement it. The safest OO break — the compiler catches missteps | object | low |
| **Extract Implementer** | The inverse rename: keep the interface name, rename the class to the implementer | object | low |
| **Subclass and Override Method** | Subclass the real class in the test and override the seam method. The core OO technique — many others are variations | object | medium |

### Tame globals, singletons, and statics

| Technique | What it does | Seam | Risk |
|-----------|-------------|------|------|
| **Encapsulate Global References** | Gather references to a global behind a class you can fake or relink | object/link | medium |
| **Replace Global Reference with Getter** | Read a global through an overridable getter instead of directly | object | low |
| **Introduce Static Setter** | Add a setter so a singleton's instance can be replaced in tests | object | medium |
| **Introduce Instance Delegator** | Add instance methods that delegate to static ones, so callers can be given a fake | object | low |
| **Expose Static Method** | Promote logic that uses no instance state to a static method you can test without instantiating | — | low |

### Work around hard parameters and big methods

| Technique | What it does | Seam | Risk |
|-----------|-------------|------|------|
| **Adapt Parameter** | Wrap a hard-to-fake parameter type behind a narrow interface you control | object | medium |
| **Primitivize Parameter** | Add a free function that does the work against primitive data, called by a thin method — a temporary step toward a real test | object | medium |
| **Break Out Method Object** | Move a long method into its own class whose fields are the locals/params, so it can be instantiated and tested | object | medium |
| **Pull Up Feature** | Pull the cluster you need to test into an abstract superclass, away from the problem dependencies | object | medium |
| **Push Down Dependency** | Push the problem dependencies down into a new subclass, leaving a testable abstract parent | object | medium |

### Non-OO / compiled / interpreted seams

| Technique | What it does | Seam | Risk |
|-----------|-------------|------|------|
| **Link Substitution** | Link the test against an alternative implementation of a library/object | link | medium |
| **Replace Function with Function Pointer** | Indirect a function call through a pointer you can repoint in tests (C) | link | medium |
| **Definition Completion** | Provide a test-only definition for a header-declared function/class (C/C++) | preprocessing | high |
| **Template Redefinition** | Substitute a dependency's type via a template parameter at compile time (C++) | preprocessing | medium |
| **Text Redefinition** | Redefine a method's body at run time in a dynamic language (Ruby, etc.) | preprocessing | medium |

---

## Most common in practice

The legacy-code skill keeps a shortlist for the day-to-day cases; the rest of the catalog is here when those don't fit. The everyday set: **Extract Interface**, **Parameterize Constructor**, **Subclass and Override Method**, **Extract and Override Call/Factory Method**, **Sprout/Wrap Method**, and **Adapt Parameter**. Reach into the long tail (globals, non-OO, parameter, and big-method groups) when the everyday break doesn't present a seam.

---

## How this connects to the rest of the toolkit

- **`legacy-code` skill** — owns the procedure (Change Algorithm, seam types, characterization tests); this file is its technique reference.
- **`legacy-test-strategy.md`** — *where* to place the test (effect reasoning, interception/pinch points) once a seam exists.
- **`testability-patterns.md`** — the production-code *target* design (constructor injection, interface extraction, Humble Object) these temporary breaks scaffold toward; a break is a means, the seam family there is the end.
- **`test-doubles.md`** — once a seam exists, the double that fills it (Stub/Spy/Mock/Fake), including Test-Specific Subclass (the double form of Subclass and Override Method).
- **`test-automation-principles.md`** — *Design for Testability* and *Don't Modify the SUT*: override only the seam, never behavior the test is verifying.
