<#
.SYNOPSIS
  Zero-dependency environment bootstrap for quark-share-skill-installer (Windows).

  Resolves a usable Python 3.9+ in this order:
    1. -PythonOverride / $env:QUARK_INSTALLER_PYTHON (explicit user override)
    2. WorkBuddy bundled CPython: <resources>\vendor\python\python.exe
       (resources dir discovered from WORKBUDDY_RESOURCES_PATH, WORKBUDDY_APP_PATH,
        the running WorkBuddy.exe path, and common install roots)
    3. WorkBuddy managed Python: %WORKBUDDY_CONFIG_DIR%\binaries\python\versions\*
    4. PATH: python / python3 / py -3
    5. Common system installs and a previously downloaded portable runtime
  If none works, downloads the official Windows embeddable Python (no installer,
  no admin rights, no PATH changes) into the WorkBuddy user runtime dir.

  That download is FAIL-CLOSED: the archive must match a pinned fingerprint
  (exact byte size + SHA256 + the MD5 published by python.org) before anything
  is extracted or executed, and the extracted python.exe must carry a valid
  Python Software Foundation Authenticode signature. A mirror that serves a
  different file is simply rejected and the next mirror is tried; if no pinned
  fingerprint exists for the requested version/arch, the download is refused
  instead of trusting the mirror.

  Then invokes scripts/preflight.py and forwards its JSON report verbatim.
  Stdout carries ONLY the JSON object; diagnostics go to stderr (-VerboseLog)
  or into the report's bootstrap_log field.

  NOTE: this file is intentionally pure ASCII. Windows PowerShell 5.1 reads
  BOM-less UTF-8 .ps1 files as ANSI, which would corrupt non-ASCII text.
#>
[CmdletBinding()]
param(
    [string] $SkillDir,
    [switch] $NoFix,
    [switch] $VerboseLog,
    [switch] $SkipNetwork,
    [switch] $PrepareGui,
    [switch] $ForcePortable,
    [switch] $Readable,
    [string] $LocalZip,
    [string] $CookieFile,
    [string] $PythonOverride
)

$ErrorActionPreference = 'Continue'   # native stderr must never become a terminating error
$ProgressPreference   = 'SilentlyContinue'

# Python writes UTF-8 on stdout. Windows PowerShell 5.1 otherwise decodes it
# with the OEM/ANSI code page and corrupts every non-ASCII character.
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
        error         = $reason
        python        = [ordered]@{ cmd = ''; version = ''; source = 'none'; portable = $false }
        bootstrap_log = $log.ToArray()
        blockers      = @($reason)
        hints         = @(
            'Set QUARK_INSTALLER_PYTHON to the absolute path of a Python 3.9+ interpreter.',
            'WorkBuddy ships one at: <install dir>\resources\vendor\python\python.exe',
            'A portable interpreter is only auto-downloaded when it matches a pinned SHA256 fingerprint; see bootstrap_log for the rejection reason.',
            'Then re-run this bootstrap script.'
        )
    }
    Write-Output ($obj | ConvertTo-Json -Depth 6 -Compress)
}

# ---- resolve skill / preflight paths ---------------------------------------
if (-not $SkillDir) { $SkillDir = Split-Path -Parent $PSScriptRoot }
try {
    $SkillDir = (Resolve-Path -LiteralPath $SkillDir).Path
} catch {
    Emit-Fallback ("Cannot resolve SkillDir: " + $_.Exception.Message)
    exit 1
}
$preflight = Join-Path $SkillDir 'scripts\preflight.py'
if (-not (Test-Path -LiteralPath $preflight -PathType Leaf)) {
    Emit-Fallback ("preflight.py is missing: " + $preflight)
    exit 1
}

$cfg = $env:WORKBUDDY_CONFIG_DIR
if (-not $cfg) { $cfg = Join-Path $env:USERPROFILE '.workbuddy' }
$runtimeDir  = Join-Path $cfg 'runtimes\quark-installer'
# Everything this skill writes stays under $runtimeDir. ~/Downloads is only
# READ (scanned for a zip the user downloaded themselves in the GUI/manual
# routes); nothing is ever saved there by this script.
$downloadDir = Join-Path $runtimeDir 'downloads'
$scanDirs    = @((Join-Path $env:USERPROFILE 'Downloads'))
# Install into the SAME skills root this skill was loaded from (found by walking
# up from $SkillDir), not a hardcoded ~/.workbuddy/skills: hosts mount skills
# under different roots and a wrong root means the skill never loads there.
$skillsDir   = Split-Path -Parent $SkillDir
if ((Split-Path -Leaf $skillsDir) -inotmatch '^(\.?skills)$') {
    $skillsDir = Join-Path $cfg 'skills'
}

# ---- collect Python candidates ---------------------------------------------
$candidates = New-Object System.Collections.Generic.List[object]
function Add-Candidate([string]$path, [string]$source) {
    if ($path -and (Test-Path -LiteralPath $path -PathType Leaf)) {
        [void]$candidates.Add([pscustomobject]@{ Path = $path; Source = $source })
    }
}

# 1. explicit override
$override = $PythonOverride
if (-not $override) { $override = $env:QUARK_INSTALLER_PYTHON }
if ($override) { Add-Candidate $override 'explicit_override' }

# 2. WorkBuddy bundled vendor Python (ships with every WorkBuddy install)
$roots = New-Object System.Collections.Generic.List[string]
if ($env:WORKBUDDY_RESOURCES_PATH) { [void]$roots.Add($env:WORKBUDDY_RESOURCES_PATH) }
if ($env:WORKBUDDY_APP_PATH) {
    $r = Split-Path -Parent $env:WORKBUDDY_APP_PATH
    if ($r) { [void]$roots.Add($r) }
}
try {
    $proc = Get-Process -Name 'WorkBuddy' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc -and $proc.Path) {
        $ir = Split-Path -Parent $proc.Path
        if ($ir) { [void]$roots.Add((Join-Path $ir 'resources')) }
    }
} catch { }
$pfRoot = if ($env:ProgramFiles) { $env:ProgramFiles } else { 'C:\Program Files' }
foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\WorkBuddy\resources'),
        (Join-Path $pfRoot 'WorkBuddy\resources'),
        'C:\Program Files\WorkBuddy\resources')) {
    if ($p) { [void]$roots.Add($p) }
}
foreach ($r in ($roots | Select-Object -Unique)) {
    if (-not $r) { continue }
    Add-Candidate (Join-Path $r 'vendor\python\python.exe')  'workbuddy_vendor'
    Add-Candidate (Join-Path $r 'vendor\python\python3.exe') 'workbuddy_vendor'
}

# 3. WorkBuddy managed Python
$versionsDir = Join-Path $cfg 'binaries\python\versions'
if (Test-Path -LiteralPath $versionsDir) {
    Get-ChildItem -LiteralPath $versionsDir -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | ForEach-Object {
            Add-Candidate (Join-Path $_.FullName 'python.exe')      'workbuddy_managed'
            Add-Candidate (Join-Path $_.FullName 'bin\python3')     'workbuddy_managed'
            Add-Candidate (Join-Path $_.FullName 'bin\python3.exe') 'workbuddy_managed'
        }
}

# 4. PATH interpreters
foreach ($n in @('python', 'python3')) {
    try {
        $c = Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($c -and $c.Source) { Add-Candidate $c.Source 'system_path' }
    } catch { }
}
try {
    $py = Get-Command 'py' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($py -and $py.Source) {
        $real = & $py.Source -3 -c 'import sys;print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $real) {
            Add-Candidate (($real | Select-Object -Last 1).ToString().Trim()) 'py_launcher'
        }
    }
} catch { }

# 5. common system installs + previously downloaded portable runtimes
$globs = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe'),
    'C:\Python3*\python.exe',
    'D:\Python3*\python.exe'
)
foreach ($g in $globs) {
    if (-not $g) { continue }
    Get-ChildItem -Path $g -ErrorAction SilentlyContinue | ForEach-Object {
        Add-Candidate $_.FullName 'common_install'
    }
}
if (Test-Path -LiteralPath $runtimeDir) {
    Get-ChildItem -LiteralPath $runtimeDir -Directory -Filter 'python-*-embed-*' -ErrorAction SilentlyContinue |
        ForEach-Object { Add-Candidate (Join-Path $_.FullName 'python.exe') 'reused_runtime' }
    Get-ChildItem -LiteralPath $runtimeDir -Directory -Filter 'python-*-standalone-*' -ErrorAction SilentlyContinue |
        ForEach-Object { Add-Candidate (Join-Path $_.FullName 'python.exe') 'reused_runtime' }
}

# ---- validate candidates ----------------------------------------------------
# No string literals inside the probe: avoids PowerShell native-arg quoting traps.
$probe = 'import sys,ssl,zipfile,urllib.request,json,argparse,pathlib;print(sys.version_info[:3])'
function Test-Python([string]$path) {
    try {
        $out = & $path -c $probe 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        # Never use Out-String here: it wraps long lines at the console width
        # and can inject newlines into the captured text.
        $txt = ($out -join "`n")
        $m = [regex]::Match($txt, '\((\d+),\s*(\d+),\s*(\d+)\)')
        if (-not $m.Success) { return $null }
        $maj = [int]$m.Groups[1].Value
        $min = [int]$m.Groups[2].Value
        if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 9)) { return $null }
        return ('{0}.{1}.{2}' -f $maj, $min, [int]$m.Groups[3].Value)
    } catch { return $null }
}

$pythonCmd    = ''
$pythonSource = ''
$pythonVer    = ''
$portable     = $false
if ($ForcePortable) {
    Note '-ForcePortable: skipping interpreter discovery, provisioning a portable runtime'
} else {
    foreach ($c in $candidates) {
        $v = Test-Python $c.Path
        if ($v) {
            $pythonCmd = $c.Path; $pythonSource = $c.Source; $pythonVer = $v
            Note ("Resolved Python {0} from {1} ({2})" -f $v, $c.Source, $c.Path)
            break
        }
    }
}

# ---- pinned portable runtimes ----------------------------------------------
# A downloaded interpreter is executable code we then run, so it is verified
# against a fixed fingerprint, never against "it downloaded, so it is fine".
#   size   : exact byte length of the official archive
#   sha256 : primary integrity pin
#   md5    : the checksum python.org publishes on its release page (independent
#            second opinion; a mirror serving a substituted file fails both)
# Adding a version/arch here is the only supported way to enable it.
$PinnedPython = @{
    '3.12.7|amd64' = @{
        file   = 'python-3.12.7-embed-amd64.zip'
        size   = [int64]11062583
        sha256 = '0d57bb6cb078b74d23dbfe91f77d6780d45bed328911609f1f7ee2ba1606bf44'
        md5    = '4c0a5a44d4ca1d0bc76fe08ea8b76adc'
    }
    '3.12.7|arm64' = @{
        file   = 'python-3.12.7-embed-arm64.zip'
        size   = [int64]10318404
        sha256 = 'f4217333d32cecf723d81c0cede4778ccff391f5b71b9404cfbb2d0788ef1c12'
        md5    = '6fc899d8dbd46dd2b585a038f7cf68a4'
    }
}

function Get-Digest([string]$path, [string]$algo) {
    try {
        return (Get-FileHash -LiteralPath $path -Algorithm $algo -ErrorAction Stop).Hash.ToLowerInvariant()
    } catch { return '' }
}

function Test-PinnedArtifact([string]$path, $spec) {
    try {
        $len = (Get-Item -LiteralPath $path -ErrorAction Stop).Length
    } catch {
        return @{ ok = $false; reason = 'cannot stat downloaded file' }
    }
    if ($spec.size -gt 0 -and $len -ne [int64]$spec.size) {
        return @{ ok = $false; reason = ("size mismatch: got $len, expected " + $spec.size) }
    }
    if ($spec.sha256) {
        $h = Get-Digest $path 'SHA256'
        if ($h -ne $spec.sha256) { return @{ ok = $false; reason = ("sha256 mismatch: got '$h'") } }
    }
    if ($spec.md5) {
        $m = Get-Digest $path 'MD5'
        if ($m -ne $spec.md5) { return @{ ok = $false; reason = ("md5 mismatch: got '$m'") } }
    }
    return @{ ok = $true; reason = 'fingerprint match' }
}

function Get-EmbedLayoutProblem([string]$dir) {
    if (-not (Test-Path -LiteralPath (Join-Path $dir 'python.exe') -PathType Leaf)) { return 'python.exe missing' }
    $std = Get-ChildItem -LiteralPath $dir -Filter 'python3*.zip' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $std) { return 'standard-library zip (python3xx.zip) missing' }
    if (-not (Test-Path -LiteralPath (Join-Path $dir '_ssl.pyd'))) { return '_ssl.pyd missing (no HTTPS support)' }
    return ''
}

function Get-SignatureInfo([string]$path) {
    try {
        $s = Get-AuthenticodeSignature -LiteralPath $path -ErrorAction Stop
        $subj = ''
        if ($s.SignerCertificate) { $subj = [string]$s.SignerCertificate.Subject }
        return @{ status = [string]$s.Status; subject = $subj }
    } catch {
        return @{ status = 'Unavailable'; subject = '' }
    }
}

function Write-Provenance($dir, $info) {
    try {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        $f = Join-Path $dir 'python-provenance.json'
        # BOM-less UTF-8: PowerShell 5.1's Set-Content -Encoding UTF8 adds a BOM,
        # which breaks json.load() on the Python side.
        $json = $info | ConvertTo-Json -Depth 5
        [System.IO.File]::WriteAllText($f, $json, (New-Object System.Text.UTF8Encoding($false)))
        Note ("Provenance recorded at " + $f)
    } catch {
        Note ("Could not write provenance file: " + $_.Exception.Message)
    }
}

# A rejected extraction must not stay where the candidate scan would pick it up
# again on the next run. It is moved into _rejected/ (never deleted), so the
# next run re-downloads instead of silently reusing something unverified.
function Move-RejectedRuntime([string]$dir) {
    try {
        $leaf = Split-Path -Leaf $dir
        if ($leaf -notmatch '^python-[\d.]+-embed-') { return }
        $full = (Resolve-Path -LiteralPath $dir).Path
        if (-not $full.StartsWith($runtimeDir, [System.StringComparison]::OrdinalIgnoreCase)) { return }
        $q = Join-Path $runtimeDir '_rejected'
        New-Item -ItemType Directory -Force -Path $q | Out-Null
        $target = Join-Path $q ($leaf + '-' + (Get-Date).ToString('yyyyMMdd-HHmmss'))
        Move-Item -LiteralPath $full -Destination $target -Force -ErrorAction Stop
        Note ("Moved rejected runtime to " + $target + " (left in place; nothing deleted)")
    } catch {
        Note ("Could not quarantine rejected runtime: " + $_.Exception.Message)
    }
}

# ---- auto-provision: download embeddable Python when nothing works ----------
if (-not $pythonCmd) {
    Note 'No usable Python found; preparing a portable runtime automatically'
    $pyver   = '3.12.7'
    $arch    = 'amd64'
    if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'arm64' }
    $key     = "$pyver|$arch"
    $spec    = $PinnedPython[$key]
    $zipName = "python-$pyver-embed-$arch.zip"
    $dest    = Join-Path $runtimeDir "python-$pyver-embed-$arch"
    $destPy  = Join-Path $dest 'python.exe'

    # Optional explicit artifact for enterprise mirrors / air-gapped staging.
    # A checksum is mandatory there too: an unverified override defeats the point.
    $customUrl = $env:QSI_PYTHON_ZIP_URL
    $customSha = $env:QSI_PYTHON_ZIP_SHA256
    if ($customUrl) {
        if (-not $customSha -or $customSha -notmatch '^[0-9a-fA-F]{64}$') {
            Note ('QSI_PYTHON_ZIP_URL is set but QSI_PYTHON_ZIP_SHA256 is missing or not a 64-char hex digest; ignoring the override and falling back to the pinned default mirrors')
            $customUrl = ''
        } else {
            $spec = @{ file = $zipName; size = [int64]0; sha256 = $customSha.ToLowerInvariant(); md5 = '' }
            Note 'Using QSI_PYTHON_ZIP_URL with a caller-supplied SHA256 pin'
        }
    }

    if (-not $spec) {
        Note ("No pinned fingerprint for Python $pyver/$arch; refusing to download an unverified interpreter. " +
              "Add an entry to `$PinnedPython, or set QUARK_INSTALLER_PYTHON to a Python 3.9+ executable.")
    }

    $downloaded = $false
    $verifyNote = ''
    if ($spec -and -not (Test-Path -LiteralPath $destPy)) {
        New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
        $dl = Join-Path $runtimeDir '_download'
        New-Item -ItemType Directory -Force -Path $dl | Out-Null
        $zipPath = Join-Path $dl $zipName
        $partPath = $zipPath + '.part'
        if ($customUrl) {
            $mirrors = @($customUrl)
        } else {
            $mirrors = @(
                "https://mirrors.huaweicloud.com/python/$pyver/$zipName",
                "https://registry.npmmirror.com/-/binary/python/$pyver/$zipName",
                "https://www.python.org/ftp/python/$pyver/$zipName"
            )
        }
        foreach ($u in $mirrors) {
            try {
                if ($u -notmatch '^https://') { throw 'refusing non-HTTPS download URL' }
                # Best-effort cleanup of a leftover .part file; a host-level
                # delete policy must never abort the download itself.
                try {
                    if (Test-Path -LiteralPath $partPath) { Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue }
                } catch { }
                Invoke-WebRequest -Uri $u -OutFile $partPath -UseBasicParsing -TimeoutSec 180
                $check = Test-PinnedArtifact $partPath $spec
                if (-not $check.ok) {
                    try { Remove-Item -LiteralPath $partPath -Force -ErrorAction SilentlyContinue } catch { }
                    throw ("fingerprint rejected: " + $check.reason)
                }
                Move-Item -LiteralPath $partPath -Destination $zipPath -Force
                $downloaded = $true
                $verifyNote = 'size+sha256+md5 matched pinned python.org values'
                Note ("Downloaded and verified portable Python from " + $u + " (" + $check.reason + ")")
                break
            } catch {
                Note ("Mirror failed: " + $u + " :: " + $_.Exception.Message)
            }
        }
        if (-not $downloaded) {
            Note 'No mirror produced a file matching the pinned fingerprint; not extracting anything'
        }
        if ($downloaded) {
            try {
                # Use .NET directly: Expand-Archive renders a noisy progress bar
                # into the host stream even with $ProgressPreference suppressed.
                Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
                if (-not (Test-Path -LiteralPath $dest)) {
                    New-Item -ItemType Directory -Force -Path $dest | Out-Null
                }
                [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $dest)
                Note ("Extracted portable Python to " + $dest)
            } catch {
                Note ("Extract failed: " + $_.Exception.Message)
            }
        }
    } elseif ($spec) {
        Note ("Reusing previously downloaded portable Python at " + $dest)
    }

    # Structure + signature gate before the interpreter is ever executed.
    # Signature policy (matches the documented promise exactly):
    #   Valid + Python Software Foundation  -> pass (independent proof)
    #   HashMismatch                        -> reject (bytes changed after signing)
    #   NotSigned                           -> reject, unless QSI_ALLOW_UNSIGNED=1
    #                                          (official packages are always signed)
    #   NotTrusted / UnknownError / Unavailable
    #                                       -> warn and continue on the pinned
    #                                          fingerprint alone: this is a local
    #                                          trust-store / offline condition,
    #                                          not evidence about the bytes
    if (Test-Path -LiteralPath $destPy) {
        $layoutProblem = Get-EmbedLayoutProblem $dest
        $sig = Get-SignatureInfo $destPy
        $sigVerdict = ''
        $reject = $false
        if ($layoutProblem) {
            $reject = $true
            $sigVerdict = 'layout-rejected'
            Note ("Portable runtime rejected: " + $layoutProblem)
        } elseif ($sig.status -eq 'HashMismatch') {
            $reject = $true
            $sigVerdict = 'signature-hash-mismatch'
            Note 'Portable runtime rejected: python.exe signature is invalid (content modified after signing)'
        } elseif ($sig.status -eq 'NotSigned') {
            if ($env:QSI_ALLOW_UNSIGNED -eq '1') {
                $sigVerdict = 'unsigned-allowed'
                Note 'python.exe is NOT signed; continuing only because QSI_ALLOW_UNSIGNED=1 (pinned fingerprint matched)'
            } else {
                $reject = $true
                $sigVerdict = 'unsigned-rejected'
                Note 'Portable runtime rejected: python.exe is not Authenticode-signed (official packages always are); set QSI_ALLOW_UNSIGNED=1 only if you built this archive yourself'
            }
        } elseif ($sig.status -eq 'Valid' -and $sig.subject -match 'Python Software Foundation') {
            $sigVerdict = 'valid-psf'
            Note 'Authenticode OK: python.exe signed by Python Software Foundation'
        } elseif ($sig.status -eq 'Valid') {
            # Signed and the signature verifies, but by somebody else. That is a
            # repacked or republished archive, not an officially signed one, so
            # it must not be laundered into 'signature-unverifiable' (which
            # means "this machine could not check"). Reject unless the user
            # says the archive is their own repack.
            $who = if ($sig.subject) { $sig.subject } else { 'an unknown publisher' }
            if ($env:QSI_ALLOW_UNSIGNED -eq '1') {
                $sigVerdict = 'foreign-signer-allowed'
                Note ("python.exe is signed by " + $who + " (not Python Software Foundation); continuing only because QSI_ALLOW_UNSIGNED=1")
            } else {
                $reject = $true
                $sigVerdict = 'foreign-signer-rejected'
                Note ("Portable runtime rejected: python.exe is signed by " + $who + ", not Python Software Foundation; use QSI_ALLOW_UNSIGNED=1 only for an archive you repacked yourself")
            }
        } else {
            $sigVerdict = 'signature-unverifiable'
            Note ("Authenticode not conclusive (status=" + $sig.status + "): local certificate-trust or offline condition; accepting on the pinned fingerprint alone")
        }

        if ($reject) {
            $pythonCmd = ''
            Move-RejectedRuntime $dest
        } else {
            $v = Test-Python $destPy
            if ($v) {
                $pythonCmd = $destPy
                $pythonSource = if ($downloaded) { 'portable_downloaded' } else { 'reused_runtime' }
                $pythonVer = $v; $portable = $true
                Note ("Portable Python ready: " + $destPy + " (" + $v + ")")
                Write-Provenance $runtimeDir ([ordered]@{
                        file               = $zipName
                        requested_from     = if ($customUrl) { 'QSI_PYTHON_ZIP_URL' } else { 'pinned_mirrors' }
                        size               = if ($spec) { $spec.size } else { 0 }
                        sha256             = if ($spec) { $spec.sha256 } else { '' }
                        md5                = if ($spec) { $spec.md5 } else { '' }
                        verification       = if ($verifyNote) { $verifyNote } else { 'reused previously verified runtime' }
                        signature_status   = $sig.status
                        signature_verdict  = $sigVerdict
                        signer             = $sig.subject
                        python_version     = $v
                        interpreter        = $destPy
                        verified_at        = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                    })
            } else {
                Note ("Portable Python failed the probe: " + $destPy)
                Move-RejectedRuntime $dest
            }
        }
    }
}

if (-not $pythonCmd) {
    $why = 'Unable to locate or auto-provision a usable Python 3.9+ interpreter (offline and no bundled runtime).'
    $rejected = $log | Where-Object { $_ -match 'fingerprint rejected|No mirror produced|rejected:|refusing to download' } |
        Select-Object -First 1
    if ($rejected) {
        $why = 'No usable Python, and the automatic download was refused by the integrity check (pinned fingerprint / layout / signature). Nothing was extracted. Details: ' + $rejected
    }
    Emit-Fallback $why
    exit 1
}

# ---- hand off to preflight.py ----------------------------------------------
$env:QSI_PYTHON_SOURCE   = $pythonSource
$env:QSI_PYTHON_PORTABLE = if ($portable) { '1' } else { '0' }
$env:QSI_BOOTSTRAP_LOG   = ($log -join $LOG_SEP)
$env:QSI_RUNTIME_DIR     = $runtimeDir
$env:QSI_DOWNLOAD_DIR    = $downloadDir
$env:QSI_SCAN_DIRS       = ($scanDirs -join ';')
$env:QSI_SKILLS_DIR      = $skillsDir
if ($LocalZip)   { $env:QSI_LOCAL_ZIP   = $LocalZip }
if ($CookieFile) { $env:QSI_COOKIE_FILE = $CookieFile }

$reportFile = Join-Path $runtimeDir 'last_preflight.json'
$pfArgs = @('--json')
if ($NoFix)       { $pfArgs += '--no-fix' }
if ($SkipNetwork) { $pfArgs += '--skip-network' }
if ($PrepareGui)  { $pfArgs += '--prepare-gui' }
if ($LocalZip)    { $pfArgs += @('--local-zip', $LocalZip) }
if ($CookieFile)  { $pfArgs += @('--cookie-file', $CookieFile) }
$pfArgs += @('--python-source', $pythonSource)
$pfArgs += @('--report-file', $reportFile)
if (-not $Readable) { $pfArgs += '--ascii-json' }
if ($portable)      { $pfArgs += '--python-portable' }

$raw  = & $pythonCmd $preflight @pfArgs 2>$null
# Join lines directly. Out-String would wrap long JSON lines at the host width,
# inserting newlines that make the JSON invalid.
$text = ($raw -join "`n").Trim()

if ($VerboseLog) {
    foreach ($l in $log) { [Console]::Error.WriteLine('[bootstrap] ' + $l) }
}
if (-not $text -or -not $text.StartsWith('{')) {
    Emit-Fallback ("preflight.py produced no JSON (exit=" + $LASTEXITCODE + ")")
    exit 1
}
Write-Output $text
