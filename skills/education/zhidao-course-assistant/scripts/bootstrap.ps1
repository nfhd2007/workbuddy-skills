# Zero-dependency launcher for preflight.py (Windows PowerShell 5.1).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap.ps1 check "C:\workspace"
# Always calls preflight with --json --ascii: stdout stays pure ASCII to avoid GBK mojibake.
param(
    [string]$Command = 'check',
    [string]$Workspace = ''
)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$preflight = Join-Path $scriptDir 'preflight.py'

function Test-PythonExe([string]$candidate) {
    if (-not $candidate) { return $false }
    try {
        & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Find-PythonExe {
    foreach ($c in @('python', 'python3', 'py')) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd -and (Test-PythonExe $cmd.Source)) { return $cmd.Source }
    }
    $wb = if ($env:WORKBUDDY_CONFIG_DIR) { $env:WORKBUDDY_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.workbuddy' }
    $candidates = @()
    if ($env:WORKBUDDY_RESOURCES_PATH) {
        $candidates += (Join-Path $env:WORKBUDDY_RESOURCES_PATH 'vendor\python\python.exe')
    }
    $versions = Join-Path $wb 'binaries\python\versions'
    if (Test-Path $versions) {
        $candidates += (Get-ChildItem -Path $versions -Filter 'python.exe' -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
    }
    foreach ($p in $candidates) { if (Test-PythonExe $p) { return $p } }
    return $null
}

$py = Find-PythonExe
if (-not $py) {
    [Console]::Out.WriteLine('{"ok":false,"error":"python_not_found","hint":"Install Python 3.8+ or see references/environment.md section 8"}')
    exit 1
}

$pfArgs = @($preflight, $Command, '--json', '--ascii')
if ($Workspace) { $pfArgs += @('--workspace', $Workspace) }
& $py @pfArgs
exit $LASTEXITCODE
