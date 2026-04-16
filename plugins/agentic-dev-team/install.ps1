# install.ps1 — Windows prerequisite checker for the agentic-dev-team plugin.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install.ps1

$pass = 0
$fail = 0
$missing = @()

function Check-Prerequisite {
    param(
        [string]$Name,
        [string]$InstallHint
    )

    # Special handling for bash: check PATH then Git for Windows default
    if ($Name -eq "bash") {
        $found = $false
        if (Get-Command "bash" -ErrorAction SilentlyContinue) {
            $found = $true
        } elseif (Test-Path "C:\Program Files\Git\bin\bash.exe") {
            $found = $true
        }
        if ($found) {
            Write-Host "[ok]   $Name"
            $script:pass++
            return
        }
    } else {
        if (Get-Command $Name -ErrorAction SilentlyContinue) {
            Write-Host "[ok]   $Name"
            $script:pass++
            return
        }
    }

    Write-Host "[FAIL] $Name -- required. $InstallHint"
    $script:fail++
    $script:missing += $Name
}

Write-Host "Checking agentic-dev-team prerequisites..."
Write-Host ""
Write-Host "--- Required ---"

Check-Prerequisite -Name "bash" `
    -InstallHint "Install Git for Windows from https://gitforwindows.org"

Check-Prerequisite -Name "jq" `
    -InstallHint "Install jq via winget: winget install jqlang.jq"

Check-Prerequisite -Name "git" `
    -InstallHint "Install Git for Windows from https://gitforwindows.org"

Write-Host ""

if ($fail -gt 0) {
    Write-Host "Result: $fail required dependency missing. Install and re-run."
    exit 1
} else {
    Write-Host "Result: All required dependencies present."
    exit 0
}
