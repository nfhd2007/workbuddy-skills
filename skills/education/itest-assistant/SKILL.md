---
name: itest-assistant
version: "2.4.0-local"
display_name: iTEST爱考试助手
display_name_en: iTEST Exam Assistant
description: "iTEST（爱考试 / 外研社 Unipus）全功能答题助手：运行前强制先做阶段 P 环境自检与自动准备，条件齐备就直接使用技能，缺条件就自动补齐（定位或下载 Node、修复 .ps1 的 UTF-8 BOM、修正 .sh 行尾、创建目录）或自动降级到不依赖该条件的路径，一台刚装好 WorkBuddy 的 Windows 电脑也无需手工配置。随后通过桌面自动化接管用户已登录的页面，截图加无障碍树逐屏读题，助手自行判断答案并点选客观题、填写文本题；内置选词填空（15选10）、段落信息匹配、短文填词三类填空题的判题手册与答案守恒校验；听力可回环录制转写辅助判断，文本题经量化自检后填写，逐屏截图复核，交卷默认 dry-run。运行时读图判定倒计时 / 正向计时并自动分档（full / timed / rescue），限时周测归零自动交卷时按「先保底填满、存疑题后补」执行。仅用于本人已获授权的自主训练、课程周测与开放性测验。双答案交叉法与文本量化关卡等工程思路借鉴并谨此致谢 chaoxing-homework（学习通作业助手）作者最l之人与贡献者。当用户说「用 itest 助手做这套题」「帮我做 iTEST 周测」「第一次用 iTEST 助手」「itest 环境体检」「换电脑了怎么跑」「这套周测有倒计时」时使用。"
description_zh: "iTEST（爱考试 / 外研社 Unipus）全功能答题助手：运行前强制先做阶段 P 环境自检与自动准备，条件齐备就直接使用技能，缺条件就自动补齐（定位或下载 Node、修复 .ps1 的 UTF-8 BOM、修正 .sh 行尾、创建目录）或自动降级到不依赖该条件的路径，一台刚装好 WorkBuddy 的 Windows 电脑也无需手工配置。随后通过桌面自动化接管用户已登录的页面，截图加无障碍树逐屏读题，助手自行判断答案并点选客观题、填写文本题；内置选词填空（15选10）、段落信息匹配、短文填词三类填空题的判题手册与答案守恒校验；听力可回环录制转写辅助判断，文本题经量化自检后填写，逐屏截图复核，交卷默认 dry-run。运行时读图判定倒计时 / 正向计时并自动分档（full / timed / rescue），限时周测归零自动交卷时按「先保底填满、存疑题后补」执行。仅用于本人已获授权的自主训练、课程周测与开放性测验。双答案交叉法与文本量化关卡等工程思路借鉴并谨此致谢 chaoxing-homework（学习通作业助手）作者最l之人与贡献者。当用户说「用 itest 助手做这套题」「帮我做 iTEST 周测」「第一次用 iTEST 助手」「itest 环境体检」「换电脑了怎么跑」「这套周测有倒计时」时使用。"
description_en: "Full-featured iTEST (Unipus) exam assistant. A mandatory Phase P preflight checks the machine first: proceed directly when conditions are met, otherwise auto-provision them (locate or download Node, fix the .ps1 UTF-8 BOM, normalize .sh endings, create directories) or degrade to a path that does not need the missing condition, so a fresh WorkBuddy on Windows needs no manual setup. It then drives the logged-in page via desktop automation, reads each screen with screenshots and the accessibility tree, determines answers itself and fills them in. Includes playbooks for banked cloze, paragraph matching and word-fill, an answer conservation checker, loopback audio, a text self-check, per-screen verification and dry-run submission. Detects countdown / count-up timers and auto-selects full / timed / rescue pacing; at zero it fills every unanswered item first. For authorized self-study and class quizzes. Use when the user says 'use the itest assistant to finish this quiz' or 'run the itest environment check'."
category: education
agent_created: true
author: WorkBuddy
triggers:
  - itest 助手
  - iTEST爱考试助手
  - 用 itest 助手做这套题
  - 帮我做 iTEST 周测
  - 把这份 iTEST 训练卷做完
  - iTEST 周测
  - 大英周测
  - 这套周测有倒计时
  - 限时周测
  - 第一次用 iTEST 助手
  - itest 环境体检
  - itest 换电脑
  - 换电脑了怎么跑
  - 选词填空
  - 十五选十
  - 段落信息匹配
  - 这道填空题答案是什么
  - do my iTEST quiz
  - banked cloze
---

# iTEST爱考试助手

## 总览

在你已经登录、已经打开的 iTEST 页面（Edge / Chrome 均可）上执行**桌面自动化操作**，把「确认现场 → 判定计时形态 → 逐屏读题 → 判题 → 客观题点选 → 主观题填写 → 逐屏复核 → 翻页 → 交卷 → 复盘」串成一条可复现的流水线。

脚本只做确定性动作（截图、点坐标、粘贴、按键、翻页）。**读题和判题由模型完成**：看截图 + 无障碍树，产出这一屏的 `screen.json`（题目与坐标）和 `answers.json`（题号与答案）。

**为什么不用 CDP**：iTEST 作答页有切屏监测，重启浏览器会丢作答状态、重新登录也会消耗时间；桌面操控可以直接接管你当前那个已登录的窗口。代价是读题靠视觉，**每屏都要起 PowerShell + 截图 + 模型读图，单屏开销不小**——所以限时卷必须做时间预算与分档，见 `references/timed-mode.md`。

## 安全边界（先读，不可逾越）

- **只做本人已获授权的自主训练、课程周测、开放性测验**。出现「监考 / 考试码 / 人脸识别 / 屏幕抓拍 / 切屏抓拍」等正式考试特征时，`guard` 会拦截，停止自动作答。
- **不规避任何防作弊机制**：不伪造切屏状态、不破解人脸识别、不使用或猜测考试码、不改答题终端限制。`submit` 里的红线检查没有 `--force` 开关。
- **限时卷不碰任何计时机制**：不冻结 / 篡改 / 伪造页面倒计时，不绕过自动交卷，不改系统时间。分档只调整助手自己的操作节奏；来不及就如实告知用户并安全收尾。
- **归零自动交卷不可逆**：倒计时卷必须按 `budget` 给出的 `[MODE=...]` 执行；出现 `[ACTION_REQUIRED]` 立刻告知用户剩余时间、未答题数与自动交卷风险。是否主动交卷由用户明确同意，用户不答就让平台按规则处理。
- **不代输账号密码、不处理验证码**。Unipus 通行证与学校身份认证由用户本人完成。
- **交卷不可撤销**：`submit` 默认 dry-run，必须用户明确同意后才加 `--yes`。
- **听力不代「听懂」、口语不代录**：模型没有听觉；训练卷可用「回环录制 → 转写 → 读逐字稿」辅助判断（见下文实验性链路），但答案是读文字推的，不是真听到。口语题必须用户本人录制。正式考试按红线直接拒绝。
- **录音删除不可恢复**：`submit --yes` 交卷成功后会自动执行 `postsubmit` 报告录音大小，**但绝不会自己删**。助手必须把大小告知用户并明确询问用户，得到明确同意后才能执行 `cleanup --apply`；用户拒绝或没回答就什么都不删。
- **环境自动准备的红线**：阶段 P 只写本技能自有目录（`shots/`、`audio/`、`scripts/`、`~/.workbuddy/runtimes/itest-assistant/`）；不改系统 PATH、不装系统级软件、不需要管理员权限、不删除任何已有文件。便携 Node 只从官方 / 可信镜像下载并解压到用户运行时目录。不要为「救场」执行 `rm -rf`、清理用户文件或静默全局 `npm install`。BOM 修复只给合法 UTF-8 文件前置 `EF BB BF`，不改正文一个字节。

## 运行条件总览与自动准备策略

**每次使用本技能，第一件事永远是运行阶段 P 引导脚本**：先判断本机有没有足够的条件，
**有条件就直接使用技能，没有条件就自动准备好条件（或自动降级到不依赖该条件的路径）再使用技能**。
阶段 P 把条件分成三层，逐项判定。完整规范见 `references/environment_setup.md`。

| 层 | 条件 | 缺失时的行为 | 阻塞 `ready` |
|---|---|---|---|
| **必需** | Windows 10 1809+（动作层是 Win32 API + PowerShell 5.1） | 无法自动准备，报 block 并说明平台原因 | 是 |
| **必需** | Node.js 16+ | 自动：优先 WorkBuddy 随包分发的 `resources/vendor/node.zip` / 托管 `binaries/node/versions/` / `CODEBUDDY_NODE_BIN`，其次 PATH；全都没有时自动下载官方便携 Node（免安装、免管理员） | 是 |
| **必需** | Windows PowerShell **5.1**（非 pwsh 7） | 系统自带；找不到报 block（pwsh 7 加载 `System.Windows.Forms` 会失败） | 是 |
| **必需** | 关键脚本 / 手册 / 示例齐全（19 个） | 报 block，提示重新完整解压技能包 | 是 |
| **必需** | `act.ps1` / `uia.ps1` 为 **UTF-8 带 BOM** | **自动补写 BOM**（内容不变）；已被另存成 GBK / UTF-16 则报 block 提示重新解压。这是全新电脑第一大坑 | 是（可自动修） |
| **必需** | `run.sh` / `bootstrap.sh` 为 **LF 行尾** | **自动 CRLF → LF**（避免 `bash: bad interpreter`） | 是（可自动修） |
| **必需** | `shots/` `audio/` 运行时目录 `scripts/` 可写 | 自动 `mkdir` + 写探针 | 是 |
| **必需** | 桌面动作层可用（`act.ps1 -Op info` 返回合法 JSON） | BOM 修复后自动复测；仍失败报 block | 是 |
| **必需（软）** | 运行时盘可用空间 ≥ 200 MB | 告警，不硬阻塞 | 否 |
| **路径** | iTEST 窗口在前台、已登录 | **账号凭据不能自动准备** → 不阻塞 `ready`，`route=scene`：请用户本人登录、窗口最大化、缩放 100%，然后重跑阶段 P | 否 |
| **路径** | 分辨率 = 2560×1600 基准 | 自动降级：每屏重新截图量坐标（推荐，本就不需要换算），或 `scale` 粗换算 | 否 |
| **路径** | Python + `soundcard`（听力回环，实验性） | 自动降级：跳过听力录音，客观题 / 填空题 / 文本题完全不受影响 | 否 |
| **路径** | 备用 GUI 能力（`computer-use` / `desktop-control`） | 可选；本技能自带动作层，缺失不影响 | 否 |
| **凭据** | Unipus 账号 / 学校认证 / 验证码 / 考试码 | 用户本人提供，技能绝不代输、不回显、不写入任何产物 | 否 |
| **红线** | 监考 / 考试码 / 人脸识别 / 抓拍 | `guard` 拦截，停止自动作答，无 `--force` | — |

**关键结论（最低保证）**：阶段 P 自身只需要「Node + 技能自带脚本 + 可写目录」，而 Node 由
WorkBuddy 随包分发、PowerShell 5.1 是 Windows 系统组件，BOM / 行尾 / 目录全部自动补齐。
**因此「必需层」在刚装好 WorkBuddy 的 Windows 电脑上 100% 自动就绪**，全新电脑永远能进入
「可以使用技能」的状态。唯一剩下的 `route=scene` 是让用户本人登录 iTEST —— 这是账号凭据，
不是环境缺陷，向用户说明时不要说成「环境有问题」。

## 阶段 P · 环境自检与自动准备（强制第一步，不可跳过）

**不要在阶段 P 之前执行任何业务脚本，不要假设 `node` 命令存在，不要硬编码解释器路径。**
`<SKILL_DIR>` 一律解析为本 `SKILL.md` 所在目录的绝对路径，不要假设当前工作目录就是技能目录。

**Windows（推荐，用 PowerShell 工具）**：

```powershell
$raw = & "<SKILL_DIR>\scripts\bootstrap.ps1" 2>$null
$r = (($raw -join "`n") | ConvertFrom-Json)
$NODE = $r.run.node_cmd
# 完整中文逐项报告（UTF-8）在此，务必用文件读取工具打开后逐项转述给用户：
Get-Content -LiteralPath $r.report_text_file -Encoding UTF8
```

**Windows Git Bash / macOS / Linux（用 Bash 工具）**：

```bash
R=$(bash "<SKILL_DIR>/scripts/bootstrap.sh")
# 解析 ready / route / run.node_cmd；完整中文报告：
cat "$HOME/.workbuddy/runtimes/itest-assistant/last_preflight.txt"
```

引导脚本本身**零依赖**（Windows 用 PowerShell 5.1、Unix 用 bash 就能跑），因此即使本机完全没有
Node，也能先把 Node 准备好再调 `preflight.js`。常用可选参数（两个脚本语义一致）：

| 参数 | 作用 |
| --- | --- |
| `--no-fix` / `-NoFix` | 只体检不修复（诊断用，BOM / 行尾 / 目录都不动） |
| `--skip-network` / `-SkipNetwork` | 跳过出网探测（离线环境加速） |
| `--readable` / `-Readable` | stdout 输出可读 UTF-8 JSON（默认纯 ASCII JSON，见下） |
| `--verbose` / `-VerboseLog` | 把引导过程打到 stderr |
| `--node <path>` / `-NodeOverride <path>` | 显式指定 Node 可执行文件 |
| `--runtime-dir` / `-RuntimeDir` | 覆盖便携运行时目录 |
| `-ForcePortable` / `--force-portable` | 跳过解释器发现，强制走便携分支（验证兜底用） |

**报告口径**：stdout 是**单个纯 ASCII JSON**（非 ASCII 全部 `\uXXXX` 转义）——Windows
PowerShell 5.1 会用 OEM/ANSI 代码页解码原生 stdout，中文会乱码，所以完整中文全文报告以 UTF-8
落盘，用文件读取工具打开 `report_text_file`。核心字段：

| 字段 | 含义 |
| --- | --- |
| `ready` | 必需条件是否全部满足；`true` 才能继续 |
| `route` | `direct` / `degraded` / `scene` / `block` |
| `route_reason` | 为什么走这条路径 |
| `run.node_cmd` / `py_cmd` / `ps_cmd` | 本次全流程必须使用的解释器 / PowerShell 绝对路径 |
| `node.source` | `workbuddy_managed` / `workbuddy_vendor_zip` / `system_path` / `portable_downloaded` / `reused_runtime` 等 |
| `checks[]` | 每项 `id`、`level`（required/route）、`status`（ok/fixed/warn/block）、`detail`、`fix` |
| `auto_fixed[]` | 本次自动补齐的动作（BOM / 行尾 / 目录 / 下载运行时），逐条转述用户 |
| `bootstrap_log[]` | 引导层定位 / 下载 Node 的过程记录 |
| `capabilities` | `action_layer` / `scene_ready` / `resolution_match` / `listening` / `browser` 等 |
| `degraded[]` / `blockers[]` / `hints[]` | 降级口径 / 未修复必需项 / 操作提示 |
| `report_file` / `report_text_file` | UTF-8 可读 JSON 全文 / **中文逐项报告（优先读这个给人看）** |

**阶段 P 决策表（严格按此执行）**：

| `ready` | `route` | 下一步 |
| --- | --- | --- |
| `false` | `block` | **停止**。把 `blockers[]` 逐条转述用户，按 `checks[].fix` 处理后重跑阶段 P，不要带病开工 |
| `true` | `direct` | 条件全齐备 → **直接使用技能**，进工作流程第 0 步 |
| `true` | `degraded` | 必需条件齐备且现场就绪，但可选能力有缺口 → 按 `degraded[]` 的降级口径**直接使用技能** |
| `true` | `scene` | 环境已 100% 就绪，只差用户登录 → 讲清「准备现场」三步请用户本人完成，**然后重跑阶段 P** 转 `direct` |

向用户汇报阶段 P 结果时至少说明：用了哪个 Node、来源是什么、是否自动下载了便携运行时、
自动补齐了哪些条件、本次走哪条 `route` 及原因、有哪些降级口径。
用户第一次用时，先讲清「准备现场」三步（登录 iTEST、窗口最大化、浏览器缩放 100%），等他确认再开始。
**阶段 P 之后所有命令一律用 `scripts/run.sh`（它会自动复用 `node_path.txt` 里持久化的运行时），
不要出现裸 `node` / `node.exe` 路径。** 复检环境用 `bash scripts/run.sh doctor --json`。

## 前置条件

1. **阶段 P 报告 `ready=true`**（第一次使用 / 换电脑后必须重跑，见上节）。
2. iTEST 已在浏览器中登录，并停在目标页面（考试列表 / 待完成 / 答题页 / 训练页）。账号密码与验证码由用户本人完成，技能绝不代输。
3. **iTEST 窗口可见、未被完全遮挡**。WorkBuddy 可以缩到侧边，但不要把 iTEST 最小化——截图截的是屏幕，不是窗口。
4. `scripts/run.sh info` 的 `foreground.title` 含 `iTEST`，说明窗口在前台；否则可用 `activate` / `topmost` 把它带到前台。
5. 浏览器缩放保持 100%（页面排版稳定，识别更准）。系统 DPI 缩放不影响坐标，见下文「坐标系」。
6. 分辨率与 2560×1600 基准不同时，读 `references/environment_setup.md`：**每屏截图量到的坐标直接可用，不换算**；只有复用文档预设坐标才需要 `scale`。
7. **第一张截图必须判定计时形态**（倒计时 / 正向计时 / 读不清）。上一卷无限时不代表这一卷无限时；读不清一律按限时保守处理。

## 工作流程

### 0. 确认现场 + 判定计时形态

> 进入本节前**必须已完成阶段 P** 且 `ready=true`。阶段 P 已把 Node / BOM / 行尾 / 目录全部备齐，
> 本节不再做任何环境配置，直接开始业务动作。

```bash
scripts/run.sh doctor --json            # 可选：快速复检（首次已跑过 bootstrap 时可略）
scripts/run.sh activate                 # 把 iTEST 带到前台
scripts/run.sh shot --out shots/p1.png  # 截当前屏
```

看截图确认四件事：**在哪个页面**（列表 / 答题 / 结果）、**计时条是倒计时还是正向计时**、**当前题号范围**、**有没有「剩余时间 / 时间到自动交卷」一类提示**。如果是列表页，先让用户点进目标测验，或由你按截图坐标点「进入考试 / 开始考试」。

计时形态判定口径（**每卷重判，不得沿用上一卷**）：

| 形态 | 特征 | 后果 |
| --- | --- | --- |
| `countdown` 倒计时 | `剩余时间 44:58` 一类递减数字，一般整卷一个总时钟 | **归零自动交卷**，未答题空白；必须做时间预算 |
| `countup` 正向计时 | 从 `00:00:00` 往上走（无限时训练卷） | 无自动交卷风险，走 `full` |
| `unknown` | 读不清 / 被遮挡 / 没计时条 | 按限时保守处理，重新截图确认 |

> 进入考试后倒计时就开始跑。**不要**在用户没确认的情况下点「进入考试 / 开始考试 / 交卷」。

### 0.5 时间预算与自动分档（每卷必做）

把第一屏的判定结果写进 `screen.json` 的 `timer` 字段（结构见第 1 步），然后落盘快照、算预算：

```bash
scripts/run.sh clock --screen shots/screen1.json   # 写 shots/clock.json（计时形态 / 剩余秒数 / 截止时间 / 题量）
scripts/run.sh budget --answered 0                 # 写 shots/budget.json 并打印 [MODE=...]
```

之后**每一屏循环开头都跑一次** `scripts/run.sh budget --answered <已答题数>`，照输出的 `[MODE=...]` 执行，**不要自己拍脑袋选**。时长不固定，阈值全部由「剩余时间」与「本题实测每题均耗」动态算出；模式只往更紧的方向切（`full → timed → rescue` 不回退）。换卷用 `clock --screen ... --reset` 重置节奏与旧模式。

| 模式 | 触发 | 怎么做 |
| --- | --- | --- |
| `full` | 正向计时；或剩余 ≥ 预计还需 × 1.5 | 完整流水线：双答案交叉、答案守恒、文本题量化多轮、逐屏复核 |
| `timed` | 剩余 < 预计还需 × 1.5；或计时形态未判明 | 砍掉可砍的质量关卡，优先保覆盖率；只保留抽样复核 |
| `rescue` | 剩余 ≤ 安全缓冲（`max(90s, 预计还需 × 0.15)`）；或已归零 | **先保底填满**：所有未答题给最优解填入，存疑题标注后补，不留空 |

降级顺序（时间不够时按序砍，**最后才砍题**）：① 双答案交叉 → ② 文本题多轮打磨 → ③ 填空题两轮反向交叉（整篇收齐不能砍）→ ④ 逐屏截图复核（改每 3–4 屏抽样）→ ⑤ 存疑题反复推敲。答题优先级：客观题 > 填空题 > 短文本 > 长作文。

用户已确认接受「先保底填满、存疑题后补」。**限时卷禁止启动听力回环录制 + 云端转写**（整卷实测 41 分钟，且单次播放不可回放），听力题按用户给的答案填或跳过并标明。完整口径、读图判据、交卷策略见 `references/timed-mode.md`。

`guard` 也会读 `shots/clock.json`，在红线检查之外附带打印同一模式提示，防止漏跑 `budget`。**限时周测不带监考 / 考试码 / 抓拍，属作业性质，`guard` 不拦截**，但必须按分档执行。

### 1. 逐屏读题（模型读图 + 无障碍树辅助）

每一屏先跑 `scripts/run.sh budget --answered <已答题数>` 看时间与模式，再：

```bash
scripts/run.sh uia --out shots/uia1.json
```

读 `shots/p1.png`（版式）和 `shots/uia1.json`（文本 + 坐标），产出这一屏的 `screen.json`：

```json
{
  "page": 1,
  "kind": "single | multi | judge | banked | matching | blank | reading | translate | writing | listening",
  "text": "这一屏所有可见文字（用于红线检查，尽量全）",
  "timer": {
    "mode": "countdown",
    "display": "剩余时间 44:58",
    "remainingSeconds": 2698,
    "autoSubmit": true,
    "totalQuestions": 40,
    "answeredQuestions": 0
  },
  "questions": [
    {
      "no": 26,
      "type": "single",
      "stem": "What makes women blind to ...?",
      "options": [
        { "letter": "A", "text": "Their wish to improve ...", "x": 640, "y": 412 },
        { "letter": "B", "text": "Their attempt to show off ...", "x": 640, "y": 448 }
      ]
    }
  ],
  "inputs": [
    { "no": 41, "x": 900, "y": 700 }
  ],
  "nav": {
    "next": { "x": 1600, "y": 980 },
    "card": { "x": 1480, "y": 40 },
    "submit": { "x": 1640, "y": 40 },
    "confirm": { "x": 1100, "y": 700 }
  }
}
```

- 坐标必须是**当前这张截图里的坐标**（截图左上角为 0,0），不要用上一次截图的坐标。
- 选项坐标取**整行可点区域的中心**，不是字母圆点本身——iTEST 的选项整行都能点。
- 输入框坐标取文本框内部偏上的位置，避开右下角的字数统计。
- `text` 字段要尽量把整屏文字写全，`guard` 靠它判断红线。
- `timer` 字段只在**首屏**必须给全；后续屏可省略（`budget` 用截止时间推算剩余）。显示是截止时间时换算成秒写 `remainingSeconds`；`autoSubmit` 按 `true` 处理（用户已确认归零自动交卷）。若发现每个 Section / 每题有独立倒计时，按**最短的那个**当预算并在回报里说明。
- 填空题（一屏一空 / 一屏一句 + `请输入答案…`）**必须先把整篇材料收齐**：短文全文、词库 15 个词、段落 A–O。逐屏截图拼成完整文本后再判题，不要一屏一猜。
- 填空题先建编号映射表：`屏幕题号 | 文中空号 | 答案 | 依据`。`inputs[].no` 用屏幕题号，不用文中空号，也不拿 `1/10` 进度当题号。

### 2. 判题

按 `references/answer-quality.md` 的双答案交叉法作答，写入 `answers.json`：

```json
{
  "26": { "type": "single", "answer": ["A"] },
  "27": { "type": "multi", "answer": ["A", "C"] },
  "1":  { "type": "banked", "answer": ["C"] },
  "17": { "type": "matching", "answer": ["L"] },
  "3":  { "type": "blank", "answer": ["round"] },
  "41": { "type": "text", "text": "改写后的译文或作文" }
}
```

- 字母用页面显示的 A/B/C/D，不是任何内部编号。
- 同一屏的题号必须与 `screen.json` 的 `no` 一致。
- **遇到 `banked` / `matching` / `blank` 时，先读 `references/question-types.md` 再判题**：整篇一次解完、定词性优先于定词义、段落匹配靠锚点定位而非原词命中、短文填词核对词形。三种题分别填「词库字母」「段落字母」「一个单词」。
- 这三种 `type` 的答案写在 `answer` 数组里，`fill` 会按 `type` 自动粘贴到 `inputs` 对应输入框，**不会**去点不存在的选项；`screen.json` 仍要给 `inputs[].no / x / y`。
- 判完把答案另存一份 `check.json`，跑 `node scripts/answercheck.js check.json --partial` 查数量、越界、重复、缺号；退出码 0 才填答。脚本只查形式，不查对错。**答案守恒是机械校验，几乎不耗时，任何模式都保留。**
- **按模式裁剪**：`timed` 砍掉独立重做的第二轮，只做一轮 + 守恒；填空题只做一轮（整篇收齐仍保留）。`rescue` 下所有未答题**先给最优解填满**，把题号 + 选择 + 一句话理由记进存疑清单，不要因为存疑就留空。

### 3. 填客观题

```bash
scripts/run.sh guard --screen shots/screen1.json                    # 先过红线 + 看模式提示
scripts/run.sh fill --screen shots/screen1.json --answers answers.json --dry   # 看计划
scripts/run.sh fill --screen shots/screen1.json --answers answers.json         # 执行
```

`fill` 按坐标批量点击，一屏只启一次 PowerShell，比逐题调用快得多。`timed` / `rescue` 下可跳过 `--dry` 预览，直接执行以省一轮开销。

### 4. 填主观题（翻译 / 写作 / 简答）

先写一版 → 用 `textcheck.js` 量化 → 按报告改（最多 3 轮）→ 再 `fill`（长文本自动走剪贴板粘贴，不逐字敲）：

```bash
node scripts/textcheck.js answers/q41.txt        # 退出码 0 才算过
```

未通过就按报告「待改」逐条修：拆句制造长短反差、删连接词、打散平行结构、加具体细节、去套话。术语和结论不能改。

**按模式裁剪**：`timed` / `rescue` 只写 1 版完整答案直接 `fill`，不跑多轮打磨；`rescue` 下即使来不及打磨也**必须写一版落进输入框，不留空**。

### 5. 逐屏复核

```bash
scripts/run.sh shot --out shots/after1.png
```

**必须看图**逐题核对：勾选有没有点亮、文本有没有落进输入框、有没有点错行。`verify` 只能告诉你「答案是否属于这一屏」，判断不了勾选状态：

```bash
scripts/run.sh verify --screen shots/screen1.json --answers answers.json
```

**按模式裁剪**：`full` 每屏复核；`timed` 每 3–4 屏抽样 1 次，且 `fill` 后至少看 1 张；`rescue` 只在交卷前抽查关键题。第一屏无论什么模式都必须人工看图复核，确认落点准了再往下。

### 6. 翻页

**用答题卡跳题，不要用 `next`**：实测「下一题」点 4 次都没反应，白费一轮；答题卡点题号 100% 生效（跳转后自动收起）。

```bash
scripts/run.sh click --x 1078 --y 135     # 开答题卡
scripts/run.sh click --x 958  --y 301     # 点 3 号题 → 跳到该题所在屏
```

题号坐标以当前截图重新量为准（`references/itest-ui.md` 第十节全卷实战标定为间距 60px，早期 55px 记录已废弃）。`scripts/run.sh next --screen s.json` 保留但**不推荐使用**。

翻页后回到第 1 步，重新截图、重新跑 `budget`、重新产出 `screen.json`。阅读题一屏多题时，先做完本屏再翻。

### 7. 交卷

```bash
scripts/run.sh submit --screen shots/screenN.json          # dry-run，只报坐标
scripts/run.sh submit --screen shots/screenN.json --yes    # 真点，并处理确认弹层
```

- 只在最后一屏复核通过、用户明确同意后执行。
- 若弹「您有 N 道题未完成」，先返回补齐，不要硬交。
- **倒计时卷**：`submit` 在剩余 ≤ 120 秒时会打印 `[ACTION_REQUIRED]`，说明距自动交卷还剩多少。先确认未答题是否已保底填满；是否现在主动交卷**必须由用户明确同意**，用户不答就什么都不点，让平台按规则自动交卷。
- 交卷后截图留档；有次数限制的测验失败一次就停，先看现场，不盲目重试。
- **交卷成功后 `submit` 会自动打印「录音占用报告」**（文件数、每个大小、合计）。看到输出里的 `[ACTION_REQUIRED]`，助手必须用 AskUserQuestion 向用户报告大小并询问是否删除，建议三个选项：`全部删除` / `保留最新一份` / `不删`。**只有用户答"删"才执行 `cleanup --apply`**，其余一律不删。
- 若是**用户自己点交卷**（没走 `submit`），助手确认页面已交卷后主动跑一次 `scripts/run.sh postsubmit`，同样走上面的询问流程。

### 8. 复盘

交卷后若允许查看答卷，截图读每题「我的答案 / 正确答案 / 得分」，输出错题清单。若提示「考试尚未结束，无法查看成绩」，如实告诉用户，不要猜。

### 9. 收尾清理（交卷后，由用户决定）

交卷成功后 `submit` 会自动跑 `postsubmit` 报出录音占用（见第 7 步）。助手据此询问用户，按回答执行：

| 用户回答 | 执行 |
| --- | --- |
| 全部删除 | `scripts/run.sh cleanup --apply` |
| 保留最新一份 | `scripts/run.sh cleanup --keep 1 --apply` |
| 不删 / 未回答 | 什么都不做 |

```bash
scripts/run.sh postsubmit                  # 单独补一份报告（只报告，绝不删文件）
scripts/run.sh cleanup                     # 随时查看将删清单（默认 dry-run）
scripts/run.sh cleanup --apply             # 仅在用户明确同意后
```

- **绝不自动删除**。删除不可恢复，而存疑题（细节题、数字题）常常还要回听原文，何时删必须由用户决定。
- 只处理本技能 `audio/` 目录内的 `.wav` 普通文件，不递归、不碰其他目录；60 秒内刚写入的文件默认跳过（疑似仍在录制）。
- 精确删一个：`cleanup --file paper_20261121.wav --apply`。

## 听力音频采集（实验性，仅训练卷）

我听不到声音，但可以把「听」翻译成「读」：用 WASAPI 回环录制**系统正在播放的数字音频** → 转写成英文逐字稿 → 读文字判断答案 → 复用已标定坐标点选。完整链路、实测数据与择优结论见 `references/audio-capture.md`。

- **边界**：只录「已经播放出来的声音」，不改网页、不读 `<audio>`、不翻网络请求、不下载受保护的音频文件。**仅训练 / 模考卷**；正式考试有监考、人脸识别、抓拍、考试码时按安全边界直接拒绝。
- **限时卷禁用本链路**：整卷实测 26 分钟音频、加操作间隔 41 分钟，且每段只播一次、录砸补不回来。任何倒计时卷都装不下，听力题按用户给的答案填或跳过并在回报中标明。
- **现状**：2026-11-21 已完成可行性验证，并用「四级听力模拟题（三）」整卷 25 题实战跑通（录制 → 转写 → 逐题点选 → 答题卡全绿，未交卷）。仍是**实验性链路**：逐屏坐标靠 `uia` 现取，尚未固化成一条自动命令。
- **择优结论**：用云端转写工具（逐字命中、自带时间戳分段、零安装）；本地 FunASR 在本机 Windows 上有 `fcntl` / `/tmp` / `ffmpeg` 三处硬伤，暂不可用。
- **每段听力只播一次**：不能暂停回放，录砸补不回来；先确认录音有效（`silence: false`）再判断答案。新卷首次仍建议先做纯录音演练。
- **回报口径**：点选项是 100% 机械准确；「听懂 → 选对」是辅助判断，准确率明显更低。没把握的题标出来交用户定，不硬猜。

## 坐标系（重要，踩过坑）

- `act.ps1` 已做线程级 DPI 感知，`shot` 截出的就是 **2560×1600 物理像素图**，`click --x --y` 也用同一套物理坐标。**截图上量到的坐标直接点，不做任何换算。**
- 前提一：**`act.ps1` / `uia.ps1` 必须保存为 UTF-8 带 BOM**。无 BOM 时 PowerShell 5.1 按 GBK 读中文，`Add-Type` 的 C# 代码跟着崩，整个动作层返回 `{}`（`info` 会显示 1707×1067 逻辑像素，就是丢 BOM 的症状）。
- 前提二：窗口最大化、贴 (0,0)、不被遮挡。窗口一移动，全部坐标作废，必须重新 `shot`。
- 前提三：全程只用本技能的 `run.sh shot / click`，不要混用其他截图工具。
- `uia.ps1` 的坐标**只在窗口最大化且位于原点时可信**（误差 <5px）；窗口移位后可能差几百像素，只用来校对文字。

## 命令速查

| 命令 | 作用 |
| --- | --- |
| **阶段 P（强制首步）** | |
| `scripts/bootstrap.ps1` / `bash scripts/bootstrap.sh` | **一键环境自检与自动准备**：定位/下载 Node、补 BOM、修行尾、建目录、判定 route，输出 JSON + 中文报告 |
| `scripts/run.sh doctor [--json] [--no-fix]` | 用已解析的运行时快速复检环境（不下载）；`--no-fix` 只体检 |
| `scripts/run.sh scale --auto --coords "x,y"` | 把 2560×1600 预设坐标粗换算到本机分辨率 |
| **业务动作** | |
| `scripts/run.sh info` | 前台窗口 / 光标 / 屏幕尺寸 |
| `scripts/run.sh activate` | 把 iTEST 带到前台 |
| `scripts/run.sh topmost --title X` | 强制置顶（WorkBuddy 抢焦点时必用） |
| `scripts/run.sh minimize --title WorkBuddy` | 最小化遮挡窗口（`--front` 会最小化当前前台，慎用） |
| `scripts/run.sh shot --out x.png` | 截当前屏 |
| `scripts/run.sh uia --out u.json` | 导出无障碍树（文本 + 坐标） |
| `scripts/run.sh clock --screen s.json [--reset]` | 记录计时快照（倒计时 / 正向计时 / 未知），换卷用 `--reset` |
| `scripts/run.sh budget --answered N` | 算剩余 / 已用 / 每题均耗 / 预计还需，输出 `[MODE=...]` |
| `scripts/run.sh move/click --x N --y N` | 移动 / 点击 |
| `scripts/run.sh scroll --x N --y N --clicks -5` | 滚轮（负数向下） |
| `scripts/run.sh type --text "…"` | 输入（默认粘贴，`--raw` 逐字） |
| `scripts/run.sh key --combo "ctrl+a"` | 按键 |
| `scripts/run.sh record --list` | 列出回环录制设备 |
| `scripts/run.sh record --out a.wav --seconds 60` | 回环录制系统音频（实验性，限时卷禁用） |
| `scripts/run.sh guard --screen s.json` | 正式考试红线检查 + 限时模式提示 |
| `scripts/run.sh fill --screen s.json --answers a.json [--dry]` | 批量作答 |
| `scripts/run.sh verify --screen s.json --answers a.json` | 检查答案归属 |
| `scripts/run.sh next --screen s.json` | 下一题（⚠️ 实测不响应，优先用答题卡跳题） |
| `scripts/run.sh submit --screen s.json [--yes]` | 交卷（默认 dry-run；剩余 ≤120s 会提示自动交卷风险） |
| `scripts/run.sh postsubmit` | 交卷后报告录音大小 + 输出待询问标记（绝不删文件） |
| `node scripts/textcheck.js <f>` | 文本 AI 味量化 |
| `node scripts/answercheck.js <check.json> [--partial] [--json]` | 填空题答案守恒校验（数量 / 越界 / 重复 / 缺号） |
| `scripts/run.sh cleanup [--apply] [--keep N] [--file f.wav]` | 做完题后删录音（默认 dry-run） |
| `node scripts/lint.js` | 发布前自检（含限时策略关键词检查） |

## 输出要求

用中文回报，不贴原始 JSON：

0. **阶段 P 环境结论**（每次必报）：`ready` 与 `route`、用了哪个 Node 及来源、是否自动下载了便携运行时、自动补齐了哪些条件（BOM / 行尾 / 目录）、有哪些降级口径。有 `[阻塞]` 项说明卡在哪、需要用户做什么；`route=scene` 要明确说明「环境已就绪，只差您本人登录 iTEST」。
1. **做了哪份卷子**：名称、题型与题量、完成到第几屏、是否交卷。
2. **作答情况**：客观题 `已确认/总数`、存疑题（题号 + 选择 + 一句话理由）；主观题字数与人写度分数、改了哪几类特征。听力/口语是否跳过。
3. **填空题专项**：给一张 `屏幕题号 | 文中空号 | 答案 | 依据 | 置信` 表，说明跑过 `answercheck.js` 的结果；存疑题单独列出两种判断与理由，不硬猜。
4. **本次重点**：3–6 条「知识点 → 本题怎么考」，便于复习。
5. **交卷后**：若交卷成功，报告录音文件数与合计大小，并明确询问用户是否删除；未得到同意前不得执行删除。
6. **限时卷额外回报**：计时形态与开局剩余；结束时剩余 / 已用 / 每题均耗；实际跑的模式（`full` / `timed` / `rescue`）、中途切档次数与砍掉的关卡；是否有自动交卷风险、是否主动交卷；**保底填入的存疑清单**（题号 + 两种判断），便于用户交卷后复核。

中途停下时，说明卡在哪一步、已填多少、需要用户决定什么，并给出截图路径。

## 发布到开放平台前

```bash
node scripts/lint.js
```

退出码 0 才算可发布。注意：`version` 必须写成三段式并加引号（如 `"2.4.0"`）；用 `cleanup --apply` 清掉 `audio/`，再清理 `shots/`、`.scratch/`、`.archive/` 与任何真实考试 ID、JWT（`eyJ...`）。`_skillhub_meta.json` 的版本号必须与 SKILL.md 一致并写 `userModified: true`，防止市场更新静默覆盖本地改动。`lint.js` 会额外检查 SKILL.md 的限时关键词（倒计时 / timed / rescue / 保底 / clock / budget）、`references/timed-mode.md` 是否存在，以及编排层是否有 `clock` / `budget` / `decideMode` / `autoSubmit`，防止改版时把限时能力弄丢。**阶段 P 新增的 4 个脚本与 `references/environment_setup.md` 也要一并纳入分发清单**（发布版 / 萌新版模板需同步）。

## 三版本维护（重要）

本技能有三个版本，名字 / 产物各不相同，可共存、互不覆盖：

| 版本 | 位置 / 产物 | 版本名 | 能力 |
|---|---|---|---|
| 本地满血版 | `~/.workbuddy/skills/itest-assistant/` | `2.4.0-local` | 助手自行判题 + 填空题解法 + 文本量化优化 + 限时分档 + **阶段 P 环境自检与自动准备（bootstrap / preflight / scale，开箱即用）**（本文件所在版本，开发源） |
| 发布版 | `dist/itest-assistant-publish.zip` | `2.0.0` | 只按用户给的答案操作，无文本优化（上架用） |
| 萌新版 | `dist/itest-assistant-newbie.zip` | `2.3.0-newbie` | 满血版全部能力 + 一键环境体检 / BOM 自动修复 / 跨分辨率换算 / 零基础文档，开箱即用 |

> **满血版自 2.4.0 起已内建阶段 P**：`bootstrap.ps1` / `bootstrap.sh` / `preflight.js` / `scale.js`
> 与 `references/environment_setup.md` 是本版本新增文件，判题能力、动作层、限时能力全部保持向后兼容。
> 重建两个分发版时需把这些文件纳入复制清单并同步模板 SKILL.md，否则分发版缺少阶段 P 命令。

改了满血版后，重建两个分发版：

```bash
cd ~/WorkBuddy/2026-11-20-23-43-15
PY_BIN=<python路径> node .build/build-publish.js --zip      # 发布版
PY_BIN=<python路径> node .build/build-newbie.js             # 萌新版（默认就打 zip）
```

- `build-publish.js`：从满血版复制文件、排除 `textcheck.js` / `answer-quality.md` / `question-types.md` / `answercheck.js` / 运行产物，再用 `.build/publish-template/` 覆盖三个发布口径文件（SKILL.md、walkthrough.md、answers.example.json）。**填空题判题手册与守恒校验是满血版专用能力，发布版按「用户给答案」口径不得包含，已加入排除清单**；这类改动不需要改模板，但必须重建 zip。若满血版改了发布版也要用的功能或命令，才需要同步改这三个模板文件。脚本自带残留词与 lint 自检，构建失败会报错。
- `build-newbie.js`：从满血版复制**全部功能文件（不剥离任何判题 / 文本能力）**，用 `.build/newbie-template/` 覆盖 / 注入萌新版专属文件（SKILL.md、README.md、run.sh、doctor.js、scale.js、quickstart.md、portability.md、walkthrough.md），做编码归一化（`.ps1` 强制 UTF-8 BOM、其余 LF 无 BOM），跑 lint 与完整性自检后打包。萌新版技能名为 `itest-assistant-newbie`，与另外两版不同目录，**导入不会覆盖**。
- **限时能力是三版本共用的**：`scripts/itest.js` 的 `clock` / `budget` / `decideMode` 与 `references/timed-mode.md` 会随复制进入两个分发版；发布版与萌新版的 `SKILL.md` / `walkthrough.md` 由模板覆盖，**必须同步补上倒计时 / timed / rescue / 保底 / clock / budget 六个关键词**，否则新 lint 会判定构建失败。

三个 zip 文件名固定不同（`itest-assistant-full.zip` / `itest-assistant-publish.zip` / `itest-assistant-newbie.zip`）。发布版与满血版同为 `itest-assistant` 目录名，**不要把发布版导入到满血版的同一目录**，否则会覆盖本地文件；萌新版无此问题。

## 资源

- `scripts/bootstrap.ps1`：**阶段 P Windows 零依赖引导**（纯 ASCII，定位/下载 Node、持久化运行时、调 preflight、输出纯 ASCII JSON）。
- `scripts/bootstrap.sh`：**阶段 P Git Bash / macOS / Linux 零依赖引导**（同上语义，平台感知便携包）。
- `scripts/preflight.js`：**阶段 P 自检核心**（条件分层、自动修复 BOM/行尾/目录、动作层复测、route 决策，产出结构化 JSON + UTF-8 中文全文报告）。
- `scripts/scale.js`：跨分辨率坐标粗换算（阶段 P 的 route 层辅助工具）。
- `references/environment_setup.md`：**阶段 P 完整规范**（条件清单、Node 解析优先级、各平台兜底、目录约定、凭据边界、故障排查）。
- `scripts/act.ps1`：桌面动作层（截图 / 移动 / 点击 / 输入 / 粘贴 / 按键 / 激活 / 批量）。**必须 UTF-8 带 BOM，阶段 P 会自动补写**。
- `scripts/uia.ps1`：无障碍树导出（文本 + 坐标），读长文时比截图 OCR 准。**必须 UTF-8 带 BOM**。
- `scripts/record_loopback.py`：WASAPI 回环录制（实验性，需 `pip install soundcard`）。
- `scripts/itest.js`：编排层（shot / uia / clock / budget / guard / fill / verify / next / submit / postsubmit / cleanup）。
- `scripts/run.sh`：统一入口，优先复用 `node_path.txt` 里阶段 P 持久化的运行时，分派 doctor / scale / record 与全部原有子命令。
- `references/itest-ui.md`：iTEST 页面地图、题型识别、计时形态判定、踩坑记录。
- `references/timed-mode.md`：**限时周测的读图判据、三档模式、降级顺序、保底填满、交卷策略与边界**（限时卷必读）。
- `references/audio-capture.md`：听力音频回环录制、转写择优、实测数据与硬限制。
- `references/question-types.md`：填空题族解法手册（15 选 10 选词填空、段落信息匹配、短文填词），含编号映射、词性定位、两轮交叉与校准样例。
- `references/walkthrough.md`：下次周测照着做的操作清单与常见故障。
- `assets/screen.example.json`、`assets/answers.example.json`：两份输入的结构示例。
- `references/answer-quality.md`：正确率双答案交叉法、AI 味与 AIGC 判定率优化 7 个改法。
- `scripts/answercheck.js`：填空题答案守恒校验（数量 / 字母越界 / 重复 / 缺号 / 单词形态）。
- `scripts/textcheck.js` / `scripts/lint.js`：文本关卡与发布自检。
