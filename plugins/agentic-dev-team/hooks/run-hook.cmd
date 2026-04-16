@echo off
REM run-hook.cmd — Windows shim for Claude Code hooks
REM Locates bash and delegates to the .sh hook script, passing stdin and args.
REM Exit codes from the bash script are propagated.

setlocal

REM Strategy 1: bash on PATH (Git for Windows adds it)
where bash >nul 2>&1
if %ERRORLEVEL% equ 0 (
    bash %*
    exit /b %ERRORLEVEL%
)

REM Strategy 2: Git for Windows default location
if exist "C:\Program Files\Git\bin\bash.exe" (
    "C:\Program Files\Git\bin\bash.exe" %*
    exit /b %ERRORLEVEL%
)

REM Strategy 3: WSL fallback
where wsl >nul 2>&1
if %ERRORLEVEL% equ 0 (
    wsl bash %*
    exit /b %ERRORLEVEL%
)

REM No bash found
echo ERROR: bash not found. Install Git for Windows from https://gitforwindows.org 1>&2
exit /b 1
