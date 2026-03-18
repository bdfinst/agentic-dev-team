---
name: python-quality
description: Python code quality — type hints, exception handling, modern idioms, dataclass/Pydantic patterns
tools: Read, Grep, Glob
model: haiku
---

# Python Quality

Output JSON:

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

Status: pass=clean Python, warn=improvements needed, fail=unsafe patterns
Severity: error=bare except or type safety issue, warning=missing types or anti-pattern, suggestion=modern idiom
Confidence: high=mechanical (add type hint, use f-string); medium=design choice; none=domain context needed

Model tier: small
Context needs: diff-only
File scope: `*.py`

## Activates when

`pyproject.toml`, `requirements.txt`, or `setup.py` exists.

## Skip

Return skip when no `.py` files in the changeset.

## Detect

Type hints:

- Missing type annotations on function signatures (public APIs must have types)
- `Any` used without justification
- No `mypy` or `pyright` config for strict checking
- `# type: ignore` without explanation

Exception handling:

- Bare `except:` or `except Exception:` without re-raise or specific handling
- Silencing exceptions with `pass`
- Catching too broad (Exception when only ValueError is expected)
- Missing `from` in `raise ... from` chains

Modern idioms:

- `format()` or `%` string formatting instead of f-strings
- Manual dict/list construction instead of comprehensions
- `type()` checks instead of `isinstance()`
- Mutable default arguments (`def f(x=[])`)

Data modeling:

- Plain dicts where `dataclass` or `Pydantic.BaseModel` would add type safety
- Duplicate field definitions across multiple dicts
- Missing validation at API boundaries (use Pydantic for request/response)

## Ignore

Django/Flask-specific patterns, test fixtures, script-only files, architecture.
