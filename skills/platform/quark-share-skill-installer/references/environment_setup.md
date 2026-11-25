# 夸克分享技能安装器 · 环境自检与自动准备规范

本文件是「夸克分享技能安装器」（技术标识 `quark-share-skill-installer`）阶段 P 的参考文档，供需要深入理解或排查环境问题时按需加载。目标是回答一个问题：**一台刚下载安装 WorkBuddy、什么都没配置的电脑，凭什么能直接跑这个技能？**

## 1. 设计原则

1. **零依赖引导层**：自检逻辑不能依赖 Python 本身（否则没 Python 就永远无法自检）。因此入口是纯 PowerShell / Bash 脚本，只依赖操作系统自带组件；Python 定位成功后才调用 Python 写的 `preflight.py` 做深度体检。
2. **先判断、再决定**：`ready=true` 直接继续；`ready=false` 才处理 blockers。绝大多数"缺条件"由脚本静默补齐，Agent 不需要临场发挥。
3. **能自动补的自动补，不能自动补的换路径**：Python / 目录 / 脚本校验都自动补；Cookie 是账号凭据，绝不自动获取；默认的浏览器路径本来就不需要它，连浏览器也不可用时才退到本地 zip 路径。
4. **最小副作用**：只有一个写入根 `<config>/runtimes/quark-installer/`（外加技能安装目录）；`~/Downloads` 只读扫描。不改 PATH、不装系统级软件、不要管理员权限、不删任何已有文件。下载的解释器必须校验后才执行。
5. **机器接口稳定优先**：Windows PowerShell 5.1 会把 UTF-8 的 stdout 按 ANSI/GBK 解码，中文必乱码；`Out-String` 还会按控制台宽度折行破坏 JSON。因此 Windows 下 stdout 输出**纯 ASCII JSON**，完整中文报告以 UTF-8 落盘供文件读取工具查看。

## 2. 条件清单

### 2.1 必需条件（`level=required`，决定 `ready`）

| 检查 ID | 判定 | 自动修复 |
| --- | --- | --- |
| `python_version` | `sys.version_info >= (3, 9)` | 由引导层换用更高版本解释器 |
| `stdlib_modules` | 17 个标准库模块可导入（argparse、json、os、re、sys、time、shutil、zipfile、pathlib、hashlib、datetime、ssl、socket、subprocess、urllib.request、urllib.error、urllib.parse），清单以 `scripts/preflight.py` 里的 `REQUIRED_MODULES` 为准 | 无；不完整就换解释器 |
| `scripts` | 三个业务脚本存在，且各自能被 `--help` 正常加载（同时验证语法与依赖）。这一步是全技能**唯一**执行代码的地方，且执行的是本技能自带脚本，不碰待安装包；要严格零执行就加 `--no-script-probe`，此时只校验文件存在、该项降级为 `warn`（可加载性标记为未验证，不阻塞） | 无；提示重新分发技能包 |
| `scripts.optional`（`level=route`） | `manage_footprint.py` 可加载；缺失/损坏只告警不阻塞——它是唯一被允许删文件的脚本，坏了必须被看见 | 无；提示重新分发技能包 |
| `dir.download` / `dir.skills` / `dir.backup` / `dir.runtime` | 目录存在且可写（写一个探针文件再删掉，只删自己刚创建的文件） | 自动 `mkdir -p` |
| `disk_space` | 下载盘可用空间 ≥ 250 MB | 仅告警，不硬阻塞 |

### 2.1.1 只读与审计项（`level=route`）

| 检查 ID | 说明 |
| --- | --- |
| `dir.scan` | 只读扫描目录（默认 `~/Downloads`）是否存在；只找文件、不写入，永不影响 `ready` |
| `skills_root` | 实际安装根，默认取**本技能自身所在根**；`skills_roots` 列出全部探测到的候选根与 `active` 项 |
| `footprint` | 实测本技能磁盘足迹（总字节数、文件数、逐项 `components`），并给出清理命令提示 |

`blockers[]` 只收集 `level=required` 且 `status=block` 的项；非空即 `ready=false`。

### 2.2 路径条件（`level=route`，不阻塞 `ready`）

| 检查 ID | 影响 |
| --- | --- |
| `network_quark` | 到 `https://pan.quark.cn/` 的连通性；4xx/5xx 也算"主机可达" |
| `cookie` | 只检测 `QUARK_COOKIE` / `--cookie-file` / 本技能 `scripts/cookie.txt` / 各 skills 根下的 `quark-drive/scripts/cookie.txt` 是否存在且非空，**绝不读取内容**（报告里给 `cookie.path`，只给路径不给值）。候选位置由 `scripts/_skills_paths.py` 统一给出：本技能所在根 → `QSI_SKILLS_DIR` → `<config>/skills` → `~/.workbuddy/skills`；`quark_share_download.py` **import 同一个模块**，不是各写一份。否则 `QSI_SKILLS_DIR` 指向工作区 `.skills` 时会出现“预检说有 Cookie、下载说 401”，连 `route` 都会被误判成 `manual` 而绕开 `--route api` |
| `quark_drive_skill` | 是否装有 `quark-drive`（提供 `get_cookie.py` 刷新 Cookie），可选 |
| `gui_control` | Windows 下 `computer-use` 技能或 `workbuddy-computer-use` 插件；或 `desktop-control` 技能 + `agent-desktop` CLI。**只代表"有桌面操控手段"，不代表可以用**：使用前提是主桌面（`window_id: "screen"`），虚拟桌面 / 隔离桌面一律禁用（见 SKILL.md 红线 7） |
| `browser` | Edge / Chrome / Chromium / Firefox / Safari 可执行文件 |
| `local_zip` | 用户传入的本地 zip 是否为有效 zip |

### 2.3 路径决策（`route`）

```
--route 强制值优先        -> api / gui / manual（legacy 路径，仅用户明确要求时）
local_zip 有效           -> local_zip   （跳过下载，直接阶段 3）
浏览器已安装             -> browser     （默认：阶段 1B，用浏览器扩展接管已登录窗口点下载）
否则                     -> manual      （阶段 1C：手动下载 + --local-zip 重跑阶段 P）
```

v1.4.0 起 `api` / `gui` **不再自动选用**：`api` 只在 `--route api` 时考虑，`gui` 只在 `--route gui` 时考虑。默认路径是 `browser`——它不需要 Cookie、不写用户网盘、不接管鼠标键盘，因此把「Cookie 缺失」从阻塞项彻底变成了无关项。`browser` 是否真能落地，要到阶段 1B 用 `user_open_tabs` 才能确认（`preflight` 只能看到浏览器装没装）。

`route=api` 只说明 Cookie 与网络具备，**不代表直链可用**——分享直链接口实测不存在（`sharepage/download` 路由级 404），这条路实际是「先转存到用户网盘 → 再取直链 → 下载后移入回收站」：会写用户账号、消耗每日转存次数、整链未端到端验证。`route_reason` 会原样写明这一点，阶段 1A 必须先取得用户同意。用户不愿写网盘时，正确响应是改走默认的 `browser` 路径或 `manual`，不是硬试转存。

**最低保证**：`local_zip` 只需要 Python + 业务脚本 + 可写目录，这三项在全新电脑上全部由阶段 P 自动就绪。因此即使完全离线、没有 Cookie、没有 GUI 插件，技能依然能完成审查与安装。

## 3. Python 解析优先级

引导脚本按以下顺序找解释器，每个候选都会实际执行一段探针（导入 `ssl` / `zipfile` / `urllib.request` 等并打印版本），验证失败就跳过：

| 序 | 来源 `python.source` | 位置 |
| --- | --- | --- |
| 1 | `explicit_override` | `-PythonOverride` / `--python` / 环境变量 `QUARK_INSTALLER_PYTHON` |
| 2 | `workbuddy_vendor` | `<WORKBUDDY_RESOURCES_PATH>/vendor/python/python.exe`（Windows 实测随安装包分发，`install-manifest.json` 含 `resources/vendor/python/python.exe`）；另从 `WORKBUDDY_APP_PATH`、运行中的 `WorkBuddy.exe` 路径、常见安装根推导 |
| 3 | `workbuddy_managed` | `<WORKBUDDY_CONFIG_DIR>/binaries/python/versions/*/python.exe`（或 `bin/python3`），按版本名倒序 |
| 4 | `system_path` / `py_launcher` | PATH 中的 `python` / `python3`；`py -3 -c "import sys;print(sys.executable)"` 解析出的真实路径 |
| 5 | `common_install` | `%LOCALAPPDATA%\Programs\Python\Python3*`、`C:\Python3*`、`/usr/local/bin/python3`、`/opt/homebrew/bin/python3` 等 |
| 6 | `reused_runtime` | 之前已下载到运行时目录的便携 Python |

**关键事实**：WorkBuddy 自身携带一个完整 CPython（本机为 3.13.14，含 `Lib/`、`DLLs/`、OpenSSL，HTTPS 实测可用）。所以"刚装 WorkBuddy 的电脑"通常第 2 步就命中，完全不需要用户安装 Python，也不需要联网下载。第 2 步能成立，是因为 WorkBuddy 会注入 `WORKBUDDY_RESOURCES_PATH` / `WORKBUDDY_APP_PATH` / `WORKBUDDY_CONFIG_DIR` 等环境变量。

## 4. 兜底：自动准备便携 Python

### 4.1 Windows（已端到端实测）

当所有候选都不可用时，`bootstrap.ps1` 自动：

1. 按 `PROCESSOR_ARCHITECTURE` 选 `amd64` / `arm64`，目标文件 `python-3.12.7-embed-<arch>.zip`（约 11 MB / 10 MB）。
2. 镜像依次尝试（三个均已实测返回 200）：
   - `https://mirrors.huaweicloud.com/python/3.12.7/python-3.12.7-embed-amd64.zip`
   - `https://registry.npmmirror.com/-/binary/python/3.12.7/python-3.12.7-embed-amd64.zip`
   - `https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip`
3. **下载物必须先匹配固定指纹，否则一律丢弃**。指纹硬编码在脚本的 `$PinnedPython` 表里，逐项比对：

   | 文件 | 精确字节数 | SHA256 | python.org 公布的 MD5 |
   | --- | --- | --- | --- |
   | `python-3.12.7-embed-amd64.zip` | 11062583 | `0d57bb6cb078b74d23dbfe91f77d6780d45bed328911609f1f7ee2ba1606bf44` | `4c0a5a44d4ca1d0bc76fe08ea8b76adc` |
   | `python-3.12.7-embed-arm64.zip` | 10318404 | `f4217333d32cecf723d81c0cede4778ccff391f5b71b9404cfbb2d0788ef1c12` | `6fc899d8dbd46dd2b585a038f7cf68a4` |

   - 三者必须全等；任一不符即删除临时文件、记 `fingerprint rejected: <原因>`、换下一个镜像。
   - SHA256 值取自 python.org 官方 FTP 与华为云镜像的**同一份文件**（两边 MD5 均与 python.org 发布页一致，可交叉验证）。
   - 只接受 `https://`；`file://` / `http://` 直接拒绝。
   - 目标版本/架构没有固定指纹时**拒绝下载**（fail closed），而不是"下载什么用什么"。
   - 企业内网镜像可用 `QSI_PYTHON_ZIP_URL` + `QSI_PYTHON_ZIP_SHA256`（64 位十六进制，必填）成对覆盖，脚本仍强制校验 SHA256。
4. 解压前用 .NET `ZipFile.ExtractToDirectory` 落到 `<runtime>/python-3.12.7-embed-<arch>/`（免安装、免管理员、不改 PATH）。
5. **解压后再过两道闸**，任一不过都不执行该解释器：
   - 结构：必须含 `python.exe`、`python3xx.zip`（标准库）、`_ssl.pyd`；
   - 签名：`Get-AuthenticodeSignature` 检查 `python.exe`，判定见下表（`provenance.signature_verdict` 会记下最终结论）：

   | 签名状态 | 处置 | verdict |
   | --- | --- | --- |
   | `Valid` + 签名者含 `Python Software Foundation` | 放行，独立佐证 | `valid-psf` |
   | `Valid` 但签名者**不是** PSF | **拒收**：签名有效不等于官方发布，这是重打包/第三方构建。不得归入下一行（那行的含义是“本机无法验证”）；仅当用户说明是自己重打包并设 `QSI_ALLOW_UNSIGNED=1` 时放行 | `foreign-signer-rejected` / `foreign-signer-allowed` |
   | `HashMismatch`（签名后内容被改） | **拒收**，隔离到 `_rejected/` | `signature-hash-mismatch` |
   | `NotSigned`（官方包一定签名） | **拒收**；仅当用户设 `QSI_ALLOW_UNSIGNED=1`（自建包）才放行 | `unsigned-rejected` / `unsigned-allowed` |
   | `NotTrusted` / `UnknownError` / `Unavailable` | 告警放行：本机证书链或离线问题，不代表字节可疑，以指纹为唯一依据 | `signature-unverifiable` |

   `QSI_ALLOW_UNSIGNED` / `QSI_ALLOW_UV` 是给用户解卡的开关，不是给 Agent 的通路：只能由用户本人提出（见 SKILL.md 红线 10）。无论谁开启，结果都会被记进 `integrity_notes` 与 `warning`，不会静悄悄通过：

   | verdict | 是否进 `integrity_notes` | 说明 |
   | --- | --- | --- |
   | `unsigned-allowed` | 是 | 指纹匹配但无签名 |
   | `foreign-signer-allowed` | 是 | **签名者不是 PSF**（重打包/第三方构建），只凭指纹 + 用户覆盖放行；文案里带上签名者主体名 |
   | `signature-unverifiable` | 是 | 本机证书链无法验证，只凭指纹放行 |
   | `valid-psf` | 否 | 官方签名，无需额外披露 |
   | `unsigned-rejected` / `foreign-signer-rejected` / `signature-hash-mismatch` / `layout-rejected` | 是 | 只会在“旧的 provenance 残留”时出现：说明本机曾拒收过一份运行时，需要重跑 bootstrap 重新确认 |
   | 其它未知取值 | 是 | 原样回显 verdict，提示人工复核——宁可多报一条，也不让未知状态混进干净的 `ready=true` |
6. 通过后才跑探针验证；`python.source=portable_downloaded`、`python.portable=true`，并把来源证据写入 `<runtime>/python-provenance.json`（文件名、字节数、SHA256、MD5、校验结论、签名状态与签名者、校验时间、解释器路径）。

被拒收的解压目录会被移到 `<runtime>/_rejected/`：既不会被候选扫描再次选中，也不做删除，留作排查证据。

实测结论：embeddable 包内含 `python312.zip`（标准库）、`_ssl.pyd`、`libssl-3.dll` / `libcrypto-3.dll`，`urllib` 发起 HTTPS 返回 200，三个业务脚本的 `--help` 均能正常加载。它只缺 pip / site-packages，而本技能全部脚本只用标准库，因此完全够用。

**威胁模型说明**：这条链路防的是「镜像站被劫持 / 被替换 / 传输损坏」——即把别人伪造的解释器装进来跑后续脚本。它不防「python.org 官方值本身被篡改到脚本里」，那需要签名验证脚本自身；因此同时保留 Authenticode 这一条独立于下载通道的检查。

可用 `-ForcePortable` 强制走这条分支（例如主动预置便携运行时）；强制也不会跳过任何校验。

### 4.2 macOS / Linux（best-effort，未在本机实测）

`bootstrap.sh` 的兜底顺序：

1. 优先仍是多路径定位 WorkBuddy 内置 / 托管 Python（这些路径按 Windows 的目录规律推广，**未在真实 macOS / Linux 环境验证**，若未命中会继续往下走）。
2. 若设置了 `QSI_ALLOW_UV=1` 且系统有 `uv`：执行 `UV_PYTHON_INSTALL_DIR=<runtime>/pythons uv python install 3.12`，再用 `uv python find 3.12` 取路径，安装物全部限定在运行时目录内，不污染系统。
   **这条路径不属于 fail-closed 保证**：完整性由 uv 自己内置的哈希完成，本技能无法再校验，因此默认关闭；日志会记 `uv-verified, no pinned fingerprint`，`python.source=uv_provisioned`。
3. 若设置了环境变量 `QSI_PORTABLE_PYTHON_URL`：下载 tarball 到 `_download/`，**必须**同时提供 `QSI_PORTABLE_PYTHON_SHA256`（64 位十六进制），SHA256 不符即丢弃且不解压；通过后解到 `<runtime>/portable-url/`，自动查找其中的 `python3` 可执行文件。只接受 `https://`。适合企业镜像 / 离线预置。
4. 全部失败则 `ready=false`，输出明确的手动命令（`brew install python@3.12`、发行版包管理器、`QUARK_INSTALLER_PYTHON`，或 `QSI_ALLOW_UV=1` 启用 uv 路径）。

> 如实说明：Unix 分支的定位规律与 uv 兜底属于通用实现，未在真实 macOS / Linux 机器上跑通验证。Windows 分支（含自动下载）已端到端实测。

## 5. 目录约定

| 目录 | 默认位置 | 写入？ | 用途 |
| --- | --- | --- | --- |
| `dirs.download` | `<config>/runtimes/quark-installer/downloads` | 写入 | API 直链下载的 zip 落盘位置（不再写 `~/Downloads`） |
| `dirs.skills` | **本技能自身所在的技能根**（如 `~/.workbuddy/skills/`、工作区 `.skills/`）；父目录不像技能根时退回 `~/.workbuddy/skills` | 写入 | 技能安装根目录 |
| `dirs.backup` | `<skills>/.backups/` | 写入 | 同名技能备份 |
| `dirs.runtime` | `~/.workbuddy/runtimes/quark-installer/` | 写入 | 便携 Python、`_download/`、`_rejected/`、`last_preflight.json`、`python-provenance.json`；用 `--runtime-dir` / `QSI_RUNTIME_DIR` 改过位置时，清理脚本也要传同一个值 |
| `scan_dirs` | `~/Downloads` | **只读** | GUI / 手动路径下用户自己下载的 zip 在此被扫描，从不写入 |

`WORKBUDDY_CONFIG_DIR` 存在时以其为 `~/.workbuddy` 的替代。引导脚本通过 `QSI_DOWNLOAD_DIR` / `QSI_SCAN_DIRS` / `QSI_SKILLS_DIR` / `QSI_RUNTIME_DIR` 把目录传给 `preflight.py`；也可用 `--download-dir` / `--skills-dir` / `--runtime-dir` 显式覆盖。

`last_preflight.json` 是 UTF-8 中文完整报告，每次阶段 P 覆盖更新，不含任何 Cookie 内容。`python-provenance.json` 记录便携解释器的来源与校验证据。

清理一律走 `scripts/manage_footprint.py`：默认只报告（逐项字节数），`--purge` 是 dry-run，`--purge --yes` 才执行；只允许动 `runtimes/quark-installer`，拒绝符号链接与 junction、home / 配置根 / 盘符根，正在运行的解释器目录自动跳过。

如果阶段 P 用过 `--runtime-dir` / `QSI_RUNTIME_DIR` 把运行时目录改到别处，清理时**必须传同一个值**（`--runtime-dir <dirs.runtime>`），否则脚本会以“不是本技能自有目录”拒绝。为不让这个覆盖变成“随便删”开关，非默认目录还要满足一条：末层目录名是 `quark-installer`，或其中存在 `last_preflight.json` / `python-provenance.json`。归属校验现在在**扫描之前**就跑（否则 `--runtime-dir ~` 会先把整个主目录量一遍才报错），拒绝时输出一行“已拒绝 : …”并以非 0 退出。`--keep-python` 保留的是**内容里真有解释器可执行文件**的目录（便携 embed 包与 `uv` 的 `pythons/` 都保留，无解释器的残留目录照删），并一并保留 `python-provenance.json`，否则留着解释器却丢了来源记录。**不要**用 `rm -rf` 手工清理。

完整性覆盖（`QSI_ALLOW_UNSIGNED=1` / `QSI_ALLOW_UV=1`）一旦生效，`preflight.py` 会把结论放进 `integrity_notes` 并合并进 `warning`，避免被当成普通的 `ready=true` 汇报出去。覆盖分三种：`unsigned-allowed`（无签名）、`foreign-signer-allowed`（签名者非 PSF，即用户重打包）、`uv`（来源未经本技能校验）——三种都要念，不能只念前一种。

## 6. 凭据与 GUI 能力的边界

**Cookie**：属于账号凭据，技能绝不自动获取、绝不回显、绝不写入技能包、绝不要求用户粘贴进对话。`preflight.py` 只用 `is_file()` + `stat().st_size` 判断存在与否。缺 Cookie 时的"自动准备"是**换路径**（浏览器或本地 zip），不是补凭据。若用户确实要走 API 路径，自行在浏览器登录 `pan.quark.cn` 后运行 `quark-drive` 的 `get_cookie.py`，或设置 `QUARK_COOKIE` / `--cookie-file`。

**GUI 能力**：`computer-use` 是 WorkBuddy 内置插件（Windows），`desktop-control` 需要 `agent-desktop` CLI。自动安装第三方全局 CLI 会改动用户环境，因此默认**不**执行。仅当 `route=gui` 且 `gui_control=false`、并且用户明确同意后，才加 `-PrepareGui` / `--prepare-gui` 重跑阶段 P，由 `preflight.py` 调用 `npm install -g agent-desktop`（超时 300 秒，失败只记 hint，不阻塞）。GUI 自 v1.4.0 起不再是默认路径，正常情况下根本用不到它。

**桌面模式**：v1.4.1 起明确禁止虚拟桌面 / 隔离桌面（`isolated desktop`、`gui_child_session_*`、任何新建或切换 Windows 桌面的模式）。它会替换用户的桌面环境，实测有损坏壁纸的风险，且无法回滚。桌面操控只在主桌面（`window_id: "screen"`）上进行；若某能力仅在虚拟桌面下可用，则视同不可用，直接降级到手动下载。`gui_control=true` 只说明"有这个手段"，不构成使用授权——还需要用户同意接管鼠标键盘。

宿主的「默认独立桌面」开关若开着，`create_task` 即使传 `window_id: "screen"` 也会被路由到 `child_session`（Session 7）。所以桌面操控开工前必须 `gui_list_windows` 查一次：返回里出现 `kind: "child_session"` 就说明这个开关在生效，此时不要创建任务，请用户到「设置 → 电脑控制」关掉它，或直接走手动下载。

## 7. 报告字段速查

| 字段 | 用途 |
| --- | --- |
| `ready` | 必需条件是否齐备 |
| `python.cmd` | **后续所有脚本的解释器**绝对路径；每条命令都要内联它（每次工具调用都是新进程，`$PY` 不会延续） |
| `python.source` / `python.portable` | 解释器来源；`portable` 由 source 推导（`portable_downloaded` / `reused_runtime` / `uv_provisioned` / `portable_url` 均为 `true`），不再固定为 `false` |
| `route` / `route_reason` | 建议下载路径与选择原因（缺 Cookie 与“有 Cookie 但网络不通”会给出不同原因，不再一律说成缺 Cookie） |
| `checks[]` | 逐项体检结果（`level` / `status` / `detail` / `fix`） |
| `auto_fixed[]` / `bootstrap_log[]` | 自动补齐动作与引导过程，需转述给用户 |
| `capabilities` | `api_download` / `gui_download` / `install` / `network_quark` / `cookie` / `gui_control` / `browser`（共 7 项） |
| `dirs` / `report_file` | 目录绝对路径、UTF-8 中文报告路径 |
| `skills_roots` | 探测到的技能根（`path` / `exists` / `active`），第一个即本技能所在根；装到非 `active` 根会导致技能不加载 |
| `scan_dirs` | 只读扫描目录列表（默认 `~/Downloads`） |
| `footprint` | 磁盘足迹：`bytes` / `files` / `components[]` / `read_only_scanned[]` |
| `runtime_provenance` | 便携 Python 的来源与校验证据（`sha256` / `md5` / `verification` / `signature_status` / `signer`）；用系统 Python 时为空 |
| `integrity_notes[]` | 解释器在完整性覆盖下放行的说明（`unsigned-allowed` / `foreign-signer-allowed` / `signature-unverifiable` / `uv`，以及残留的拒收记录与未知 verdict），同时并入 `warning` |
| `blockers[]` / `hints[]` / `warning` | 阻塞项、操作提示、端点可信度提醒 |

`status` 取值：`ok`（原本就绪）/ `fixed`（本次自动补齐）/ `warn`（路径条件缺失，不影响 `ready`）/ `block`（必需条件未修复）。

## 8. 常见问题

| 现象 | 处理 |
| --- | --- |
| `ready=false` | 读 `blockers[]`；多为 Python 完全不可用且离线，或目录不可写 |
| 没有 `python` 命令 | 正常，引导层会定位 WorkBuddy 内置 Python 或自动下载便携版 |
| 便携 Python 下载失败 | 检查网络/代理；或设置 `QUARK_INSTALLER_PYTHON` 指向任一 Python 3.9+；离线机器用 WorkBuddy 自带 `resources/vendor/python/python.exe` |
| 便携 Python 指纹校验被拒 | 正常安全行为，不要绕：`bootstrap_log` 会写明 `fingerprint rejected: sha256 mismatch / size mismatch`。脚本已丢弃并换镜像；全部镜像都不过，说明网络链路在改写内容，改用 WorkBuddy 自带 Python 或 `QUARK_INSTALLER_PYTHON`；私有镜像用 `QSI_PYTHON_ZIP_URL` + `QSI_PYTHON_ZIP_SHA256` 成对提供 |
| 解压后仍被拒（`python3xx.zip missing` / `_ssl.pyd missing` / 签名 `HashMismatch`） | 结构或签名闸门拦下，说明包内容不是官方 embeddable 包；该目录会被移到 `_rejected/`。换镜像重试，或改用本地已有 Python |
| 想清理本技能文件 | `scripts/manage_footprint.py` 看明细 → `--purge`（dry-run）→ `--purge --yes`。只动 `runtimes/quark-installer`；改过 `--runtime-dir` 就加同样的参数 |
| Linux 上只有 uv、没有系统 Python | uv 路径默认关闭（本技能无法复校其完整性）。要启用设 `QSI_ALLOW_UV=1`；更稳的是 `QUARK_INSTALLER_PYTHON` 或 `QSI_PORTABLE_PYTHON_URL` + SHA256 |
| 技能装完列表里不出现 | 装到了宿主不读的根。看 `skills_roots` 的 `active` 项，用 `--skills-dir` / `--target-dir` 指过去重装 |
| `~/Downloads` 里找不到下载的 zip | 那是只读扫描目录，API 路径现在把 zip 存到 `<runtime>/downloads`；GUI / 手动路径才需要去 `~/Downloads` 找 |
| PowerShell 中文乱码 / JSON 解析失败 | 用 `-Readable` 仅在确认 UTF-8 的宿主下输出中文；默认 ASCII JSON 免疫代码页问题；完整中文看 `report_file`；引导脚本已用 `-join` 替代 `Out-String`，不会折行破坏 JSON |
| `preflight.py produced no JSON` | 查看 stderr，确认 `scripts/` 完整、标准库可导入 |
| `route=manual` | 手动下载 zip 后带 `--local-zip <路径>` 重跑阶段 P |
| 需要 GUI 但 `agent-desktop` 缺失 | 用户同意后加 `-PrepareGui`；或直接走本地 zip |
| 想强制使用便携 Python | Windows 加 `-ForcePortable`；Unix 设 `QSI_PORTABLE_PYTHON_URL` |

## 9. 隐私与足迹

- 便携 Python 只从官方 / 可信镜像下载，且必须匹配固定指纹（字节数 + SHA256 + 官方 MD5）并带 PSF 签名才解压执行；落地在用户运行时目录，不写系统目录。
- 全部写入限定在 `~/.workbuddy/runtimes/quark-installer/`（以及技能安装目录）。`~/Downloads` 只读扫描，不再出现"我从来没让它往那写"的文件。
- `last_preflight.json` 不记录 Cookie 内容、提取码、签名直链；只记录存在与否与来源标签。
- `python-provenance.json` 只记录解释器来源与校验证据（公开信息），不含任何凭据。
- 写探针只创建并删除自己刚创建的 `.qsi-write-test-<pid>` 文件，不触碰任何已有文件。
- 网络探测只访问 `pan.quark.cn` 根路径，不携带任何凭据。
- 用户要"删干净"时用 `manage_footprint.py`：报告 → dry-run → `--yes`，且脚本硬编码拒绝越界路径。
