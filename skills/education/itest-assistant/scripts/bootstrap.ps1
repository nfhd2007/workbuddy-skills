<#
.SYNOPSIS
  Zero-dependency environment bootstrap for itest-assistant (Windows).

  Resolves a usable Node.js 16+ in this order:
    1. -NodeOverride / $env:ITEST_NODE_BIN / $env:NODE_BIN (explicit override)
    2. Persisted stage-P runtime (~/.workbuddy/runtimes/itest-assistant/node_path.txt)
    3. WorkBuddy managed Node: %WORKBUDDY_CONFIG_DIR%\binaries\node\versions\*
    4. $env:CODEBUDDY_NODE_BIN (WorkBuddy sets this for its own CLI)
    5. PATH: node / node.exe
    6. Common installs (Program Files\nodejs)
    7. WorkBuddy bundled vendor\node.zip (ships with every install, NO download)
    8. Auto-download official portable Node from mirrors (last resort)
  Then invokes scripts/preflight.js and forwards its pure-ASCII JSON verbatim.

  Stdout carries ONLY the JSON object. Diagnostics go to stderr (-VerboseLog)
  or into report.bootstrap_log. The full readable Chinese report is written
  as UTF-8 to $report_file (read it with a file tool).

  NOTE: this file is intentionally pure ASCII. Windows PowerShell 5.1 reads
  BOM-less UTF-8 .ps1 as ANSI, which would corrupt non-ASCII text.
#>
[CmdletBinding()]
param(
    [string] $SkillDir,
    [string] $RuntimeDir,
    [string] $NodeOverride,
    [switch] $NoFix,
    [switch] $SkipNetwork,
    [switch] $ForcePortable,
    [switch] $Readable,
    [switch] $VerboseLog
)

$ErrorActionPreference = 'Continue'   # native stderr must never be terminating
$ProgressPreference   = 'SilentlyContinue'
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

$LOG_SEP = '||'
$log = New-Object System.Collections.Generic.List[string]
function Note([string]$m) { [void]$log.Add($m) }

function Emit-Fallback([string]$reason) {
    $obj = [ordered]@{
        ok            = $false
        ready         = $false
        stage         = 'P'
        error         = $reason
        node          = [ordered]@{ cmd = ''; version = ''; source = 'none'; portable = $false }
        run           = [ordered]@{ node_cmd = '' }
        route         = 'block'
        route_reason  = $reason
        bootstrap_log = $log.ToArray()
        blockers      = @($reason)
        hints         = @(
            'Set ITEST_NODE_BIN or NODE_BIN to an absolute path of Node 16+.',
            'WorkBuddy ships Node under %WORKBUDDY_CONFIG_DIR%\binaries\node\versions and resources\vendor\node.zip.',
            'Then re-run this bootstrap script.'
        )
        checks        = @()
        auto_fixed    = @()
        report_file   = ''
    }
    Write-Output ($obj | ConvertTo-Json -Depth 6 -Compress)
}

# ---- resolve skill / preflight paths ---------------------------------------
if (-not $SkillDir) { $SkillDir = Split-Path -Parent $PSScriptRoot }
try { $SkillDir = (Resolve-Path -LiteralPath $SkillDir).Path }
catch { Emit-Fallback ("Cannot resolve SkillDir: " + $_.Exception.Message); exit 1 }
$preflight = Join-Path $SkillDir 'scripts\preflight.js'
if (-not (Test-Path -LiteralPath $preflight -PathType Leaf)) {
    Emit-Fallback ("preflight.js is missing: " + $preflight); exit 1
}

$cfg = $env:WORKBUDDY_CONFIG_DIR
if (-not $cfg) { $cfg = Join-Path $env:USERPROFILE '.workbuddy' }
if (-not $RuntimeDir) { $RuntimeDir = Join-Path $cfg 'runtimes\itest-assistant' }
$nodePathFile = Join-Path $RuntimeDir 'node_path.txt'
$reportFile   = Join-Path $RuntimeDir 'last_preflight.json'

# ---- collect Node candidates ------------------------------------------------
$candidates = New-Object System.Collections.Generic.List[object]
function Add-Candidate([string]$p, [string]$src) {
    if ($p -and (Test-Path -LiteralPath $p -PathType Leaf)) {
        [void]$candidates.Add([pscustomobject]@{ Path = $p; Source = $src })
    }
}

# 1. explicit override
$override = $NodeOverride
if (-not $override) { $override = $env:ITEST_NODE_BIN }
if (-not $override) { $override = $env:NODE_BIN }
if ($override) { Add-Candidate $override 'explicit_override' }

# 2. persisted stage-P runtime (survives across separate tool calls)
if (Test-Path -LiteralPath $nodePathFile -PathType Leaf) {
    $saved = (Get-Content -LiteralPath $nodePathFile -Raw -Encoding UTF8).Trim()
    if ($saved) { Add-Candidate $saved 'reused_runtime' }
}

# 3. WorkBuddy managed Node
$versionsDir = Join-Path $cfg 'binaries\node\versions'
if (Test-Path -LiteralPath $versionsDir) {
    Get-ChildItem -LiteralPath $versionsDir -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | ForEach-Object {
            Add-Candidate (Join-Path $_.FullName 'node.exe') 'workbuddy_managed'
            Add-Candidate (Join-Path $_.FullName 'node')     'workbuddy_managed'
        }
}

# 4. WorkBuddy CLI-provided node
if ($env:CODEBUDDY_NODE_BIN) { Add-Candidate $env:CODEBUDDY_NODE_BIN 'workbuddy_cli' }

# 5. PATH
foreach ($n in @('node.exe', 'node')) {
    try {
        $c = Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c -and $c.Source) { Add-Candidate $c.Source 'system_path' }
    } catch { }
}

# 6. common installs
$pf = if ($env:ProgramFiles) { $env:ProgramFiles } else { 'C:\Program Files' }
foreach ($g in @((Join-Path $pf 'nodejs\node.exe'), 'C:\nodejs\node.exe', 'D:\nodejs\node.exe')) {
    Add-Candidate $g 'common_install'
}

# ---- validate candidates (no Out-String: it wraps long lines and breaks JSON) -
$probe = 'process.stdout.write(process.versions.node)'
function Test-Node([string]$p) {
    try {
        $out = & $p -e $probe 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $txt = ($out -join "`n")
        $m = [regex]::Match($txt, '^v?(\d+)\.(\d+)\.(\d+)')
        if (-not $m.Success) { return $null }
        if ([int]$m.Groups[1].Value -lt 16) { return $null }
        return $m.Groups[1].Value + '.' + $m.Groups[2].Value + '.' + $m.Groups[3].Value
    } catch { return $null }
}

$nodeCmd = ''; $nodeSource = ''; $nodeVer = ''; $portable = $false
if (-not $ForcePortable) {
    foreach ($c in $candidates) {
        $v = Test-Node $c.Path
        if ($v) {
            $nodeCmd = $c.Path; $nodeSource = $c.Source; $nodeVer = $v
            Note ("Resolved Node {0} from {1} ({2})" -f $v, $c.Source, $c.Path)
            break
        }
    }
} else {
    Note '-ForcePortable: skipping interpreter discovery, provisioning a portable runtime'
}

# ---- 7. WorkBuddy bundled vendor\node.zip (no network needed) ---------------
function Expand-NodeZip([string]$zip, [string]$dest) {
    # Use .NET directly: Expand-Archive renders a noisy progress bar into the
    # host stream even with $ProgressPreference suppressed.
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
        if (-not (Test-Path -LiteralPath $dest)) {
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
        }
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $dest)
        $exe = Get-ChildItem -LiteralPath $dest -Recurse -Filter 'node.exe' -File -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if ($exe) { return $exe.FullName }
    } catch { Note ("vendor zip extract failed: " + $_.Exception.Message) }
    return ''
}

if (-not $nodeCmd) {
    $res = $env:WORKBUDDY_RESOURCES_PATH
    if (-not $res -and $env:WORKBUDDY_APP_PATH) {
        $r = Split-Path -Parent $env:WORKBUDDY_APP_PATH
        if ($r) { $res = $r }
    }
    if (-not $res) {
        try {
            $proc = Get-Process -Name 'WorkBuddy' -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($proc -and $proc.Path) { $res = Join-Path (Split-Path -Parent $proc.Path) 'resources' }
        } catch { }
    }
    if (-not $res) { $res = Join-Path $env:LOCALAPPDATA 'Programs\WorkBuddy\resources' }
    $vendorZip = Join-Path $res 'vendor\node.zip'
    if (Test-Path -LiteralPath $vendorZip -PathType Leaf) {
        $vdest = Join-Path $RuntimeDir 'node-vendor'
        $cached = ''
        if (Test-Path -LiteralPath $vdest) {
            $cached = (Get-ChildItem -LiteralPath $vdest -Recurse -Filter 'node.exe' -File -ErrorAction SilentlyContinue |
                       Select-Object -First 1).FullName
        }
        if (-not $cached) { $cached = Expand-NodeZip $vendorZip $vdest }
        if ($cached) {
            $v = Test-Node $cached
            if ($v) {
                $nodeCmd = $cached; $nodeSource = 'workbuddy_vendor_zip'; $nodeVer = $v; $portable = $true
                Note ("Unpacked WorkBuddy bundled Node {0} ({1})" -f $v, $cached)
            }
        }
    }
}

# ---- 8. auto-download official portable Node (last resort) -----------------
if (-not $nodeCmd) {
    Note 'No usable Node found; preparing a portable runtime automatically'
    $nver = '22.14.0'
    $arch = 'win-x64'
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'win-arm64' }
    $zipName = "node-v$nver-$arch.zip"
    $dest    = Join-Path $RuntimeDir "node-v$nver-$arch"
    $downloaded = $false

    $cachedNode = ''
    if (Test-Path -LiteralPath $dest) {
        $cachedNode = (Get-ChildItem -LiteralPath $dest -Recurse -Filter 'node.exe' -File -ErrorAction SilentlyContinue |
                       Select-Object -First 1).FullName
        if ($cachedNode) { Note ("Reusing previously downloaded portable Node at " + $dest) }
    }
    if (-not $cachedNode) {
        New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
        $dl = Join-Path $RuntimeDir '_download'
        New-Item -ItemType Directory -Force -Path $dl | Out-Null
        $zipPath = Join-Path $dl $zipName
        $mirrors = @(
            "https://mirrors.huaweicloud.com/nodejs/v$nver/$zipName",
            "https://registry.npmmirror.com/-/binary/node/v$nver/$zipName",
            "https://nodejs.org/dist/v$nver/$zipName"
        )
        foreach ($u in $mirrors) {
            try {
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                Invoke-WebRequest -Uri $u -OutFile $zipPath -UseBasicParsing -TimeoutSec 180
                if ((Get-Item -LiteralPath $zipPath).Length -lt 5MB) { throw 'downloaded file too small' }
                $downloaded = $true
                Note ("Downloaded portable Node from " + $u)
                break
            } catch { Note ("Mirror failed: " + $u + " :: " + $_.Exception.Message) }
        }
        if ($downloaded) {
            $cachedNode = Expand-NodeZip $zipPath $dest
            if ($cachedNode) { Note ("Extracted portable Node to " + $dest) }
        }
    }
    if ($cachedNode) {
        $v = Test-Node $cachedNode
        if ($v) {
            $nodeCmd = $cachedNode
            # Lesson learned: a reused cached runtime must NOT be reported as downloaded.
            $nodeSource = if ($downloaded) { 'portable_downloaded' } else { 'reused_runtime' }
            $nodeVer = $v; $portable = $true
            Note ("Portable Node ready: " + $cachedNode + " (" + $v + ")")
        }
    }
}

if (-not $nodeCmd) {
    Emit-Fallback 'Unable to locate or auto-provision a usable Node 16+ interpreter (offline and no bundled runtime).'
    exit 1
}

# ---- persist resolution so later run.sh calls (separate tool calls) reuse it --
try {
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    [System.IO.File]::WriteAllText($nodePathFile, $nodeCmd, (New-Object System.Text.UTF8Encoding($false)))
    Note ("Persisted node path to " + $nodePathFile)
} catch { Note ("Could not persist node path: " + $_.Exception.Message) }

# ---- hand off to preflight.js ----------------------------------------------
$env:ITEST_NODE_SOURCE   = $nodeSource
$env:ITEST_NODE_PORTABLE = if ($portable) { '1' } else { '0' }
$env:ITEST_BOOTSTRAP_LOG = ($log -join $LOG_SEP)
$env:ITEST_RUNTIME_DIR   = $RuntimeDir
if (-not $env:ITEST_PS) { $env:ITEST_PS = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') }

$pfArgs = @('--report-file', $reportFile, '--runtime-dir', $RuntimeDir)
if ($NoFix)       { $pfArgs += '--no-fix' }
if ($SkipNetwork) { $pfArgs += '--skip-network' }
if ($Readable)    { $pfArgs += '--readable' }

$raw = & $nodeCmd $preflight @pfArgs 2>$null
# Join lines directly. Out-String would wrap long JSON lines at the host width,
# inserting newlines that make the JSON invalid.
$text = ($raw -join "`n").Trim()

if ($VerboseLog) { foreach ($l in $log) { [Console]::Error.WriteLine('[bootstrap] ' + $l) } }
if (-not $text -or -not $text.StartsWith('{')) {
    Emit-Fallback ("preflight.js produced no JSON (exit=" + $LASTEXITCODE + ")"); exit 1
}
Write-Output $text
