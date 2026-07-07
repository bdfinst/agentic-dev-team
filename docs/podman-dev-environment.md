# Podman dev environment

A reproducible container that ships the full toolchain this repo's gates need,
so you can run the local checks (and everything the pre-push hook runs) without
installing anything on your host beyond [Podman](https://podman.io/).

It is the container equivalent of [`setup-prereqs-linux.sh`](../setup-prereqs-linux.sh)
and [`scripts/dev-setup.sh`](../scripts/dev-setup.sh): same tools, pinned to an
Ubuntu base so it matches the Ubuntu VMs used by Claude Code on the web and by
GitHub Actions.

## What's in the image

Defined in [`Containerfile`](../Containerfile):

| Layer            | Contents                                                              |
| ---------------- | -------------------------------------------------------------------- |
| Hard deps        | `jq`, `shellcheck`, `python3` + `pip`, `git` — what `ci-local.sh` checks |
| Python dev deps  | everything in [`requirements-dev.txt`](../requirements-dev.txt) (PyYAML, semgrep, httpx, jsonschema, pytest(+asyncio/xdist), ruff, mypy, …) |
| Node             | Node 24+ (the `engines` floor; version tracks [`.nvmrc`](../.nvmrc)) plus `npm ci` deps (husky, eslint, commitlint, lint-staged) |
| GitHub CLI       | `gh` for PR operations                                                |

## Build

```bash
podman build -t agentic-dev-team:dev .
```

The Node major version can be overridden to match `.nvmrc` if it ever changes:

```bash
podman build --build-arg NODE_MAJOR=24 -t agentic-dev-team:dev .
```

## Run

Mount the repo at `/workspace` and open a shell. The `:Z` suffix relabels the
volume for SELinux (Fedora/RHEL); it is a harmless no-op on other hosts.

```bash
podman run --rm -it -v "$PWD":/workspace:Z agentic-dev-team:dev
```

Run the same deterministic checks GitHub CI runs, without dropping into a shell:

```bash
podman run --rm -v "$PWD":/workspace:Z agentic-dev-team:dev \
  bash scripts/ci-local.sh
```

Run the Python test suites directly:

```bash
podman run --rm -v "$PWD":/workspace:Z agentic-dev-team:dev \
  python3 -m pytest
```

### Git hooks (husky)

The image bakes in the npm dev-dependencies, but git hooks are per-clone (they
embed absolute paths and need a `.git`). When you mount the real repo, install
them once inside the container:

```bash
podman run --rm -v "$PWD":/workspace:Z agentic-dev-team:dev npm ci
```

## Notes

- **Rebuild after dependency changes.** The image caches
  `requirements-dev.txt` and `package-lock.json` in their own layers; rebuild
  (`podman build …`) after either changes so the container picks up new deps.
- **PEP 668.** Ubuntu 24.04's system pip is externally-managed. Inside this
  disposable container we install with `--break-system-packages` onto the system
  interpreter the gates invoke — the same escape hatch `dev-setup.sh` falls back
  to. Don't copy that flag to your host; use a virtualenv there instead.
- **Graphify / CodeGraph** are intentionally omitted — they are optional,
  user-level code-intelligence tools, not gate prerequisites.
