# CI/CD file scope

## Glob list

The canonical glob list for "files that carry CI/CD pipeline configuration."
Security-relevant content in these files (leaked secrets, `continue-on-error`
on a security gate, overly broad `permissions:`) often escapes a normal
`src/` tree walk, so any scan that claims to cover CI/CD must walk these
paths explicitly — including up to the repo root in a monorepo, since a
workflow file can live outside the scanned subtree.

- `.github/workflows/*.{yml,yaml}` (GitHub Actions)
- `.gitlab-ci.yml` + `.gitlab/**/*.{yml,yaml}` (GitLab CI)
- `.circleci/config.yml` (CircleCI)
- `azure-pipelines.yml` + `.azure-pipelines/**/*.{yml,yaml}` (Azure Pipelines)
- `bitbucket-pipelines.yml`
- `Jenkinsfile` + `jenkinsfile.d/**/*` (Jenkins)

## Empty-scan reporting

If a target has no files in any of these classes, record an empty scan
result (e.g. `"ci_dirs_scanned": []`) rather than silently omitting the
field — a reader must be able to tell "no CI files in scope" from "CI scope
wasn't checked."
