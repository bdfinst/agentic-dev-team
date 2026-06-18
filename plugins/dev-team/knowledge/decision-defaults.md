# Decision Defaults

High-reversal-cost decision axes that recur across tasks and, when guessed wrong,
force an interrupt and rework. For each axis: the trigger that raises it, the default
stance, and what to confirm before committing. Screen every non-trivial request
against this list during discovery; surface any ambiguous axis in a single upfront
batch rather than guessing and being corrected later.

These are defaults, not laws — an explicit user instruction always wins. The point is
to resolve the axis *before* building, not to relitigate it mid-stream.

## Destructive shape: replace vs. merge

Trigger: a request writes config, settings, dotfiles, or installer output where prior
content may exist. Default: ask which is wanted before acting — a clean replace and an
in-place merge are different operations with different blast radii. Confirm: does the
user want existing content preserved (merge) or overwritten (replace)? When unstated
and the target is non-trivial, ask; do not silently merge.

## Format fidelity: preserve the native format

Trigger: handling a vector or structured asset (SVG, source diagram, lossless data).
Default: preserve the native, lossless form; do not down-convert (for example, SVG to
PNG) for convenience. Confirm: if a conversion seems necessary, name the reason and
get agreement before doing it.

## Evolution: migrate vs. edit a stub in place

Trigger: a target has been renamed, deprecated, or replaced by a successor (a plugin,
module, or file with a forwarding stub). Default: migrate to the current target rather
than editing the deprecated stub in place. Confirm: verify which artifact is canonical
before changing it — a stub edit that looks done can leave the real target untouched.

## Integration: auto-merge vs. direct-to-trunk

Trigger: landing changes on a shared branch. Default: open a PR and use auto-merge
gated on green checks rather than merging directly to trunk. Confirm: only merge
directly when the user has asked for it; a direct merge can bypass checks and lose work.

## Scope: touch only what was requested

Trigger: a request names specific files, slides, or targets. Default: change only
those; do not expand scope to adjacent items. Confirm: if neighboring changes seem
warranted, propose them separately rather than folding them in unasked.
