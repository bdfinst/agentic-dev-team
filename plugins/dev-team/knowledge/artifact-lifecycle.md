# Artifact Lifecycle States

This file defines the lifecycle state model for tracked plugin artifacts (skills,
agents). States are maintained in `metrics/artifact-usage.json` and consumed by
the `/artifact-lifecycle` skill to report and propose transitions.

## States

### active
An artifact used within the last 30 days. No lifecycle transition is needed.

### stale
An artifact **not used in more than 30 days** (i.e., `days_since_used >= 30` and
`< 90`). Stale artifacts are candidates for disabling — add them to
`## Disabled Skills` in project `CLAUDE.md` so they do not load into context
until deliberately re-enabled.

### archived
An artifact **not used in more than 90 days** (i.e., `days_since_used >= 90`).
Archive candidates should be evaluated for permanent removal from the active set.

## Lifecycle Thresholds

| State | Threshold |
|-------|-----------|
| active | `last_used_at` < 30 days ago |
| stale | `last_used_at` >= 30 days ago (and < 90 days) |
| archived | `last_used_at` >= 90 days ago |

Both boundaries are **inclusive**: an artifact last used exactly 30 days ago is
stale; an artifact last used exactly 90 days ago is an archive candidate.

## Pinned Exemption

Artifacts listed under `## Pinned Skills` in `CLAUDE.md` are exempt from all
lifecycle transitions regardless of `last_used_at`. A pinned artifact is excluded
from the Stale Skills and Archive Candidates sections of `/artifact-lifecycle`
output and is never proposed for disabling or removal.

## artifact-usage.json Schema

```json
{
  "<artifact-name>": {
    "use_count": 5,
    "last_used_at": "2026-06-01T12:00:00Z",
    "lifecycle": "active"
  }
}
```

The `lifecycle` field is initialised to `"active"` on first write and preserved
on subsequent upserts — a manually-set `"stale"` value is not overwritten when
the artifact is next used. The `/artifact-lifecycle` skill computes effective
lifecycle from `last_used_at` rather than from this stored field, so the stored
value is informational only.
