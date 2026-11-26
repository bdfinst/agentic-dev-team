# Sandbox approach for unattended runs

**Question:** Should dev-team ship a devcontainer or Docker template for
unattended runs (`/autoship`, long builds), or document Claude Code's native
sandbox settings?

**Recommendation:** Document a native-sandbox settings recipe. Ship no
template. Link Anthropic's reference devcontainer for users who need a
container.

## Evidence

Sources: Claude Code docs pages `sandboxing`, `permissions`, `permission-modes`,
and `devcontainer`. The sandbox page was read only through its troubleshooting
section, so its advanced settings are not covered here.

| | Native sandbox | Reference devcontainer |
| --- | --- | --- |
| Isolation | OS-level (Seatbelt on macOS; bubblewrap on Linux and WSL2). Writes limited to the working directory, temp, and `--add-dir`. Network through a proxy with an empty domain allowlist. Child processes inherit the limits. | Container boundary, optional egress firewall, non-root user. |
| Gaps | Reads most of the machine by default, including `~/.ssh`. Read/Edit/Write/WebFetch, hooks, and local MCP servers are outside the sandbox. Native Windows has no sandbox. | A malicious repo can still exfiltrate credentials mounted into the container. Firewall needs `NET_ADMIN`/`NET_RAW`. |
| Login persistence | None needed; uses the host login. | Named volume at `~/.claude` plus `CLAUDE_CONFIG_DIR`, or an API key or OAuth token as a secret. |
| Setup cost | macOS: `/sandbox`. Linux: install `bubblewrap` and `socat`. | Docker, a Dev Containers editor, the `claude-code` feature, volume and env setup. |
| Fit for `/autoship` | Sandboxed Bash can auto-allow without prompts, so unattended rounds stop on fewer prompts. | Needed only when the run uses `--dangerously-skip-permissions`. |

## Recipe

```json
{
  "sandbox": {
    "enabled": true,
    "autoAllowBashIfSandboxed": true,
    "allowUnsandboxedCommands": false,
    "network": { "allowedDomains": ["github.com", "api.github.com"] }
  }
}
```

Add `sandbox.filesystem.denyRead` for credential directories (`allowRead`
re-allows a narrower path inside it). Never combine an unattended run with
`bypassPermissions` outside a container.

**Keys checked against the sandboxing and settings pages:** `sandbox.enabled`,
`sandbox.autoAllowBashIfSandboxed`, `sandbox.allowUnsandboxedCommands`,
`sandbox.network.allowedDomains`, `sandbox.filesystem.denyRead`,
`sandbox.filesystem.allowRead`, `sandbox.excludedCommands`, and
`permissions.blockReadsOutsideWorkingDirectories` (v2.1.257 or later) exist.
The settings index describes `autoAllowBashIfSandboxed` as "Run sandboxed
commands without a permission prompt". The pages checked did not state its
type or default; the sandboxing page implies it is off unless set. The
`allowUnsandboxedCommands` default was not captured either, so the recipe sets
both explicitly.

**Auto-allow limits:** a command a Bash deny rule matches is still blocked, and
content-scoped ask rules such as `Bash(git push *)` still prompt. A failed
command may be retried with `dangerouslyDisableSandbox`, which runs unsandboxed;
`allowUnsandboxedCommands: false` turns the retry off. Only part of the
auto-allow section was readable, so read it in full before publishing the
recipe.

**GitHub access:** `github.com` is only an example `allowedDomains` entry, and
git over HTTPS works once the host is listed. Plain `ssh` ignores the proxy, so
git over SSH can fail on macOS; switch the remote to HTTPS, or add
`excludedCommands` entries for `git push *`, which then run outside the
sandbox and reach any host. The Go-based `gh` can fail TLS on macOS behind the
proxy; the documented fixes are an `excludedCommands` entry or
`sandbox.enableWeakerNetworkIsolation`.

## Why not a template

dev-team's own value is the pipeline, not a runtime. A shipped template would
need upkeep as the reference devcontainer changes, and the native sandbox
removes the prompts that most hurt an unattended run. No follow-up
implementation issue is needed because no template is chosen.

## Open

The recipe is untested in a real `/autoship` round. Run one sandboxed round and
record whether `/ship`'s `gh`, `git push`, and test commands all work inside the
network allowlist, on HTTPS and on SSH remotes.
