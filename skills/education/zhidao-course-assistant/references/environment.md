# 运行环境自检与自动准备

本文件是「知到 / 智慧树课程助手」的运行条件权威说明。技能在**每次被触发时**都必须先走完这里的流程：先判断本机是否具备条件，具备则直接开始；不具备则按下述分层模型自动补齐，补齐后再开始。

目标是：**一台刚安装 WorkBuddy、从未配置过的电脑，也能在用户配合最少步骤的前提下跑起来。**

## 一、约定符号

| 符号 | 含义 |
| --- | --- |
| `<SKILL_DIR>` | 当前技能 `SKILL.md` 所在目录的**绝对路径**。从 `preflight.py` 自身位置解析，不要假设工作目录就是技能目录。 |
| `<CWD>` | 当前工作区的绝对路径。运行态目录与台账都放在这里。 |
| `<PY>` | 可用的 Python 解释器命令（`python` / `python3` / `py -3`，或 WorkBuddy 内置解释器的绝对路径）。 |

所有命令都用**绝对路径**调用脚本，跨 Windows / macOS / Linux 一致。

## 二、运行条件总表

| 条件 | 级别 | 由谁检测 | 缺失时由谁处理 | 是否阻塞开始 |
| --- | --- | --- | --- | --- |
| Python 3.8+（`ledger.py` / `preflight.py` 依赖） | required | `preflight.py check` | 用户安装或用 WorkBuddy 内置解释器 | 是 |
| `~/.workbuddy` 存在（WorkBuddy 已启动过） | required | `preflight.py check` | 用户安装并启动一次 WorkBuddy | 是 |
| 运行态目录 `<CWD>/.workbuddy/course-assistant/` | required | `preflight.py check` | **`prepare` 自动创建** | 否（可自动修） |
| `env-<技能名>.json`（解析后的绝对路径） | required | `preflight.py check` | **`prepare` 自动生成** | 否（可自动修） |
| Browser Use 插件 / `mcp__browser__*` 工具 | required | **WorkBuddy 工具层探测** | Agent 引导启用插件；仍失败则自动降级方案 B | 是（工具层） |
| 站点连通性 | optional | `preflight.py check` | 报告即可，主流程打开页面时再判 | 否 |
| 系统浏览器（Edge / Chrome / QQ / Chromium） | optional | `preflight.py check` | 用内置浏览器即可忽略；复用外部登录态才需安装 | 否 |
| `computer-use` 技能（Windows） | fallback | `preflight.py check` | **Agent 用 `search_and_install_skills` 自动安装** | 仅方案 B |
| `desktop-control` 技能 | fallback | `preflight.py check` | **Agent 用 `search_and_install_skills` 自动安装** | 仅方案 B |
| Node.js + npm | fallback | `preflight.py check` | 用户安装或用 WorkBuddy 内置 Node | 仅方案 B |
| `agent-desktop` CLI | fallback | `preflight.py check` | 用户同意后 `prepare --allow-install` 自动安装 | 仅方案 B |
| Windows PowerShell 5.1 | fallback | `preflight.py check` | 系统自带，缺失则不用 computer-use | 仅方案 B |
| 用户已登录目标站点 | runtime | 主流程第 1 步 | **用户本人**（禁止代输凭据） | 运行时暂停 |
| 用户指定课程名 | runtime | 主流程第 1.5 步 | 用户 | 运行时询问 |

> 「是否阻塞开始」为「否（可自动修）」的项，不得要求用户手动处理，必须直接执行 `prepare`。

## 三、三层自动准备模型

**第 1 层｜脚本层（无条件自动执行）**
`preflight.py prepare` 负责：创建运行态目录、生成 `env-<技能名>.json`、可选初始化台账、用户同意后安装 `agent-desktop`。这些动作只写本地文件，不提权、不联网（除非 `--allow-install`）、不触碰凭据。

**第 2 层｜Agent 层（WorkBuddy 在本会话内自动执行）**
脚本无法检测 MCP 工具、也无法安装 WorkBuddy 技能与插件，因此以下动作由 WorkBuddy 依据 `check --json` 的 `agent_actions` 自动完成：

1. **探测工具层**：检索 `mcp__browser__browsers_list` 的 schema。能加载 → 方案 A 可用。
2. **启用插件**：`list_installed_plugins` 查 `workbuddy-browser-use` 状态；未启用则引导用户在「设置 > 智能体 > 浏览器操控」开启，必要时用 `suggest_plugin_install` 给出连接卡片。
3. **安装缺失技能**：`ToolSearch` 加载 `search_and_install_skills`，按需安装 `computer-use` / `desktop-control`，安装后重新 `check`。

**第 3 层｜用户层（无法自动完成，一次性列清楚）**
仅限：登录课程站点、授予系统权限（macOS 辅助功能）、安装系统级软件（Python / Node / 浏览器）、确认系统弹窗、同意全局 npm 安装。这些必须**一次性**汇总给用户，附可复制命令与步骤，等用户完成后继续；禁止反复追问、禁止代替用户登录或点击 UAC / 安装器 / 密码框。

## 四、命令速查

```bash
# 0) 推荐：零依赖引导，自动定位 Python（PATH -> WorkBuddy 随包 / 托管运行时）
bash "<SKILL_DIR>/scripts/bootstrap.sh" check --json --workspace "<CWD>"
#    Windows 纯 PowerShell：powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap.ps1" check "<CWD>"

# 1) 体检（机器可读，stdout 只含 JSON）
<PY> "<SKILL_DIR>/scripts/preflight.py" check --json --workspace "<CWD>"
#    需要纯 ASCII JSON 时加 --ascii（PowerShell 5.1 / GBK 控制台）

# 2) 自动准备（复检一次，并输出最终状态）
<PY> "<SKILL_DIR>/scripts/preflight.py" prepare --json --workspace "<CWD>"

# 2') 顺带为指定课程初始化台账（仅当台账不存在时）
<PY> "<SKILL_DIR>/scripts/preflight.py" prepare --json --workspace "<CWD>" --course "课程名"

# 2'') 用户已明确同意安装 CLI 时，自动补装 agent-desktop
<PY> "<SKILL_DIR>/scripts/preflight.py" prepare --json --workspace "<CWD>" --allow-install

# 3) 只取解析后的绝对路径（供桌面分支引用）
<PY> "<SKILL_DIR>/scripts/preflight.py" paths --json --workspace "<CWD>"

# 不想做联网探测时加 --no-network；调整超时用 --timeout 3
```

`check` / `prepare` **恒返回退出码 0**（表示脚本执行成功）；真实状态一律读 JSON，不要把退出码当作「是否就绪」。`paths` 恒输出 JSON。

### `check --json` 关键字段

| 字段 | 含义 |
| --- | --- |
| `ready` | 本机必需条件是否齐全（不含工具层与用户登录态） |
| `next_action` | `prepare` → 先跑 prepare；`wait_user` → 有阻塞项需用户处理；`probe_tools_then_run` → 探测工具层后开始 |
| `auto_fix` | 可由 `prepare` 自动修复的检查项 id 列表 |
| `agent_actions` | 需 WorkBuddy 在本会话内执行的动作（含 `kind` / `target` / `how`） |
| `needs_user` | 需用户配合的项，`blocking` 标明是否阻塞 |
| `blocking` | 阻塞项的 id 列表 |
| `paths` / `env_file` | 解析后的绝对路径，桌面分支一律从这里取 |
| `tool_layer` | 工具层探测说明与降级指引 |

## 五、新机首次运行的完整流程

1. 运行 `check --json`。
2. `next_action == "prepare"` → 执行 `prepare --json`，再读其返回的 `ready` / `next_action`。
3. 按 `agent_actions` 逐条执行（工具层探测、插件启用、技能安装），然后重新 `check --json` 确认。
4. 探测 `mcp__browser__browsers_list`：
   - **可用** → 采用方案 A（受控标签 + DOM 快照 / 截图），进入主流程第 0 步。
   - **不可用** → 先按第六节启用浏览器操控；仍不可用则**自动降级方案 B**，并对方案 B 的条件执行同样一轮 `check → prepare → agent_actions`。
5. 若仍有 `needs_user` 中 `blocking: true` 的项 → 一次性输出清单（步骤 + 命令），等待用户完成。
6. `ready == true` 且工具层可用 → 进入主流程；登录态与课程名在第 1 / 1.5 步按原有规则处理。

> 全程不得跳过 `check`。即便 `env-<技能名>.json` 已存在，也要重新 `check`，因为插件、CLI、技能可能在上次运行后被卸载或升级。

## 六、启用浏览器操控能力（工具层）

`mcp__browser__*` 工具由 **Browser Use 插件**提供。按以下顺序处理：

1. `list_installed_plugins` 查看 `workbuddy-browser-use` 是否已安装并启用。
2. 未启用 → 提示用户打开 **WorkBuddy 设置 > 智能体 > 浏览器操控**，确认 Browser Use 插件已安装且开启。
3. **内置浏览器（IAB）无需任何扩展**：`browsers_list` 中 `type: "desktop"`、名称 `WorkBuddy Browser` 即可用，这是默认首选。
4. 仅当用户需要复用**自己浏览器里的登录态**时，才需要外部浏览器扩展：设置页点对应浏览器的「前往安装」，装好 WorkBuddy Chrome / Edge / QQ 浏览器扩展并启用。
5. 遇到 `stale_tab` / `browser_not_found` / `extension_disconnected` / `host_restarted`：从 `browsers_list` 重新开始，不复用旧标识。
6. 若内置浏览器也不可用且插件短期无法启用 → 降级方案 B，不要改用 HTTP 抓取或命令行浏览器（站点有浏览器检测，且硬性边界禁止绕过）。

## 七、方案 B 的自动准备（桌面备用分支）

降级到方案 B 时，按 `check --json` 的 `paths` 取绝对路径，**禁止硬编码**：

- `paths.computer_use_skill` → `<SKILL_DIR>/scripts/computer-use.ps1`，必须用 Windows PowerShell 5.1（`$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe`），JSON 走 stdin 管道，路径反斜杠双写。
- `paths.desktop_control_skill` → `agent-desktop` CLI；`paths.npm` / `paths.npx` 用于安装与兜底调用。
- 缺失技能 → Agent 用 `search_and_install_skills` 安装。
- 缺失 `agent-desktop` → 向用户给出 `npm install -g agent-desktop` 与 `agent-desktop status`；用户同意后可直接执行 `prepare --allow-install` 自动安装。
- macOS 需按 `agent-desktop permissions --guide` 授予辅助功能权限；Windows 10 1809+ 使用 UI Automation，无需额外授权。
- 桌面分支占用真实鼠标键盘，开始前提示用户不要同时使用鼠标；系统级弹窗、密码框、不可撤销按钮一律交还用户。

## 八、获取 Python 与 Node（新机常见）

WorkBuddy 通常自带便携版运行时，但版本目录名会变，**不要写死版本路径**。`bootstrap.sh` / `bootstrap.ps1` 已把以下优先级脚本化，正常情况无需人工干预：

1. PATH 中的 `python` / `python3` / `py`，且版本 ≥ 3.8（Bash 工具的 PATH 通常已含 WorkBuddy 内置解释器）。
2. `WORKBUDDY_RESOURCES_PATH/vendor/python/python.exe`（随安装包分发的完整 CPython）。
3. `~/.workbuddy/binaries/python/versions/*/python(.exe)`（用户级托管运行时）。
4. 都找不到时，bootstrap 输出纯 ASCII 的 `python_not_found` JSON，由用户安装 Python 3.8+ 或按 `preflight.py` 报告中的 `needs_user` 处理。

手动探测命令：

```bash
python --version || python3 --version || py -3 --version
ls ~/.workbuddy/binaries/python/versions/     # Windows: %USERPROFILE%\.workbuddy\binaries\python\versions\
ls ~/.workbuddy/binaries/node/versions/
node --version && npm --version
```

- Bash 工具的 PATH 一般已包含 WorkBuddy 内置 `python` / `node`；若没有，用上面 `ls` 找到的实际绝对路径作为 `<PY>`。
- 都没有时再让用户安装：Python 3.8+（https://www.python.org/downloads/）、Node.js 18+（https://nodejs.org/）。
- `preflight.py` 与 `ledger.py` 只用标准库，无需 pip 安装任何包。

## 九、路径解析与硬编码禁令

`prepare` 会在 `<CWD>/.workbuddy/course-assistant/` 生成 `env-<技能 name>.json`，其中 `paths` 包含：

`skill_dir` / `skills_root` / `workbuddy_home` / `workspace` / `runtime_dir` / `python_exe` / `python_cmd` / `node` / `npm` / `npx` / `agent_desktop` / `powershell` / `computer_use_skill` / `desktop_control_skill` / `browser_use_plugin_dir` / `browsers` / `ledger` / `ledger_script` / `preflight_script`

- 两个课程助手各自使用**以技能名命名的独立配置文件**，互不覆盖。
- 文档与调用中**禁止出现具体用户名、盘符、版本目录名**（如 `用户主目录`、`versions/3.13.x`）。一律从 `env-<技能名>.json` 或 `paths --json` 读取。
- 该文件只存路径与环境信息，**不存账号、Cookie、Token、DOM 快照、截图或页面内容**。

## 十、安全边界（不可自动化的部分）

以下内容即使技术上能做，也**不得自动执行**：

- 代输账号密码、验证码、人脸 / 摄像头抽检；保存或使用凭据、Cookie、Token。
- 点击 UAC 提示、安装器、杀毒软件弹窗、系统级「是 / 否」对话框。
- 未经用户明确同意执行 `npm install -g` 等系统级安装（`--allow-install` 必须来自用户的显式同意）。
- 绕过浏览器检测、风控、验证码；用 HTTP 抓取替代真实浏览器。
- 计分测验 / 作业 / 考试的代答与提交；伪造观看时长、篡改心跳、调用题库或答案 API。

自动准备只做「本地文件 + 已授权的工具层动作」；遇到上述情形立即停止并交还用户。

## 十一、常见报错与处理

| 现象 | 处理 |
| --- | --- |
| `python: command not found` | 按第八节取 WorkBuddy 内置解释器绝对路径作为 `<PY>`，或安装 Python 3.8+ |
| `check --json` 输出里 `auto_fix` 非空 | 直接执行 `prepare --json`，不要让用户手动建目录 |
| `mcp__browser__browsers_list` 检索不到 | 按第六节启用插件；仍失败则降级方案 B 并准备其条件 |
| `browsers_list` 只有内置浏览器 | 正常，内置浏览器无需扩展；需要外部登录态才装扩展 |
| `extension_disconnected` | 从 `browsers_list` 重新获取浏览器与标签标识，不复用旧 id |
| `npm install -g agent-desktop` 失败 | 检查 `paths.npm` 是否有效、网络与权限；失败只影响方案 B，不阻塞方案 A |
| `agent-desktop status` 提示缺权限（macOS） | 按 `agent-desktop permissions --guide` 授权 |
| 连通性探测报 warn | 不阻塞；检查网络 / 代理 / 校园网认证，主流程打开页面时再判 |
| `env-<技能名>.json` 里路径指向别的技能 | 重新执行 `prepare --json` 覆盖为当前技能的路径 |
| PowerShell 里 `@ref` 报错 | `ref` 加引号：`'@s8f3k2p9:e12'`（desktop-control 语法坑） |
| JSON 参数报 `Invalid JSON primitive` | 走 stdin 管道，Windows 路径反斜杠双写（computer-use 语法坑） |

## 十二、幂等性与性能

`prepare` 可重复执行：目录用 `mkdir(exist_ok=True)`，配置文件原子替换，台账仅在不存在时初始化。脚本默认做一次轻量站点连通性探测（约 1 秒，`--timeout` 可调，`--no-network` 可跳过），不启动浏览器、不登录、不读取任何页面内容。`prepare` 会把完整中文报告落盘为 `<runtime_dir>/last_preflight.json`（UTF-8），供文件读取工具查看；stdout 保持为 JSON，纯 ASCII 需求用 `--ascii`。
