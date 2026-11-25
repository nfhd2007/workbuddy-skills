---
name: hike-course-assistant
author: nfhd2007
version: 1.1.0
display_name: 智慧树课程助手
display_name_en: Hike Course Assistant
description_zh: "在 hike-teaching-center.polymas.com（AI智慧课程中心）与 wisdom-mooc.zhihuishu.com（智慧树 MOOC 学习页）辅助完成课程的重复性播放流程——自动连播下一节、保持会话、静音后台播放、维护进度台账；另可对非计分练习 / 自检题自动填写答案，最终交卷仍由用户本人确认。在用户本人已登录的会话里操作、不碰凭据；计分测验、作业与考试一律不代答；不调用题库接口、不绕过验证、不伪造观看时长、不做多账号批量操作。"
description_en: "Assists repetitive playback workflows on the Zhihuishu AI Teaching Center and MOOC study pages: auto-advance to the next lesson, keep the session alive, mute playback, and maintain a progress ledger. Can also auto-fill answers for non-graded practice / self-check questions, while final submission is left to the user. Runs only in the user's own logged-in session; never answers graded quizzes, homework or exams, never calls question-bank or answer APIs, bypasses verification, fabricates watch time, or operates multiple accounts."
description: 智慧树课程助手：在 hike-teaching-center.polymas.com（AI智慧课程中心）与 wisdom-mooc.zhihuishu.com（智慧树 MOOC 学习页）辅助完成课程的重复性播放流程——自动连播下一节、保持会话、静音后台播放、维护进度台账；另可对非计分练习 / 自检题自动填写答案（点击选项 / 填入答案文本 / 推进下一题），最终交卷仍由用户本人确认。当用户提到「刷课」「挂课」「自动连播下一节」「课程进度」「还剩几节没看」「AI教学中心」「智慧树」或上述域名，或「这道题怎么做」「给个参考答案」「自动填答案」「帮我填上」时应使用本技能。不适用于计分测验、作业与考试的代答或自动提交、绕过验证、伪造观看时长、多账号批量操作；答题辅助仅限非计分练习，不调用题库接口、不自动交卷。运行前自动完成环境自检与依赖准备（Python / 浏览器工具 / 桌面备用分支 / 台账），使刚安装 WorkBuddy 的电脑也能直接使用。工程思路借鉴并谨此致谢 ocsjs/OCS 网课助手（MIT）原作者与贡献者。
agent_created: true
---

# 智慧树课程助手

> 技术标识：`hike-course-assistant`（技能 `name` 字段只允许小写字母、数字与连字符，故中文名作为显示名使用）

## 目的与定位

把在线课程里重复的播放操作自动化：在用户本人已登录的浏览器会话中，观察课程播放状态、在一节结束后进入下一节、保持会话有效、静音后台播放，并把进度记成可查询的台账。

本技能的播放流程只做点击与状态读取，不改变平台记录的学习事实；答题辅助会在**非计分练习 / 自检题**上自动填写答案（会改变该练习的作答状态），但**计分作业、测验与考试一律零点击**。

另有**答题辅助（旁路能力）**：仅对**非计分的练习 / 自检题**，抄录题干与选项、推理出答案，并在页面上**自动填写答案**（点击选项 / 填入答案文本 / 点「下一题」推进）。该能力不进入播放主循环；计分作业、测验与考试一律不适用，最终「交卷 / 提交成绩」仍由用户本人确认。完整规则见 `references/answer-assist.md`。

## 硬性边界（不可协商）

执行以下动作前立即停止并把控制权交还用户：

- 代答计分测验、考试、作业，或任何计分考核的选择、填写与提交
- 在非计分练习上点击最终「交卷 / 提交成绩」按钮
- 绕过验证码、人脸/摄像头抽检、风控校验
- 伪造观看时长、篡改心跳上报、调用或伪造接口数据、调用题库 / 搜题接口 / 答案 API
- 使用或保存用户账号密码、代输登录凭据
- 多账号批量操作、并发开多个课程会话
- 关闭用户正在使用的窗口或标签

遇到验证码、人脸、计分测验、考试、作业界面时：**停止整个循环，不做任何点击，报告所见内容**。

**答题辅助的硬上限**（仅适用于非计分练习，见 `references/answer-assist.md`）：

- 允许：只读题干与选项 → 检索 / 推理 → 点击选项 / 填入答案文本 / 点击「下一题 / 确认 / 检查答案」推进 → 每步重新观察验证。
- 禁止：点击最终「交卷 / 提交成绩」；调用题库、搜题接口、答案 API 或平台任何写接口；读取隐藏字段或页面源码里的答案；替用户确认验证码 / 人脸 / 风控弹窗；连续盲操作。
- 判不准是否计分，或出现「测试 / 考试 / 作业 / 测验 / 限时 / 计分 / 计入平时分 / 仅一次提交机会」等字样时，一律按 `VERIFICATION` 停止，**零点击、不给答案、不填写**。
- 用户随时说「停」即立即停止，交还控制权。

登录态失效时只提示用户本人重新登录，不尝试自动重登。

## 运行前：环境自检与自动准备（每次触发技能的第一件事）

**不得假设运行电脑已配置好。** 每次被触发、执行任何浏览器或桌面动作之前，先完成以下三步。目标是：一台刚安装 WorkBuddy、从未配置过的电脑，也能在最少人工配合下直接运行。

### 第 -1 步：本机体检与自动准备

1. 解析 `<SKILL_DIR>`（本 `SKILL.md` 所在目录的绝对路径）与 `<CWD>`（当前工作区绝对路径）。`<SKILL_DIR>` 由脚本从自身位置解析，不要假设工作目录就是技能目录。
2. 执行体检（stdout 为纯 JSON，退出码恒为 0，状态一律读 JSON，不把退出码当作是否就绪）。**首选零依赖引导脚本**，它会自动定位可用的 Python（含 WorkBuddy 随包分发的解释器），无需用户预先配置：

   ```bash
   bash "<SKILL_DIR>/scripts/bootstrap.sh" check --json --workspace "<CWD>"
   ```

   Windows 纯 PowerShell 环境用 `powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>\scripts\bootstrap.ps1" check "<CWD>"`（stdout 为纯 ASCII JSON，规避 PowerShell 5.1 的 GBK 中文乱码）。确认 `python` 可用时也可直接调用 `python "<SKILL_DIR>/scripts/preflight.py" check --json --workspace "<CWD>"`；加 `--ascii` 可输出纯 ASCII JSON。Python 定位优先级见 `references/environment.md` 第八节。
3. 按返回的 `next_action` 决策：

   | `next_action` | 动作 |
   | --- | --- |
   | `prepare` | 执行 `prepare --json --workspace "<CWD>"`，以其返回的 `ready` / `next_action` 为最终结论。脚本自动建运行态目录、生成 `env-<技能名>.json`、可选初始化台账；**不要让用户手动建目录** |
   | `wait_user` | 一次性列出 `needs_user` 中 `blocking: true` 的项（步骤 + 可复制命令），等待用户完成后重新 `check` |
   | `probe_tools_then_run` | 进入第 -2 步 |

4. 逐条执行 JSON 中的 `agent_actions`（插件状态检查、缺失技能安装等），执行后重新 `check --json` 确认。完整条件表、命令与报错处理见 `references/environment.md`。

### 第 -2 步：工具层探测与自动降级

1. 检索 `mcp__browser__browsers_list` 的 schema。能加载 → 方案 A 可用，进入第 -3 步。
2. 检索不到 → 按 `references/environment.md` 第六节启用 Browser Use 插件：用 `list_installed_plugins` 查状态，引导用户在「设置 > 智能体 > 浏览器操控」开启。**内置浏览器（IAB）无需任何扩展**；只有需要复用外部浏览器登录态时才装扩展。
3. 仍不可用 → **自动降级到方案 B**，并对方案 B 的条件执行同一轮 `check → prepare → agent_actions`：缺失的 `computer-use` / `desktop-control` 技能用 `search_and_install_skills` 自动安装；`agent-desktop` 缺失时给出安装命令，用户明确同意后用 `prepare --allow-install` 自动安装。
4. 方案 A 与方案 B 都不可用 → 一次性输出阻塞项清单并停止，不改用 HTTP 抓取、命令行浏览器或任何绕过手段。

### 第 -3 步：进入主流程

只有通过第 -1 / -2 步，才进入下方「工作流」第 0 步。`needs_user` 中 `blocking: false` 的项（登录态、课程名）不在此处等待，由第 1 / 1.5 步按原有规则处理。

### 硬规则

- **不跳过 `check`**：即使 `env-<技能名>.json` 已存在也要重跑，插件、CLI、技能可能在上次运行后被卸载或升级。
- 桌面分支的所有绝对路径从 `prepare --json` 返回的 `env_file` 指向配置中的 `paths` 读取，或用 `preflight.py paths --json` 获取；**禁止硬编码用户名、盘符或版本目录名**。
- 自动准备只做本地文件与已授权的工具层动作：禁止代替用户登录、禁止点击 UAC / 安装器 / 密码框、禁止未经用户明确同意执行全局安装。
- 环境类失败一律「先自动修、修不了再一次性报告」，不得反复追问用户。

## 站点分工（2026-11-21 实跑确认）

| 站点 | 角色 | DOM 快照可用性 |
| --- | --- | --- |
| `hike-teaching-center.polymas.com` | AI智慧课程中心：登录、12 门 AI智课列表、课程主页、我的学习 | **几乎不可用**（课程中心 3 节点、课程主页 1 个空 button、我的学习 0–1 节点）→ 必须截图识别 + 坐标点击 |
| `wisdom-mooc.zhihuishu.com/study/index?recruitAndCourseId=...` | 智慧树 MOOC 学习页：左侧章节树、中间视频区 + AI课程导览、右侧 AI学伴；**实际播放发生在这里** | **可用**（20+ 节点；章节为 `role="button"`，小节为编号 `div` + 标题 `div`）→ 可用 `node_id` 点击章节/小节 |

课程中心的课程可能是空课（如「新生入学教育与导学[理论]」0 资源），需先判定再决定是否继续；有视频内容的课程在智慧树学习页。两处登录态各自独立，都在同一浏览器里，用户本人登录后技能在受控标签内操作，不碰凭据。

### 按页面版本分派（借鉴 OCS 的适配器设计）

OCS 把智慧树按 UI 版本拆成多个处理器（共享课 / 新版 AI 课 / 新智慧学习 / **Hike**、**HikeV2** 等），共用一个 `ZHSProcessor` 接口。本技能沿用这个「先判页面版本、再选信号来源」的思路，**不写死一套选择器**：

| OCS 接口职责 | 本技能对应状态/动作 | 无 JS 条件下的近似实现 |
| --- | --- | --- |
| `hasJob()` | `EMPTY_COURSE` | 快照/截图里是否存在任务节点、是否出现「暂无数据 / 共 0 个学习资源」 |
| `getNext({ next, restudy })` | `ENDED` → 进入下一节；列表为空即 `ALL_DONE` | 过滤已完成项（✓ 勾选）→ 定位当前项 → 取下一项；`restudy` 默认关闭 |
| `hideDialog()` | `DIALOG` | 仅关闭非考核类提示弹窗；考核类弹窗按 `VERIFICATION` 立即停 |
| `getCourseName()` / `getChapterName()` | 台账字段 | 从可见 DOM 文案或截图读取 |

> 注意：OCS 靠页面内 JS 与 CSS 选择器实现这些接口，本技能**不能执行 JS**，所以这里借鉴的是职责划分，不是实现。实际判定一律靠可见 DOM 快照 + 截图人工判读；平台改版出现新 UI 时按 `UNKNOWN` 停下报告，不要套用旧文案盲点。详见 `references/ocs-reference.md`。

## 前置条件（由第 -1 / -2 步自检保证）

- `ready == true`，且工具层探测成功（方案 A），或已自动降级到方案 B 且其条件齐备。
- 桌面分支路径已从 `env-<技能名>.json` 的 `paths` 解析；首次运行或出现路径类异常时已重跑 `prepare`。
- `mcp__browser` 工具可用；首次调用前用工具检索加载所需 schema，不要凭记忆猜参数。参数速查阅 `references/browser-tools.md`。
- 用户已在目标浏览器会话中登录，或愿意手动登录一次（由第 1 步处理，禁止代输凭据）。
- 用户已明确指定要刷哪门课，且该课存在未完成的视频小节。**若用户表示已全部看完，直接输出台账汇总并停止，不要为了「试跑」去重播已完成视频。**
- 已阅读 `references/site-notes.md`；未填项按保守策略（见「状态判定」）。
- 环境自检出现 `blocking` 项、或需降级方案 B 时，已阅读 `references/environment.md`。
- 启用答题辅助前已阅读 `references/answer-assist.md`；仅在用户明确请求、且题目可判定为非计分练习时启用；开始前已向用户确认「自动填写答案」的范围与停止方式。

## 默认参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| 观察间隔 | 45 秒 | 每轮循环之间的间隔，可在 30–60 秒间调整；上一轮未结束不启动下一轮（防重入） |
| 单次最长运行 | 120 分钟 | 到点停止并输出汇总 |
| 未知状态连续上限 | 3 轮 | 连续无法分类即停止并报告 |
| 静音 | 首次进入循环时执行一次 | 点音量按钮或按 `m`，之后不再重复 |
| 复习模式 `restudy` | 关闭 | 只跳未完成小节；开启才会重看已完成小节。默认关闭，避免重播已完成视频（借鉴 OCS 同名配置） |
| 异常自动刷新 | 开启，上限 2 次 | 截图/画面异常时 `tab_reload` 一次尝试恢复；连续失败即停止报告（借鉴 OCS `reloadWhenError`） |
| 台账文件 | `./hike-progress.json` | 可用 `--file` 覆盖 |
| 答题辅助 `answer_assist` | 按需（默认不启用） | 仅用户显式请求时开启；主循环不自动进入答题辅助；开启后可在非计分练习上自动填写答案，但仍不自动交卷 |
| 单轮最多填写题数 | 20 | 达到即停止并输出汇总，防止在未知界面里无限循环 |
| 环境自检 | 每次触发强制执行 | 见「运行前：环境自检与自动准备」；仅站点连通性探测可用 `--no-network` 跳过 |

用户在触发时给出的参数覆盖默认值。

## 工作流

> 进入本工作流前，必须已完成第 -1 / -2 步环境自检与工具层探测；未通过时不得开始任何浏览器或桌面动作。

### 第 0 步：确认受控标签（每轮动作前都要做）

1. `tabs_list` 检查受控标签是否还在。**实测受控状态会周期性丢失**（登录、reload、claim 其他标签后都可能掉）。
2. 不在则 `user_open_tabs` 找用户标签 → `tabs_claim` 重新接管；登录态保留在浏览器里，不需要重新登录。
3. 记录 `browser_id` / `tab_id`，本轮后续调用复用。

### 第 1 步：取得已登录的标签（方案 A，默认）

1. `browsers_list` 取得 `browser_id`。
2. `user_open_tabs`；若有目标站点标签，`tabs_claim` 接管。
3. 否则 `tabs_new` / `tab_goto` 打开 `https://hike-teaching-center.polymas.com`。
4. `dom_cua_get_visible_dom` 读一次快照，判断是否为登录页。
5. 若为登录页：**暂停**，向用户输出「请在受控标签中手动登录，完成后回复继续」，等待用户确认后重新快照。全程不读取、不输入、不保存账号密码与验证码。
6. 会话有效后记录 `browser_id` / `tab_id`。

站点存在浏览器检测，非现代浏览器只返回「当前浏览器暂不支持」提示，因此必须使用真实浏览器工具，不要用 HTTP 抓取代替。

### 方案 B：操控用户现有浏览器窗口（自动降级分支）

当第 -2 步判定 `mcp__browser` 不可用、且插件短期无法启用时**自动切换**到本分支，不再要求用户手动改配置。切换前先对方案 B 的条件执行一轮 `check → prepare → agent_actions`：技能缺失用 `search_and_install_skills` 自动安装，`agent-desktop` 在用户同意后用 `prepare --allow-install` 自动安装。所有绝对路径从 `env-<技能名>.json` 的 `paths` 读取，禁止硬编码。用户明确要求操控自己现有窗口时也走本分支。

改用 `computer-use`（截图 + 坐标点击）或 `desktop-control`（无障碍树 + `ref`）：

- 每个动作前必须截图或快照取坐标/`ref`，动作后立即再次观察验证。
- 禁止连续盲操作，禁止凭记忆坐标点击。
- 该分支会占用真实鼠标键盘；开始前提示用户不要同时使用鼠标。

桌面分支的路径解析与条件准备见 `references/environment.md` 第七节；两套桌面技能的调用协议见 `references/browser-tools.md` 末尾。

### 第 1.5 步：从课程中心进入指定课程（polymas 侧）

1. 停在「AI智慧课程中心」时，先截图定位目标课程卡片。**以课程名为准**，不要用教师名（页面上有 URL 编码乱码）。
2. 用 `cua_click` 点卡片中心；**首次点击常不生效**，重试一次，或把「点击 + 截图」放进同一个 `cua_execute` 动作序列。
3. URL 变化会滞后，以截图出现「课程主页」为准，不要立刻读 URL 就下结论。
4. 若课程主页显示 0 资源 / 空态（见「停止条件」），报告并停止。

### 第 2 步：建立基线

按当前站点取信号：

- **polymas 侧**：截图读取「总学习进度 N%」「共 N 个学习资源」「0.0学分 / 0.0学时」；左侧导航 7 项（课程主页 / 我的学习 / 我的任务 / 我的消息 / 小组学习 / AI翻转 / 学习助手）。
- **智慧树侧**：`dom_cua_get_visible_dom` 读章节树，抽取章标题（`第N章: …`）、小节编号（`0.1` / `1.1`）、小节标题（问句式）。**完成状态靠截图看小节前的 ✓ 勾选**（DOM 快照里没有该状态）。未展开的章节不出现在快照里，统计前需逐章展开。
- 用 `scripts/ledger.py init` 建立台账，再用 `record` 写入已知小节状态，输出一行基线摘要（课程、总节数、已完成、剩余）。若第 -1 步已用 `prepare --course` 初始化过台账，用 `init --force` 或 `record --total` 更新基线，不要沿用空台账。

### 第 3 步：主观察循环

每轮按固定顺序执行：

1. **观察**：先做第 0 步确认标签；再按站点取信号——polymas 侧以 `tab_screenshot` 为主，智慧树侧用 `dom_cua_get_visible_dom` + 截图。截图必须实际查看。
2. **分类**：

| 状态 | 判定依据 | 动作 |
| --- | --- | --- |
| `PLAYING` | 视频画面在动 / 播放器显示进度，无「下一节」提示 | 不点击，仅记录 |
| `ENDED` | 出现「下一节」「继续学习」「已完成」「观看完成」，或当前小节出现 ✓ 勾选 | 进入下一节 |
| `ALL_DONE` | 章节树所有小节均带 ✓ 勾选 | **停止，输出汇总** |
| `EMPTY_COURSE` | 「暂无数据」「共 0 个学习资源」「总学习进度 0%」「教学计划：暂无」「0.0学分 / 0.0学时」 | **停止并报告「该课程无学习内容」** |
| `DIALOG` | 出现非考核类提示弹窗（如「继续播放」确认） | 关闭该弹窗 |
| `SESSION_EXPIRED` | 回到登录页、出现「登录超时/请重新登录」 | 停止，提示用户重新登录 |
| `VERIFICATION` | 验证码、人脸、摄像头、计分测验、考试、作业、章节树里的「测试」节点、polymas「训练题库」tab，或**无法判定是否计分**的答题界面 | **立即停止，零点击，交还用户** |
| `PRACTICE_QUESTION` | 页面明确标注「练习 / 自检 / 不计分 / 不计入成绩 / 可反复作答」的题目界面 | **暂停播放循环**，转入第 3.5 步答题辅助（自动填写答案）；不确定是否计分时归入 `VERIFICATION` 并零点击 |
| `UNKNOWN` | 以上都不匹配 | 不动作，计数 +1 |

3. **动作**：
   - 首次循环执行一次静音：优先点击播放器音量按钮，否则 `dom_cua_keypress` 发送 `m`。执行后重新观察确认。
   - 智慧树侧优先用 `dom_cua_click` 点最近一次快照的 `node_id`（章节 `role=button`、小节标题 `div`）；**polymas 侧没有可用 `node_id`，一律用截图 + `cua_click` 坐标**。
   - `node_id` 只在生成它的那次快照内有效；界面变化后重新快照。
   - 每次点击后立即重新观察，确认状态真的变了再进入下一轮；不要重复可能已生效的动作。
   - 不主动导航离开课程页，不关闭受控标签，以保持后台播放与会话。
4. **记录**：状态变化（尤其是 `ENDED` → 下一节）后用 `ledger.py record` 写入。
5. **等待**：按观察间隔进入下一轮。工具没有 wait 能力，用循环节奏控制，避免高频轮询给页面施压。
6. **检查停止条件**。

### 第 3.5 步：答题辅助（旁路，自动填写非计分练习）

仅在 `answer_assist` 被用户显式请求，且题目可判定为**非计分练习**时执行。独立于播放循环；开始前向用户确认一次范围，之后按「一题一轮」推进：

1. **取题**：先做第 0 步确认受控标签，再用 `dom_cua_get_visible_dom` + `tab_screenshot` 抄录当前题的题干、选项与按钮文案；polymas 侧 DOM 不可用，一律以截图为准，**截图必须实际查看**。
2. **判类**：按 `references/answer-assist.md` 判定表确认「非计分」。命中计分特征或判不准 → 退回 `VERIFICATION`，零点击、不给答案、不填写。
3. **求解**：用模型知识推理，或用 WebSearch / 公开资料检索核对；不调用平台题库 / 搜题接口 / 答案 API，不读取隐藏字段或页面源码里的答案。低把握时先向用户说明不确定，不硬填。
4. **填写（本步核心）**：
   - 先重新取一次快照，`node_id` / 坐标只用最新一次观察的结果；**每次点击后立即再次观察**，确认状态真的变了再进下一题，不重试可能已生效的动作。
   - 智慧树侧优先 `dom_cua_click` 点选项的 `node_id`；polymas 侧无可用 `node_id`，用截图 + `cua_click` 坐标。文本输入用 `dom_cua_type` / `cua_type`。
   - 允许点击「下一题 / 确认 / 检查答案」这类**推进按钮**；**不点击**「交卷 / 提交成绩」。
5. **记录与收尾**：每填一题在对话里报一次（题号、所填答案、把握程度）；达到单轮题数上限、遇到交卷按钮、题目做完或用户说「停」即输出汇总，停在提交前请用户本人确认。之后询问是否继续播放循环；继续则回到第 3 步第 1 项重新观察。

> 该步骤只在**非计分练习**上做点击，不改变计分考核的任何记录；遇到验证码、人脸、风控提示或任何计分字样立即停止并交还用户。完整规则见 `references/answer-assist.md`。

### 第 4 步：停止条件

命中任一即停止：`ALL_DONE`；`EMPTY_COURSE`；用户要求停止（含「都看完了」）；达到单次最长运行；`SESSION_EXPIRED`；`VERIFICATION`；`PRACTICE_QUESTION`（暂停循环、转入第 3.5 步，达到单轮题数上限 / 交卷前 / 用户说「停」即收尾，由用户决定是否续跑）；`UNKNOWN` 连续达到上限；连续两轮点击后界面无变化（疑似被风控拦截）。

> **不要为了验证连播逻辑而重播已完成的视频。** 没有未完成小节时直接收尾。

### 第 5 步：收尾

1. 运行 `ledger.py summary`，输出已完成/剩余清单与完成比例。
2. 报告停止原因。
3. **保留受控标签**，不调用关闭/清理类工具，方便下一次直接续跑。

## 状态判定（重要）

浏览器工具**不能执行任意 JavaScript**（无 `evaluate` / `execute_script`），也没有 wait 能力。因此：

- 不读取 `video.currentTime`、`video.ended`、`video.muted` 等属性，不用 JS 注入静音或心跳。
- 只依据**可见 DOM 文案**、按钮状态与截图画面判定；文案以 `references/site-notes.md` 的实跑记录为准，未填部分按保守策略：仅识别明确字样，其余一律归为 `UNKNOWN` 且不点击。
- 站点差异见「站点分工」：**polymas 靠截图，智慧树靠 DOM 快照 + 截图**。
- **完成状态（✓ 勾选）只在截图上可见**，DOM 快照不含，必须看图。
- 绝不因「看起来像」就猜着点。宁可停下报告。

**答题界面的归类（保守优先）**：`VERIFICATION` 与 `PRACTICE_QUESTION` 的区别只在于「是否计分」。只有当页面上出现明确的「练习 / 自检 / 不计分 / 不计入成绩 / 可反复作答」等字样时，才归为 `PRACTICE_QUESTION`；出现「测试 / 考试 / 作业 / 测验 / 计分 / 计入平时分 / 限时 / 仅一次提交机会」，或两种字样都没有、判不准时，一律归为 `VERIFICATION` 并停止，不给参考答案。章节树的「测试」节点与 polymas「训练题库」tab 按 `references/site-notes.md` 的既有结论视为考核类，不进入。详见 `references/answer-assist.md`。

**自动填写的观察纪律**：只用**最新一次**快照的 `node_id` / 坐标；界面变化后必须重新快照，禁止凭记忆坐标连点。按钮语义按 `references/answer-assist.md` 的按钮语义表归类，认不出语义一律不点。

## 失败处理（实跑踩过的坑）

- 受控标签周期性掉线 → 每次动作前 `tabs_list` 确认，不在则重新 `tabs_claim`。
- 坐标点击首次常不生效 → 重试一次，或用 `cua_execute` 把「点击 + 截图」合并成一个动作序列。
- 截图报 `provider invocation timed out` → `tab_reload` 后恢复；期间标题与 URL 仍可正常读取，说明页面没崩。
- URL 路由滞后 → 判定页面是否切换以截图为准。
- `node_id` 只在生成它的那次快照内有效；点击后先验证再继续；对可能已生效的动作不重试。
- 多标签导致目标不明确时，用 `tabs_selected` / `tabs_get` 明确指定。
- 会话失效只提示用户重新登录，不尝试自动重登、不读取凭据。
- 任何异常都优先「停止 + 报告」，不尝试绕过。
- 答题辅助时题干抄录不全、选项缺失或截图模糊 → **不填写**，只报告能读到的部分并标注「信息不完整」，不猜题、不盲点。
- 点击后界面无变化或出现未知弹窗 → 立即停止该轮，重新观察并报告，不连续重试（疑似被风控拦截）。
- 无法确认题目是否计分 → 按 `VERIFICATION` 处理，零点击、不填答案；不要为了「帮上忙」而放宽判定。
- 任何一步出现「交卷 / 提交成绩」按钮 → 停在该处，交还用户本人确认。
- `check --json` 返回 `auto_fix` 非空 → 直接 `prepare --json` 复检，不要手动建目录或猜路径。
- `mcp__browser__browsers_list` 检索不到 → 按 `references/environment.md` 第六节启用插件；仍失败则自动降级方案 B 并准备其条件。
- 桌面技能路径失效、换了电脑或用户名不同 → 重跑 `prepare --json` 重新生成 `env-<技能名>.json`，禁止沿用旧路径。
- `python` 不可用 → 按 `references/environment.md` 第八节取 WorkBuddy 内置解释器绝对路径作为 `<PY>`。
- 环境项缺失但可自动修复时，不得把用户拉进来手动处理；只有 `blocking: true` 的项才需要一次性报告并等待。

## 致谢与设计借鉴

本技能的工程组织方式借鉴了开源项目 **OCS 网课助手**，谨向原作者及所有贡献者致谢。

| 项目 | 地址 | 说明 |
| --- | --- | --- |
| OCS 网课助手（主脚本） | https://github.com/ocsjs/ocsjs | TypeScript 用户脚本，MIT 许可；`ZHSProject` 的 `domains` 明确包含 `zhihuishu.com` 与 `polymas.com`，并设有 `Hike` / `HikeV2` 处理器 |
| OCS 桌面端 | https://github.com/ocsjs/ocs-desktop | Electron + Vue 3 + Playwright 的用户脚本启动器 |
| 官方文档 | https://docs.ocsjs.com | 平台兼容列表与使用说明 |
| 文档仓库 | https://github.com/ocsjs/ocs-docs | MIT 许可 |

**借鉴了什么（仅限工程思路）**：按域名与页面版本分派处理器的适配器结构（见「按页面版本分派」）；从任务列表过滤已完成项、定位当前项、取下一项的连播抽象；`hasJob()` 式的空课程判定；声明式配置项（`restudy` / `reloadWhenError` / `stopTime`）；进度汇总由记录数组派生而非单独存计数，避免数据不同步；轮询防重入与超时保护；仅在重要事件提醒的分级通知；以及「不要最小化浏览器、注意缩放比例」这类环境约束的经验提示。

**明确不借鉴**：本技能不含 OCS 任何源码，也没有引入其自动答题、题库接口 / 在线搜题、随机选项与提交试卷、弹窗测验代答、验证码识别与滑块破解、绕过脚本检测、多账号与浏览器多开、自动登录与凭据保存等功能。这些都在「硬性边界」中排除；OCS 自身也提示倍速超过 1.5x 存在封号风险，本技能因此不做倍速干预。新增的答题辅助只在非计分练习上按可见 DOM 逐题点击填写，不含 OCS 的自动答题实现：不调用题库 / 搜题接口、不随机选项、不按提交率自动交卷、不处理弹窗测验。技术路线也不同：OCS 在页面内注入 JS，本技能只用浏览器工具提供的可见 DOM 快照、点击、按键与截图。

> 参考项目的能力范围不代表本技能的许可范围；两者定位不同，一切以本文件的「硬性边界」为准。

## 资源

- `scripts/bootstrap.sh` / `scripts/bootstrap.ps1` — 零依赖引导层，自动定位 Python（PATH → WorkBuddy 随包 / 托管运行时）后调用 `preflight.py`；PowerShell 版固定输出纯 ASCII JSON。
- `scripts/preflight.py` — 运行环境自检 / 自动准备 / 路径解析，纯标准库，提供 `check` / `prepare` / `paths`；支持 `--ascii`，`prepare` 落盘 `last_preflight.json`。运行前用 `python <path> --help` 查参数，不要凭记忆猜。
- `scripts/ledger.py` — 进度台账，纯标准库，提供 `init` / `record` / `summary` / `reset`。运行前用 `python <path> <command> --help` 查参数，不要凭记忆猜。
- `references/environment.md` — 运行条件总表、三层自动准备模型、新机首次运行流程、工具层启用、方案 B 准备与常见报错。
- `references/browser-tools.md` — 浏览器与桌面工具的参数速查、能力边界、失败处理。
- `references/site-notes.md` — 双站点页面结构观察记录；未填项按保守策略执行。
- `references/ocs-reference.md` — OCS 项目调研记录、可借鉴清单与边界对照表。
- `references/answer-assist.md` — 非计分练习的自动填写规则：适用范围、计分判定表、按钮语义表、逐题工作流、停止条件与禁止清单。
