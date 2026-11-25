param(
  [Parameter(Mandatory = $true)][string]$Op,
  [string]$Json = '{}'
)
$ErrorActionPreference = 'Stop'

# 统一 UTF-8，避免中文题干/答案在 stdin/stdout 上乱码
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$src = @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public class NX {
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, IntPtr e);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] p, int cb);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr ctx);

    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public InputUnion U; }
    [StructLayout(LayoutKind.Explicit)] public struct InputUnion {
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public KEYBDINPUT ki;
        [FieldOffset(0)] public HARDWAREINPUT hi;
    }
    [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] public struct HARDWAREINPUT { public uint uMsg; public ushort wParamL; public ushort wParamH; }

    const uint UNICODE = 0x0004;
    const uint KEYUP = 0x0002;

    public static void TypeText(string s) {
        foreach (char c in s) {
            if (c == '\r') continue;
            if (c == '\n') { TapVk(0x0D); continue; }
            INPUT[] a = new INPUT[2];
            a[0].type = 1; a[0].U.ki.wScan = (ushort)c; a[0].U.ki.dwFlags = UNICODE;
            a[1].type = 1; a[1].U.ki.wScan = (ushort)c; a[1].U.ki.dwFlags = UNICODE | KEYUP;
            SendInput(2, a, Marshal.SizeOf(typeof(INPUT)));
            System.Threading.Thread.Sleep(4);
        }
    }

    public static void TapVk(ushort vk) {
        INPUT[] a = new INPUT[2];
        a[0].type = 1; a[0].U.ki.wVk = vk; a[0].U.ki.dwFlags = 0;
        a[1].type = 1; a[1].U.ki.wVk = vk; a[1].U.ki.dwFlags = KEYUP;
        SendInput(2, a, Marshal.SizeOf(typeof(INPUT)));
        System.Threading.Thread.Sleep(30);
    }

    public static void KeyCombo(string combo) {
        string[] parts = combo.ToLower().Split('+');
        ushort[] mods = new ushort[parts.Length - 1];
        int mc = 0;
        for (int i = 0; i < parts.Length - 1; i++) {
            string m = parts[i].Trim();
            if (m == "ctrl" || m == "control") mods[mc++] = 0x11;
            else if (m == "alt") mods[mc++] = 0x12;
            else if (m == "shift") mods[mc++] = 0x10;
            else if (m == "win") mods[mc++] = 0x5B;
        }
        ushort vk = VkOf(parts[parts.Length - 1].Trim());
        for (int i = 0; i < mc; i++) TapDown(mods[i]);
        TapVk(vk);
        for (int i = mc - 1; i >= 0; i--) TapUp(mods[i]);
    }

    static void TapDown(ushort vk) { INPUT[] a = new INPUT[1]; a[0].type = 1; a[0].U.ki.wVk = vk; SendInput(1, a, Marshal.SizeOf(typeof(INPUT))); System.Threading.Thread.Sleep(15); }
    static void TapUp(ushort vk) { INPUT[] a = new INPUT[1]; a[0].type = 1; a[0].U.ki.wVk = vk; a[0].U.ki.dwFlags = KEYUP; SendInput(1, a, Marshal.SizeOf(typeof(INPUT))); System.Threading.Thread.Sleep(15); }

    public static ushort VkOf(string k) {
        if (k.Length == 1) {
            char c = char.ToUpperInvariant(k[0]);
            if (c >= 'A' && c <= 'Z') return (ushort)c;
            if (c >= '0' && c <= '9') return (ushort)c;
        }
        switch (k) {
            case "enter": case "return": return 0x0D;
            case "tab": return 0x09;
            case "esc": case "escape": return 0x1B;
            case "space": return 0x20;
            case "backspace": return 0x08;
            case "delete": case "del": return 0x2E;
            case "left": return 0x25; case "up": return 0x26; case "right": return 0x27; case "down": return 0x28;
            case "home": return 0x24; case "end": return 0x23;
            case "pageup": case "pgup": return 0x21; case "pagedown": case "pgdn": return 0x22;
            default: throw new Exception("unknown key: " + k);
        }
    }

    public static void ScrollAt(int x, int y, int clicks) {
        if (x >= 0 && y >= 0) SetCursorPos(x, y);
        System.Threading.Thread.Sleep(60);
        int n = clicks < 0 ? -clicks : clicks;
        int delta = clicks > 0 ? 120 : -120;
        for (int i = 0; i < n; i++) {
            mouse_event(0x0800, 0, 0, (uint)delta, IntPtr.Zero);
            System.Threading.Thread.Sleep(50);
        }
    }

    public static void ClickAt(int x, int y, int clicks) {
        if (x >= 0 && y >= 0) SetCursorPos(x, y);
        System.Threading.Thread.Sleep(60);
        for (int i = 0; i < clicks; i++) {
            mouse_event(0x0002, 0, 0, 0, IntPtr.Zero);
            System.Threading.Thread.Sleep(30);
            mouse_event(0x0004, 0, 0, 0, IntPtr.Zero);
            System.Threading.Thread.Sleep(60);
        }
    }
}
'@

if (-not ("NX" -as [type])) {
  Add-Type -TypeDefinition $src
}

# 关键：必须在加载 System.Windows.Forms 之前声明 DPI 感知。
# 否则 WinForms 先缓存了逻辑像素（150% 缩放下 1707x1067），
# 而截图/点击实际是物理像素（2560x1600），坐标会差 1.5 倍、全部点偏。
[void][NX]::SetProcessDPIAware()
# 从 node 启动时子进程会继承父进程的 DPI 模式（通常是 unaware），
# SetProcessDPIAware 会被忽略；必须再强制线程上下文为 PER_MONITOR_AWARE_V2 (-4)。
[void][NX]::SetThreadDpiAwarenessContext([IntPtr](-4))

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { $raw = $Json }
$o = $raw | ConvertFrom-Json

function Send-Result($obj) {
  $obj | ConvertTo-Json -Depth 8 -Compress
}

try {
  switch ($Op) {
    'info' {
      $p = New-Object 'NX+POINT'
      [void][NX]::GetCursorPos([ref]$p)
      $fg = [NX]::GetForegroundWindow()
      $sb = New-Object System.Text.StringBuilder 512
      [void][NX]::GetWindowText($fg, $sb, 512)
      $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
      Send-Result @{
        ok = $true
        cursor = @{ x = $p.X; y = $p.Y }
        foreground = @{ handle = $fg.ToInt64(); title = $sb.ToString() }
        primaryScreen = @{ x = $b.X; y = $b.Y; width = $b.Width; height = $b.Height }
      }
    }
    'screenshot' {
      $path = [string]$o.path
      if ([string]::IsNullOrWhiteSpace($path)) { throw 'screenshot requires path' }
      $dir = Split-Path -Parent $path
      if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
      if ($o.region) {
        $b = New-Object System.Drawing.Rectangle([int]$o.region.x, [int]$o.region.y, [int]$o.region.width, [int]$o.region.height)
      } else {
        $b = [System.Windows.Forms.SystemInformation]::VirtualScreen
      }
      $bmp = New-Object System.Drawing.Bitmap($b.Width, $b.Height)
      $g = [System.Drawing.Graphics]::FromImage($bmp)
      $g.CopyFromScreen($b.X, $b.Y, 0, 0, $bmp.Size)
      $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
      $g.Dispose(); $bmp.Dispose()
      Send-Result @{ ok = $true; path = $path; width = $b.Width; height = $b.Height; x = $b.X; y = $b.Y }
    }
    'move' {
      $x = [int]$o.x
      $y = [int]$o.y
      [void][NX]::SetCursorPos($x, $y)
      Send-Result @{ ok = $true; x = $x; y = $y }
    }
    'click' {
      $clicks = 1
      if ($null -ne $o.clicks) { $clicks = [int]$o.clicks }
      [NX]::ClickAt([int]$o.x, [int]$o.y, $clicks)
      Send-Result @{ ok = $true; x = [int]$o.x; y = [int]$o.y; clicks = $clicks }
    }
    'scroll' {
      [NX]::ScrollAt([int]$o.x, [int]$o.y, [int]$o.clicks)
      Send-Result @{ ok = $true; x = [int]$o.x; y = [int]$o.y; clicks = [int]$o.clicks }
    }
    'type' {
      $text = [string]$o.text
      if ($text.Length -eq 0) { throw 'type requires non-empty text' }
      [NX]::TypeText($text)
      Send-Result @{ ok = $true; chars = $text.Length }
    }
    'paste' {
      $text = [string]$o.text
      if ($text.Length -eq 0) { throw 'paste requires non-empty text' }
      Set-Clipboard -Value $text
      Start-Sleep -Milliseconds 120
      [NX]::KeyCombo('ctrl+v')
      Send-Result @{ ok = $true; chars = $text.Length }
    }
    'key' {
      $keys = @($o.keys)
      foreach ($k in $keys) { [NX]::KeyCombo([string]$k) }
      Send-Result @{ ok = $true; keys = $keys }
    }
    'activate' {
      $title = [string]$o.title
      if ([string]::IsNullOrWhiteSpace($title)) { throw 'activate requires title' }
      $proc = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$title*" } | Select-Object -First 1
      if (-not $proc) { throw "no window found with title containing '$title'" }
      $h = $proc.MainWindowHandle
      if ([NX]::IsIconic($h)) { [void][NX]::ShowWindow($h, 9) }
      [void][NX]::BringWindowToTop($h)
      [void][NX]::SetForegroundWindow($h)
      Start-Sleep -Milliseconds 250
      Send-Result @{ ok = $true; title = $proc.MainWindowTitle; handle = $h.ToInt64() }
    }
    'topmost' {
      $title = [string]$o.title
      if ([string]::IsNullOrWhiteSpace($title)) { throw 'topmost requires title' }
      $proc = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$title*" } | Select-Object -First 1
      if (-not $proc) { throw "no window found with title containing '$title'" }
      $h = $proc.MainWindowHandle
      if ([NX]::IsIconic($h)) { [void][NX]::ShowWindow($h, 9) }
      $off = $false
      if ($null -ne $o.off) { $off = [bool]$o.off }
      $after = if ($off) { [IntPtr](-2) } else { [IntPtr](-1) }
      [void][NX]::SetWindowPos($h, $after, 0, 0, 0, 0, 0x0003)
      if (-not $off) { [void][NX]::SetForegroundWindow($h) }
      Start-Sleep -Milliseconds 250
      Send-Result @{ ok = $true; title = $proc.MainWindowTitle; topmost = (-not $off) }
    }
    'minimize' {
      $h = [IntPtr]::Zero
      $label = ''
      if ($o.front) {
        $h = [NX]::GetForegroundWindow()
        $sb = New-Object System.Text.StringBuilder 512
        [void][NX]::GetWindowText($h, $sb, 512)
        $label = $sb.ToString()
      } else {
        $title = [string]$o.title
        if ([string]::IsNullOrWhiteSpace($title)) { throw 'minimize requires --front or title' }
        $proc = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$title*" } | Select-Object -First 1
        if (-not $proc) { throw "no window found with title containing '$title'" }
        $h = $proc.MainWindowHandle
        $label = $proc.MainWindowTitle
      }
      if ($h -eq [IntPtr]::Zero) { throw 'no foreground window' }
      [void][NX]::ShowWindow($h, 6)
      Send-Result @{ ok = $true; title = $label; minimized = $true; handle = $h.ToInt64() }
    }
    'batch' {
      $results = New-Object System.Collections.ArrayList
      foreach ($a in @($o.actions)) {
        switch ([string]$a.op) {
          'click' {
            $c = 1; if ($null -ne $a.clicks) { $c = [int]$a.clicks }
            [NX]::ClickAt([int]$a.x, [int]$a.y, $c)
            [void]$results.Add(@{ op = 'click'; x = [int]$a.x; y = [int]$a.y })
          }
          'paste' {
            Set-Clipboard -Value ([string]$a.text)
            Start-Sleep -Milliseconds 100
            [NX]::KeyCombo('ctrl+v')
            [void]$results.Add(@{ op = 'paste'; chars = ([string]$a.text).Length })
          }
          'type' {
            [NX]::TypeText([string]$a.text)
            [void]$results.Add(@{ op = 'type'; chars = ([string]$a.text).Length })
          }
          'key' {
            $ks = @($a.keys)
            foreach ($k in $ks) { [NX]::KeyCombo([string]$k) }
            [void]$results.Add(@{ op = 'key'; keys = $ks })
          }
          'sleep' {
            Start-Sleep -Milliseconds ([int]$a.ms)
            [void]$results.Add(@{ op = 'sleep'; ms = [int]$a.ms })
          }
          default { [void]$results.Add(@{ op = [string]$a.op; error = 'unknown' }) }
        }
        Start-Sleep -Milliseconds 80
      }
      Send-Result @{ ok = $true; count = $results.Count; results = $results }
    }
    default { throw "unknown op '$Op'" }
  }
} catch {
  Send-Result @{ ok = $false; error = $_.Exception.Message }
  exit 1
}
