# 阶段 P · 环境自检与自动准备规范

> 本文件是「阶段 P」的完整规范。`SKILL.md` 的工作流程给的是执行动作，本文件给的是
> **为什么这样分层、每层缺了怎么办、以及安全边界**。改版时两者必须同步。

## 0. 阶段 P 要解决的问题

原技能默认假设本机已经具备：Node.js、Windows PowerShell 5.1、`.ps1` 文件带 UTF-8 BOM、
`.sh` 文件是 LF 行尾、`shots/` 与 `audio/` 目录存在、iTEST 已登录且窗口在前面。
其中任何一条不满足，技能要么报「未找到 node」，要么动作层静默返回 `{}`（BOM 丢失），
要么 `bash: bad interpreter`（CRLF），用户完全不知道该修什么。

阶段 P 把这件事变成**一条命令 + 一个结构化结论**：

- **条件齐备 → 直接进工作流程第 0 步，不做任何多余动作。**
- **缺条件 → 能自动补的自动补（BOM / 行尾 / 目录 / 运行时），不能自动补的自动降级到不依赖它的路径。**
- **凭据类条件（登录、验证码、考试码）永不自动准备**，只交给用户本人。

一台刚装好 WorkBuddy 的 Windows 电脑，阶段 P 结束后 `ready=true`、`route=scene`
（只差用户登录这一步，属凭据层），无需任何手工环境配置。

## 1. 条件分层（核心机制）

| 层 | 条件 | 缺失时的行为 | 阻塞 `ready` |
|---|---|---|---|
| **必需** | Windows 10 1809+（桌面动作层是 Win32 API + PowerShell 5.1） | 无法自动准备，报 `block` 并说明平台原因 | 是 |
| **必需** | 可用 Node.js 16+ | 自动：按第 2 节优先级定位；全都没有时自动下载官方便携 Node（免安装、免管理员）到用户运行时目录 | 是 |
| **必需** | Windows PowerShell **5.1**（不是 pwsh 7） | 系统自带；找不到报 `block`（`pwsh 7` 加载 `System.Windows.Forms` 会失败） | 是 |
| **必需** | 关键文件齐全（19 个脚本 / 手册 / 示例） | 报 `block`，提示重新完整解压技能包 | 是 |
| **必需** | `act.ps1` / `uia.ps1` 为 **UTF-8 带 BOM** | **自动补写 BOM**（内容不变）；若已被另存成 GBK/UTF-16 则报 `block` 提示重新解压 | 是（可自动修） |
| **必需** | `run.sh` / `bootstrap.sh` 为 **LF 行尾** | **自动 CRLF → LF**（避免 `bash: bad interpreter`） | 是（可自动修） |
| **必需** | `shots/` `audio/` 运行时目录 `scripts/` 存在且可写 | 自动 `mkdir` + 写探针（只删自己刚建的探针文件） | 是 |
| **必需** | 桌面动作层真的能用（`act.ps1 -Op info` 返回合法 JSON） | BOM 修复后自动复测一次；仍失败报 `block` | 是 |
| **必需（软）** | 运行时盘可用空间 ≥ 200 MB | 告警（不硬阻塞） | 否 |
| **路径** | iTEST 窗口在前台、已登录 | **不能自动准备**（账号凭据）。不阻塞 `ready`，`route=scene`：自动降级为「请用户本人登录 → 重跑阶段 P」 | 否 |
| **路径** | 分辨率 = 2560×1600 标定基准 | 不阻塞。自动降级为「每屏重新截图量坐标」（本来就是推荐做法）；或用 `scale` 粗换算 | 否 |
| **路径** | Python + `soundcard`（听力回环录制，实验性） | 不阻塞。自动降级为「跳过听力录音」，客观题 / 填空题 / 文本题完全不受影响 | 否 |
| **路径** | 备用 GUI 能力（`computer-use` / `desktop-control` / `agent-desktop`） | 不阻塞。本技能自带动作层，这些只是可选项 | 否 |
| **路径** | 浏览器 Edge / Chrome、网络（仅便携 Node 兜底需要） | 检测并报告；缺失不影响已有 Node 的机器 | 否 |
| **凭据** | Unipus 账号 / 学校认证 / 验证码 / 提取码 / 考试码 | **用户本人提供，技能绝不代输、绝不回显、绝不写入任何产物** | 否 |
| **红线** | 监考 / 考试码 / 人脸识别 / 屏幕抓拍 / 切屏抓拍 | `guard` 拦截，停止自动作答，无 `--force` | — |

### 最低保证（为什么全新电脑一定能跑）

阶段 P 自身只需要「Node + 技能自带脚本 + 可写目录」；而 Node 由 WorkBuddy 随包分发
（`resources/vendor/node.zip`、`binaries/node/versions/`、`CODEBUDDY_NODE_BIN`），
PowerShell 5.1 是 Windows 系统组件，BOM / 行尾 / 目录全部由阶段 P 自动补齐。
**因此「必需层」在刚装好 WorkBuddy 的 Windows 电脑上 100% 自动就绪。**
唯一剩下的 `route=scene` 是让用户本人登录 iTEST —— 这是账号凭据，不是环境缺陷。

这与 `quark-share-skill-installer` 的「本地 zip 路径」兜底是同一思路：
把「不能自动准备的条件」从必需层剥离出去，并为它准备一条不依赖它的路径。

## 2. Node.js 解析优先级（bootstrap 层，零依赖）

引导脚本本身**不需要 Node 就能运行**（Windows 用 PowerShell 5.1，Unix 用 bash），
因此可以在「本机完全没有 Node」时先把它准备好，再调 `preflight.js`。

| 序 | 来源 | `node.source` | 说明 |
|---|---|---|---|
| 1 | `-NodeOverride` / `ITEST_NODE_BIN` / `NODE_BIN` | `explicit_override` | 显式指定，最高优先 |
| 2 | `~/.workbuddy/runtimes/itest-assistant/node_path.txt` | `reused_runtime` | **阶段 P 持久化的运行时**，保证后续 `run.sh` 跨工具调用仍能找到 |
| 3 | `~/.workbuddy/binaries/node/versions/*/node.exe` | `workbuddy_managed` | WorkBuddy 托管，最常见命中 |
| 4 | `CODEBUDDY_NODE_BIN` | `workbuddy_cli` | WorkBuddy 为其 CLI 注入 |
| 5 | PATH `node` / `node.exe` | `system_path` | 系统已装 |
| 6 | `Program Files\nodejs` 等常见位置 | `common_install` | — |
| 7 | `resources/vendor/node.zip` 解压 | `workbuddy_vendor_zip` | **WorkBuddy 随包自带，零下载** |
| 8 | 官方便携 Node 22.14.0 自动下载解压 | `portable_downloaded` / `reused_runtime` | 三镜像依次尝试：华为云 → npmmirror → nodejs.org |

> 第 8 步是**兜底中的兜底**：2026-11-22 实测下载 34 MB 的 `node-v22.14.0-win-x64.zip`
> 并解压后，用该便携 Node 对全部业务脚本执行 `--check` 全部通过，确认此路可落地。
> 复用已下载的运行时时来源标记为 `reused_runtime`，**不会**误报成"本次自动下载"。

每个候选都会先跑 `-e "process.stdout.write(process.versions.node)"` 验证版本 ≥16，
不通过就继续下一个，避免选到一个坏的 node。

### 为什么要有 `node_path.txt`

工具调用是彼此独立的进程，环境变量不会跨调用存活。若阶段 P 自动下载了便携 Node
（不在 PATH 里），后续 `bash scripts/run.sh shot` 会重新找不到 node。
因此 bootstrap 把解析结果写到
`~/.workbuddy/runtimes/itest-assistant/node_path.txt`，
`run.sh` 的 `find_node()` 优先读它。**这是"自动准备好条件再使用技能"能贯通全流程的关键。**

## 3. 目录约定（自动准备的红线）

| 目录 | 位置 | 用途 |
|---|---|---|
| `shots/` | 技能目录内 | 截图、`clock.json` / `budget.json` / `pace.json` 等运行产物 |
| `audio/` | 技能目录内 | 听力回环录音（`.wav`），`cleanup` 只处理这里 |
| `scripts/` | 技能目录内 | 需可写：BOM / 行尾自动修复要写回 |
| `runtimes/itest-assistant/` | `~/.workbuddy/runtimes/itest-assistant/` | 便携 Node、`node_path.txt`、`last_preflight.json` / `.txt` |

**自动准备的红线（优先于一切便利）：**

1. 只写以上自有目录，**不改系统 PATH、不装系统级软件、不需要管理员权限、不删除任何已有文件**。
2. 便携 Node 只从官方 / 可信镜像下载并解压到用户运行时目录。
3. 绝不执行 `rm -rf`、绝不清理用户文件、绝不静默 `npm install -g`。
4. BOM 修复只给合法的 UTF-8 文件前置 `EF BB BF`，不改一个字节的正文；
   文件已被另存成 GBK / UTF-16 时**不猜编码**，直接报 `block` 让用户重新解压该文件。
5. 写探针只删自己刚创建的 `.itest-preflight-<pid>.tmp`。

## 4. 阶段 P 决策表（严格按此执行）

| `ready` | `route` | 下一步 |
|---|---|---|
| `false` | `block` | **停止**。把 `blockers[]` 逐条转述用户，按 `checks[].fix` 处理后重跑阶段 P，不要带病开工 |
| `true` | `direct` | 条件全齐备 → **直接使用技能**，进工作流程第 0 步（`activate` → `shot` → 判定计时形态 → `clock` → `budget`） |
| `true` | `degraded` | 必需条件齐备且现场就绪，但可选能力有缺口（分辨率不同 / 缺 Python / 无备用 GUI）→ 按 `degraded[]` 的降级口径**直接使用技能** |
| `true` | `scene` | 环境已 100% 就绪，只差用户登录 → 请用户本人完成「准备现场」三步，**然后重跑阶段 P** 转 `direct`。环境侧无需再做任何配置 |

`route=scene` 不是失败：它表示"技能已经可以用了，只剩一个只有你能做的凭据动作"。
向用户说明时不要说成"环境有问题"。

## 5. 阶段 P 报告字段（stdout 为单个纯 ASCII JSON）

> Windows PowerShell 5.1 会用 OEM/ANSI 代码页解码原生 stdout，中文会乱码。
> 因此 **stdout 一律纯 ASCII JSON**（非 ASCII 全部 `\uXXXX` 转义），
> **完整中文全文报告以 UTF-8 落盘**，用文件读取工具打开 `report_text_file`。

| 字段 | 含义 |
|---|---|
| `ready` | 必需条件是否全部满足；`true` 才能继续 |
| `route` | `direct` / `degraded` / `scene` / `block` |
| `route_reason` | 为什么走这条路径 |
| `run.node_cmd` / `py_cmd` / `ps_cmd` | **本次全流程必须使用的解释器 / PowerShell 绝对路径** |
| `node.source` | 解释器来源（见第 2 节）；`portable` 是否为便携版 |
| `checks[]` | 每项 `id`、`level`（required/route）、`status`（ok/fixed/warn/block）、`detail`、`fix` |
| `auto_fixed[]` | 本次自动补齐的动作（BOM、行尾、目录），逐条转述给用户 |
| `bootstrap_log[]` | 引导层定位 / 下载 Node 的过程记录 |
| `capabilities` | `action_layer` / `scene_ready` / `resolution_match` / `listening` / `browser` / `answer_check` 等 |
| `degraded[]` | 本次采用的降级口径 |
| `blockers[]` | 未修复的必需条件；非空时 `ready=false` |
| `hints[]` | 给 Agent 与用户的操作提示 |
| `report_file` | UTF-8 可读 JSON 全文 |
| `report_text_file` | UTF-8 中文逐项报告（**优先读这个给人看**） |

向用户汇报阶段 P 结果时至少说明：用了哪个 Node、来源是什么、是否自动下载了便携运行时、
自动补齐了哪些条件（BOM / 行尾 / 目录）、本次走哪条 `route` 及原因、有哪些降级口径。

## 6. 全平台运行口径

| 平台 | 引导脚本 | 结果 |
|---|---|---|
| Windows（推荐） | `PowerShell 工具` 调 `scripts/bootstrap.ps1` | `platform` 检查通过；动作层可用；`ready=true` |
| Windows（Git Bash） | `Bash 工具` 调 `bash scripts/bootstrap.sh` | 同上；两脚本语义一致 |
| macOS / Linux | `bash scripts/bootstrap.sh` | 仍能完成引导并给出结构化报告，但 `platform` 报 `block`：**桌面动作层是 Win32 API，本技能仅支持 Windows**，不要强行继续 |

## 7. 常见故障速查

| 现象 | 处理 |
|---|---|
| `ready=false` | 读 `blockers[]` 与对应 `checks[].fix`；多为非 Windows、Node 完全不可用且离线、或目录不可写 |
| `未找到 Node.js` / `node: command not found` | 不必手工装：阶段 P 会自动定位 WorkBuddy 自带 Node 或下载便携版；也可设 `ITEST_NODE_BIN` |
| 便携 Node 下载失败 | 引导层依次尝试华为云 → npmmirror → nodejs.org；全失败时检查网络/代理，或设 `ITEST_NODE_BIN`；离线机器仍可用 `resources/vendor/node.zip` |
| `动作层返回失败 {}` / `info` 显示逻辑像素偏小 | 九成是 `.ps1` 丢了 UTF-8 BOM；**去掉 `--no-fix` 重跑阶段 P 会自动补写**，无需手工转码 |
| 文件已被存成 GBK / UTF-16 | doctor 不猜编码：从技能包 zip 重新解压该文件覆盖，不要手工另存 |
| `bash: bad interpreter` | `.sh` 变成 CRLF 了；重跑阶段 P 自动转 LF。Windows 上优先用 `bootstrap.ps1` 避开此坑 |
| 阶段 P 之后 `run.sh` 又报未找到 node | 检查 `~/.workbuddy/runtimes/itest-assistant/node_path.txt` 是否存在且可执行；重跑阶段 P 会重写 |
| PowerShell 里报告中文乱码 | stdout 已是纯 ASCII JSON（Unicode 转义），不影响解析；完整中文报告用文件读取工具打开 `report_text_file` |
| `前台窗口不是 iTEST` | 不是环境错误：`route=scene`。请用户登录 iTEST、窗口最大化、缩放 100%，再重跑阶段 P |
| 分辨率不是 2560×1600 | 不阻塞。每屏重新截图量坐标（推荐），或 `bash scripts/run.sh scale --auto --coords "x,y"` 粗换算 |
| 缺 Python / soundcard | 只影响听力回环录制；客观题、填空题、文本题作答全部不受影响 |
| `preflight.js produced no JSON` | 查看 stderr；确认 `scripts/` 文件齐全、Node 能正常加载标准库 |
| `guard` 拦截 | 出现监考 / 考试码 / 人脸识别 / 抓拍等正式考试特征，按安全边界停止自动作答，无绕过开关 |

## 8. 与三版本构建的关系

阶段 P 是**本地满血版的功能增强**，新增文件：

- `scripts/bootstrap.ps1`、`scripts/bootstrap.sh`（引导层）
- `scripts/preflight.js`（自检核心）
- `scripts/scale.js`（跨分辨率辅助）
- `references/environment_setup.md`（本文件）
- `scripts/run.sh` 增加 `doctor` / `scale` 分派与 `node_path.txt` 优先解析

原有 `itest.js` 编排层、`act.ps1` / `uia.ps1` 动作层、三份判题手册、`lint.js` 等
**均未改动**，保持向后兼容。若要从满血版重建发布版 / 萌新版，需把上述新增文件纳入
复制清单并同步 `SKILL.md` 模板；`lint.js` 已把这些新路径纳入完整性检查。
