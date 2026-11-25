param([string]$Json = '{}')
$ErrorActionPreference = 'Stop'

[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { $raw = $Json }
$o = $raw | ConvertFrom-Json

$title = 'iTEST'
if ($o.title) { $title = [string]$o.title }
$out = 'shots/uia.json'
if ($o.out) { $out = [string]$o.out }

function Send-Result($obj) { $obj | ConvertTo-Json -Depth 6 -Compress }

try {
  $proc = Get-Process |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$title*" } |
    Select-Object -First 1
  if (-not $proc) { throw "没有标题包含 '$title' 的窗口" }

  $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
  $cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::IsOffscreenProperty, $false)
  $all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)

  $items = New-Object System.Collections.ArrayList
  for ($i = 0; $i -lt $all.Count; $i++) {
    $e = $all.Item($i)
    $n = $e.Current.Name
    if ([string]::IsNullOrWhiteSpace($n)) { continue }
    $r = $e.Current.BoundingRectangle
    if ($r.Width -le 0 -or $r.Height -le 0) { continue }
    $txt = if ($n.Length -gt 160) { $n.Substring(0, 160) } else { $n }
    [void]$items.Add([pscustomobject]@{
      type = ($e.Current.ControlType.ProgrammaticName -replace 'ControlType\.', '')
      name = $txt
      x    = [int]$r.X
      y    = [int]$r.Y
      w    = [int]$r.Width
      h    = [int]$r.Height
      cx   = [int]($r.X + $r.Width / 2)
      cy   = [int]($r.Y + $r.Height / 2)
    })
  }

  $dir = Split-Path -Parent $out
  if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  $payload = @{ ok = $true; window = $proc.MainWindowTitle; total = $all.Count; named = $items.Count; items = $items }
  $payload | ConvertTo-Json -Depth 6 -Compress | Set-Content -Path $out -Encoding UTF8
  Send-Result @{ ok = $true; window = $proc.MainWindowTitle; total = $all.Count; named = $items.Count; out = $out }
} catch {
  Send-Result @{ ok = $false; error = $_.Exception.Message }
  exit 1
}
