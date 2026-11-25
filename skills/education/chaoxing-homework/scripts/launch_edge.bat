@echo off
rem 以调试端口启动 Edge（独立 user-data-dir，不影响日常浏览器）
rem 启动后在此窗口手动完成学习通登录，再回到 WorkBuddy 继续。
setlocal
set "PORT=9222"
set "PROFILE=%LOCALAPPDATA%\cx-edge-profile"
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"

if not exist "%EDGE%" (
  echo [ERROR] 未找到 msedge.exe，请把本文件里的 EDGE 改成实际路径
  pause
  exit /b 1
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

echo [1/2] 启动 Edge，调试端口 %PORT%
start "" "%EDGE%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" --no-first-run --no-default-browser-check "https://i.chaoxing.com"

echo [2/2] 等待调试端口就绪...
timeout /t 4 /nobreak >nul
powershell -NoProfile -Command "try{ (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/json/version -TimeoutSec 5).StatusCode }catch{ 'PORT_NOT_READY' }"

echo.
echo 请在打开的 Edge 中扫码登录学习通，登录完成后回到 WorkBuddy 继续。
