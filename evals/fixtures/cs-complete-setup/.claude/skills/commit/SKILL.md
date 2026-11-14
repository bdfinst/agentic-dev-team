---
name: commit
description: Commit staged changes with a conventional commit message after the checks pass.
user-invocable: true
disable-model-invocation: true
---

# Commit

1. Run the `test` skill. Stop if it does not pass.
2. Show `git diff --staged --stat` and ask the user to confirm the staged files before committing.
3. Write a conventional commit message (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`) that names the behavior changed.
4. Run `git commit` with that message.
