# `init` fixture

This directory is deliberately empty apart from this README. The `--init-risks`
flag of `/code-review` copies the plugin's template here on first run. The eval
runner asserts:

1. Before: no `ACCEPTED-RISKS.md` in this directory.
2. After first `--init-risks`: `ACCEPTED-RISKS.md` exists and validates.
3. After second `--init-risks`: exit code non-zero, existing file untouched.

The eval cleans up the scaffolded file between runs.
