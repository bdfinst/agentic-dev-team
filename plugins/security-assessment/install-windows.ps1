#Requires -Version 5.1
<#
.SYNOPSIS
    Install the tools the agentic-security-assessment plugin calls on Windows.

.DESCRIPTION
    Companion to install.sh (which only verifies presence). This script runs the
    actual Scoop / pip commands on Windows.

    Scoop (https://scoop.sh) is the primary package manager — it requires no
    admin rights for most packages and is the closest Windows analogue to
    Homebrew. The script refuses to run without it and will not auto-install it.

    Usage:
        .\install-windows.ps1                # install tier-1 tools (recommended default)
        .\install-windows.ps1 -All           # tier-1 + optional + red-team / PDF deps
        .\install-windows.ps1 -DryRun        # print commands without running them
        .\install-windows.ps1 -Help

    If PowerShell blocks the script, run once in an elevated session:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

    Exit codes:
        0  — all requested installs succeeded (or were already present)
        1  — missing prerequisite (scoop, python) or one install failed
        2  — bad flag
#>

param(
    [switch]$All,
    [switch]$DryRun,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Help ──────────────────────────────────────────────────────────────────────

if ($Help) {
    Write-Host @"
install-windows.ps1 — install agentic-security-assessment tool dependencies on Windows.

Groups:
  tier-1 (default): python, jq, semgrep, gitleaks, trivy, hadolint, actionlint
  -All adds:        checkov, bandit, gosec, bearer, osv-scanner, grype,
                    kube-linter, trufflehog, detect-secrets, deptry,
                    kube-score, govulncheck, pandoc, weasyprint

Flags:
  -All      install every tool the plugin can call
  -DryRun   print the commands without running them
  -Help     show this message

Prerequisites:
  Scoop (https://scoop.sh) — hard requirement. Install it with:
      irm get.scoop.sh | iex
  Python >= 3.10 — install via 'scoop install python' or https://python.org
"@
    exit 0
}

# ── Platform + prerequisite gate ─────────────────────────────────────────────

if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) {
    Write-Error "This script targets Windows. On macOS use install-macos.sh; on Linux use apt/pip equivalents from install.sh's hints."
    exit 1
}

if (-not (Get-Command scoop -ErrorAction SilentlyContinue)) {
    Write-Host "error: Scoop not found. Install it first:" -ForegroundColor Red
    Write-Host "       irm get.scoop.sh | iex" -ForegroundColor Yellow
    Write-Host "       Then re-open PowerShell and re-run this script."
    exit 1
}

# Resolve python binary name — Windows installs may provide 'python' not 'python3'.
$PythonCmd = $null
foreach ($candidate in @('python3', 'python')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $PythonCmd = $candidate
        break
    }
}
if (-not $PythonCmd) {
    Write-Host "error: python not on PATH." -ForegroundColor Red
    Write-Host "       Install via 'scoop install python' or https://python.org/downloads/"
    exit 1
}

$pyVersion = & $PythonCmd -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>$null
$pyParts   = $pyVersion -split '\.'
if ([int]$pyParts[0] -lt 3 -or ([int]$pyParts[0] -eq 3 -and [int]$pyParts[1] -lt 10)) {
    Write-Host "error: python $pyVersion found; red-team harness requires >= 3.10" -ForegroundColor Red
    Write-Host "       upgrade: scoop update python"
    exit 1
}

# ── Helpers ───────────────────────────────────────────────────────────────────

$Installed = 0
$Skipped   = 0
$Failed    = [System.Collections.Generic.List[string]]::new()

function Section([string]$Title) {
    Write-Host ""
    Write-Host "── $Title ──"
}

function Invoke-Step([string]$Display, [scriptblock]$Cmd) {
    Write-Host "  `$ $Display"
    if (-not $DryRun) {
        & $Cmd
    }
}

function Install-Scoop([string]$Package, [string]$Binary = '') {
    $probe = if ($Binary) { $Binary } else { $Package }
    if (Get-Command $probe -ErrorAction SilentlyContinue) {
        Write-Host ("  [skip] {0,-16} — already installed" -f $Package)
        $script:Skipped++
        return
    }
    Invoke-Step "scoop install $Package" { scoop install $Package --no-update-scoop }
    if ($LASTEXITCODE -eq 0) {
        $script:Installed++
    } else {
        Write-Host ("  [FAIL] {0} — scoop install failed" -f $Package) -ForegroundColor Red
        $script:Failed.Add($Package)
    }
}

function Install-Pip([string]$Package, [string]$Binary = '') {
    $probe = if ($Binary) { $Binary } else { $Package }
    if (Get-Command $probe -ErrorAction SilentlyContinue) {
        Write-Host ("  [skip] {0,-16} — already installed" -f $Package)
        $script:Skipped++
        return
    }
    # Prefer pipx for isolated CLI tools; fall back to pip --user.
    if (Get-Command pipx -ErrorAction SilentlyContinue) {
        Invoke-Step "pipx install $Package" { pipx install $Package }
    } else {
        Invoke-Step "$PythonCmd -m pip install --user --quiet $Package" {
            & $PythonCmd -m pip install --user --quiet $Package
        }
    }
    if ($LASTEXITCODE -eq 0) {
        $script:Installed++
    } else {
        Write-Host ("  [FAIL] {0} — pip install failed" -f $Package) -ForegroundColor Red
        $script:Failed.Add($Package)
    }
}

# ── Scoop bucket setup ────────────────────────────────────────────────────────
# Several tools live in the 'extras' bucket. Add it once if absent.

Section "Scoop bucket setup"
$buckets = scoop bucket list 2>$null | Select-String -SimpleMatch 'extras'
if ($buckets) {
    Write-Host "  [skip] extras bucket     — already added"
    $Skipped++
} else {
    Invoke-Step "scoop bucket add extras" { scoop bucket add extras }
    if ($LASTEXITCODE -eq 0) { $Installed++ } else { $Failed.Add('scoop-extras-bucket') }
}

# ── Tier-1 baseline ──────────────────────────────────────────────────────────

Section "Tier-1 baseline — required for /security-assessment to be useful"

Install-Scoop jq
# semgrep: pip/pipx is the upstream-recommended path on all platforms.
Install-Pip semgrep
Install-Scoop gitleaks
Install-Scoop trivy
Install-Scoop hadolint
Install-Scoop actionlint

# ── Optional + red-team deps (with -All) ─────────────────────────────────────

if ($All) {
    Section "Optional SAST / policy / supply-chain"
    Install-Pip  checkov
    Install-Pip  bandit
    Install-Scoop gosec
    Install-Scoop bearer
    Install-Scoop osv-scanner
    Install-Scoop grype
    Install-Scoop kube-linter
    Install-Scoop trufflehog
    Install-Pip  detect-secrets
    Install-Pip  deptry
    Install-Scoop kube-score

    # govulncheck requires Go toolchain.
    if (Get-Command go -ErrorAction SilentlyContinue) {
        if (Get-Command govulncheck -ErrorAction SilentlyContinue) {
            Write-Host "  [skip] govulncheck       — already installed"
            $Skipped++
        } else {
            Invoke-Step "go install golang.org/x/vuln/cmd/govulncheck@latest" {
                go install golang.org/x/vuln/cmd/govulncheck@latest
            }
            if ($LASTEXITCODE -eq 0) { $Installed++ } else { $Failed.Add('govulncheck') }
        }
    } else {
        Write-Host "  [skip] govulncheck       — Go toolchain absent; skipping (scoop install go to enable)"
        $Skipped++
    }

    Section "Red-team / PDF export deps"
    Install-Scoop pandoc
    Install-Pip  weasyprint
}

# ── Summary ───────────────────────────────────────────────────────────────────

Section "Summary"
Write-Host ("  installed: {0}   skipped (already present): {1}   failed: {2}" -f $Installed, $Skipped, $Failed.Count)

if ($Failed.Count -gt 0) {
    Write-Host ""
    Write-Host ("  failed packages: {0}" -f ($Failed -join ', ')) -ForegroundColor Red
    Write-Host "  Re-run with -DryRun to inspect the failing commands, or install the"
    Write-Host "  failing packages manually."
    exit 1
}

Write-Host ""
Write-Host "  Done. Verify the install:"
Write-Host "    bash plugins/agentic-security-assessment/install.sh"
Write-Host ""
Write-Host "  Then try: /security-assessment <path-to-target>"
exit 0
