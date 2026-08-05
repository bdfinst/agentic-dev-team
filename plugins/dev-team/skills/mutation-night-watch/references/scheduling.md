# Mutation Night-Watch: Scheduling Recipes

Each recipe runs `mutation_nightwatch.py` **without** `--detach` — the
scheduler itself already runs the job detached from any interactive session,
so re-detaching would just orphan a second process. Use `--detach` only for
an ad hoc manual launch (see [`../SKILL.md`](../SKILL.md) Step 2).

Confirm the cadence and scope with the user before installing any of these —
each one runs unattended, indefinitely, until removed (see `../SKILL.md`'s
Constraints).

Substitute:

- `<repo>` — absolute path to the repository root.
- `<python>` — an absolute path to the Python 3.10+ interpreter that has the
  repo's mutation tooling on `PATH` (a venv's `python`, or the system one).

## macOS — launchd

launchd (not cron — cron does not run on a schedule reliably across macOS
sleep/wake cycles) via a per-user `LaunchAgent`.

`~/Library/LaunchAgents/dev.agentic-dev-team.mutation-nightwatch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>dev.agentic-dev-team.mutation-nightwatch</string>
  <key>ProgramArguments</key>
  <array>
    <string><python></string>
    <string><repo>/plugins/dev-team/skills/mutation-testing/scripts/mutation_nightwatch.py</string>
    <string>--repo-root</string>
    <string><repo></string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>1</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string><repo>/reports/mutation-nightwatch/launchd.log</string>
  <key>StandardErrorPath</key>
  <string><repo>/reports/mutation-nightwatch/launchd.log</string>
</dict>
</plist>
```

Load/unload:

```bash
launchctl load ~/Library/LaunchAgents/dev.agentic-dev-team.mutation-nightwatch.plist
launchctl unload ~/Library/LaunchAgents/dev.agentic-dev-team.mutation-nightwatch.plist
```

launchd's own scheduling already survives the machine sleeping (it fires on
the next wake if the fire time was missed); `mutation_nightwatch.py`'s
`caffeinate`-based `SleepInhibitor` then keeps the machine **awake for the
run itself** once it starts, so a multi-hour run isn't interrupted mid-way.

## Linux — cron + systemd-inhibit

cron runs the job; the script's own `SleepInhibitor` calls
`systemd-inhibit` internally, so no extra wrapping is needed in the crontab
line itself.

`crontab -e`:

```cron
0 1 * * * <python> <repo>/plugins/dev-team/skills/mutation-testing/scripts/mutation_nightwatch.py --repo-root <repo> >> <repo>/reports/mutation-nightwatch/cron.log 2>&1
```

Note the redirect is a direct `>>`, not a `| tee` — see
[`mutation-testing/SKILL.md`](../../mutation-testing/SKILL.md#capturing-run-output-safely)
for why a `tee` pipeline masks a startup failure's exit code. cron always
uses `sh`, so this is safe here regardless.

A machine that suspends (a laptop, not a server) needs an additional wake
trigger — cron does not wake a suspended machine. Pair with `rtcwake` or an
OS-level wake-on-schedule setting if the target machine sleeps outside of
process-level idle (systemd-inhibit only blocks *idle* suspend once the
process is already running, not a deeper suspend triggered before cron fires).

## Windows — Task Scheduler

```powershell
schtasks /create /tn "MutationNightWatch" /tr "<python> <repo>\plugins\dev-team\skills\mutation-testing\scripts\mutation_nightwatch.py --repo-root <repo>" /sc daily /st 01:00
```

Task Scheduler's own "Wake the computer to run this task" option (in the
task's **Conditions** tab, or `/sc daily` plus editing the task afterward via
`taskschd.msc`) is the Windows equivalent of the launchd/rtcwake concerns
above — enable it if the target machine sleeps.

`mutation_nightwatch.py` calls `SetThreadExecutionState` directly on Windows
(no subprocess to hold open, unlike macOS/Linux) to keep the machine awake
for the run's duration once it starts.

Remove the task:

```powershell
schtasks /delete /tn "MutationNightWatch" /f
```

## Every OS: reading the result

Regardless of scheduler, the result lands at
`<repo>/reports/mutation-nightwatch/LATEST/MORNING-SUMMARY.md` — the stable
mirror path never changes between runs. See [`../SKILL.md`](../SKILL.md)
Step 4 for the morning hand-off to `mutation-kill`.
