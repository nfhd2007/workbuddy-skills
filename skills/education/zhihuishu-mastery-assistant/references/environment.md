# 阶段 P 通道探测与交付模式判定（完整规范）

> 与 iTEST 爱考试助手「阶段 P」同构：先判定条件，**有条件就直接用，没条件就自动准备好（或自动降级到不依赖该条件的路径）再用**。v1.3.x 起增加更根本的口径：**环境自检是选路，不是闸门**——浏览器工具、已登录会话、桌面动作层、插件安装任一缺失，都不得阻断交付，只把 `channel` 降到 `readonly` / `offline`，继续按用户提问范围产出。
> **实况通道默认且优先为 WorkBuddy Edge 扩展程序**（`type=extension` / `family=edge` / `user_tabs`）。内置 IAB 不共享用户已登录会话、也没有 `user_tabs`，只作降级。精确识别字段见 `references/tooling.md`。

## 目标

一台刚安装 WorkBuddy、从未配置过的电脑，也能在最少人工配合下完成**实况运行**；而在一个 `mcp__browser__*` schema 全部加载不到、连接器列表为空、桌面层未安装、插件无法安装的沙箱里，也能完成**离线交付**（页面标题与提示/异常、颜色档位、缺口汇总、逐题演练答案清单）。唯一不能自动准备的是**用户本人的登录态**（凭据）与**浏览器扩展的安装启用**（需用户本人在设置里点一次「前往安装」）；这两项只决定 A 通道是否可用，**不决定能否回答用户**。

## 两条支路

| `delivery` | 由什么决定 | 走哪条 |
|---|---|---|
| `answer` | 用户问页面标题 / 提示异常 / 口径 | 静态页面信息速查 + `references/offline.md`，不必探测浏览器 |
| `drill` | 用户要逐题演练答案清单 / 沙箱 / 免确认 / 演练 / 说明怎么填 | `references/offline.md`，不必探测浏览器、不询问课程、不索要授权 |
| `live-run` | 用户要真实拉满 | 探测 A → B → C → D，能用 A 就走 A |

**先定 `delivery` 再探测 `channel`**：`delivery=answer/drill` 时，即使 A 通道碰巧可用，也不做真实页面操作，直接按提问范围交付；用户没要求实况采集就不要开浏览器、不要截图、不要建清单。

## Edge 扩展优先：识别、校验、安装引导（仅 A 通道）

### 1. 识别

调用 `mcp__browser__browsers_list`，在返回数组里按字段挑实例，**不要按数组顺序取第一个**：

| 判据 | Edge 扩展实例应满足 |
|---|---|
| `type` | `"extension"` |
| `family` | `"edge"`（部分版本可能缺省，则退而用 `name` 含 `Microsoft Edge`） |
| `name` | `Microsoft Edge`（实测） |
| `capabilities` | 含 `"user_tabs"` |
| `metadata` | 含 `extension_id` / `extension_version` / `profile`（实测版本 0.2.8、profile `Default`） |

实测返回（2026-11-27）：

| browser_id | name | type | family | user_tabs | 用途 |
|---|---|---|---|---|---|
| 1 | WorkBuddy Browser | `desktop` | — | ❌ 无（内置 IAB，`tab_model: multi_tab`） | 仅降级 |
| **2** | **Microsoft Edge** | **`extension`** | **`edge`** | **✅ 有** | **本技能默认通道** |

随后 `browser_info(browser_id=2)` 复核能力与标签模式，记下该 `browser_id`，**全程复用**。

### 2. 为什么实况必须走扩展

- 登录态只存在于用户自己的 Edge 里，IAB 是独立会话、不共享登录态。
- 只有带 `user_tabs` 的扩展实例才能 `user_open_tabs` → `tabs_claim` 接管用户已打开的智慧树 / 课程 / 分析页标签。
- 平台在点课程卡片、点「掌握度分析」时会 `window.open` 新标签，这些新标签只能在 `user_open_tabs` 里找到；IAB 分支需整条链路重走且用户要重新登录。
- WorkBuddy Browser Use 官方规范「未指定浏览器时优先内置浏览器」有明确例外——「需要其中的登录状态时，选择对应的扩展浏览器」。本技能实况运行恒属于该例外，且用户已明确指定偏好。

### 3. 扩展未连接时的引导（只引导，不代装；且不得阻断交付）

1. 先查 `list_installed_plugins` 里 `workbuddy-browser-use` 状态。
2. 插件已启用但 `browsers_list` 里没有 Edge 扩展实例，且**用户未声明沙箱 / 免确认、确实要实跑** → 请用户打开 WorkBuddy「设置 > 智能体 > 浏览器操控」，在 Microsoft Edge 一栏点「**前往安装**」，安装并启用 **WorkBuddy Edge 扩展程序**，保持 Edge 打开后回复「继续」重跑探测。
3. **沙箱 / 免确认 / 无法安装环境**：不做第 2 步，直接落 `channel=offline`，按用户提问范围交付；不要求用户安装、不等待回复。
4. 用户明确指定 Chrome / QQ 浏览器扩展，或明确同意在 IAB 里本人重新登录 → 按降级口径继续，`route=degraded`，并在汇报里写明影响（需重新登录、不能接管已开标签、坐标基准变化）。
5. 不代点安装器、不改系统设置、不装系统级软件、不要求管理员权限。

### 4. 运行时断开的处理

遇 `extension_disconnected` / `browser_not_found` / `stale_tab` / `host_restarted`：从 `browsers_list` 重新确认**同一个 Edge 实例**，重新 `user_open_tabs` + `tabs_claim`，不复用旧 `tab_id`、不跨实例混用；连续两次无法恢复 → 实况循环停止，但**仍要按 `delivery` 交付能离线回答的部分**，不切到 IAB 继续跑同一批标签。

## 四层条件（只影响 `channel`，不阻塞交付）

### 实况层（A 通道条件，缺一即降到 B，不 `block`）

| id | 条件 | 检查方式 | 缺失时 |
|---|---|---|---|
| `browser_tools` | `mcp__browser__browsers_list` schema 可加载 | `ToolSearch` 精确加载该工具名 | 记「不可用」，转桌面层；**不引导安装、不追问** |
| `browser_instance` | `browsers_list` 返回 ≥1 个 `type=extension` 且含 `user_tabs` 的已登录实例 | `DeferExecuteTool` 调用 | 转桌面层 |
| `core_tools` | `user_open_tabs` / `tabs_claim` / `tab_screenshot` / `cua_click` 可加载 | `ToolSearch` 批量加载 | 缺哪个找等价工具（见 `references/tooling.md`）；全缺转桌面层 |
| `skill_files` | `SKILL.md` + 6 份 `references/*.md` + `scripts/mastery.py` / `cleanup_screenshots.py` / `lint.py` 齐全 | 文件读取工具列目录 | 仅影响实况运行；离线交付只依赖 `offline.md` / `site-map.md` / `answering.md` |
| `ledger_dir` | 台账目录可写 | 尝试创建 `<CWD>/.workbuddy/mastery/` 并写探针 | 自动 `mkdir` + 写探针；不可写则用对话内表格维护待办 |

### 桌面层（B 通道条件）

| id | 条件 | 缺失时 |
|---|---|---|
| `desktop_fallback` | `computer-use` / `desktop-control` 技能可用 | 转只读层；`search_and_install_skills` 只作为可选的一次性尝试，沙箱无法安装时直接落 D |

### 只读层（C 通道条件）

| id | 条件 | 用途 |
|---|---|---|
| `web_lookup` | `WebFetch` / `WebSearch` 可用 | 读公开页面信息、核对权威资料 |
| `history` | `knowledge_search` / `conversation_search` / `Read` 台账 JSON 可用 | 复用历史台账与实跑记录 |
| `user_material` | 用户贴出的题面 / 截图 / 答案清单 | 直接作为逐题推演输入 |

### 离线层（D 通道，无条件可用）

`references/site-map.md` 的实测记录、`references/offline.md` 的交付模板始终可读。`channel=offline` 时 `route=offline`，**继续交付，不停止**。

### 路径层（只影响 `route`，不影响 `channel` 是否可用）

| id | 条件 | 不满足时 |
|---|---|---|
| `edge_extension` | **Edge 扩展实例已连接**（`type=extension` + `family=edge` + `user_tabs`） | 按第 3 节引导；沙箱 / 免确认直接落 D；用户明确降级则 `route=degraded` |
| `logged_in` | 在所选 Edge 扩展实例里首页右上出现用户名，或「我的学堂」链接可见 | `route=scene`：请用户本人登录，不代输凭据；**同时仍交付离线可答部分** |
| `course_reachable` | 能进入目标课程学习页 | 走完整导航链路重新定位；仍不行按 D 通道交付 |
| `analysis_reachable` | 菜单 → 掌握度分析可打开 | 重走第 3–4 步；或用台账里的直达 URL |
| `resolution` | 视口 / 缩放与 1699×888 基准一致 | 不换算，**每屏截图现量坐标**（换浏览器通道时尤其如此） |
| `scroll_channel` | `cua_scroll` 可用 | 降级 `dom_cua_scroll` → 键盘 `PageDown` → `tab_reload` 后重试 |
| `python` | Python 可用（台账脚本） | 自动降级：对话内表格维护待办，不阻塞 |

## 决策表

| `channel` | `route` | 下一步 |
|---|---|---|
| `live` | `direct` | 实况条件 + 现场齐备 + 走 Edge 扩展优先通道 → 直接使用技能，进工作流程第 0 步 |
| `live` / `assisted` | `degraded` | 必需能力有缺口或已降级到 IAB / 其他扩展 → 按降级口径继续，汇报里写明影响 |
| `live` | `scene` | 只差用户本人登录 → 讲清「准备现场」；**同时按 `delivery` 交付离线可答部分** |
| `readonly` / `offline` | `offline` | **不停止、不索要课程 / 授权 / 安装 / 回复「继续」** → 直接进 SKILL.md「0.5 离线演练交付」 |
| 任意 | `redline` | 仅真实页面出现作业考试 / 计分 / 监考 / 人脸 / 验证码 → 零点击停止并报告所见 |

**不再存在 `ready=false / route=block` 这一行**：环境缺失只改变通道，不改变「必须交付」这一事实。

## 阶段 P 执行清单

1. 解析 `<SKILL_DIR>` 与 `<CWD>`，不假设工作目录就是技能目录。
2. **先读用户指令定 `delivery`**（answer / drill / live-run）。`delivery=answer/drill` 时可直接跳到离线交付，不必探测浏览器。
3. `delivery=live-run` 才做探测：`ToolSearch` 加载 `mcp__browser__browsers_list` / `mcp__browser__browser_info` 等核心工具 schema；**加载不到就记「不可用」，只探测一次，不反复重试**。
4. `browsers_list` → 按「Edge 扩展优先」字段挑实例（**不取第一个**）→ `browser_info` 复核 `user_tabs` → 记录 `browser_id`。
5. 在该 `browser_id` 上 `user_open_tabs` 找已登录的智慧树标签；`tabs_claim` 接管；`tab_screenshot` + `dom_cua_get_visible_dom` 确认首页右上出现用户名。确认台账目录可写（自动创建）。
6. **仅实况通道**：首次截图之前跑 `python "<SKILL_DIR>/scripts/cleanup_screenshots.py" begin --file <清单> --json`，记下返回的清单路径。C/D 通道跳过 begin / finish。
7. 汇总 `channel` / `route` / `degraded[]` / `browser_channel`。**仅在 `delivery=live-run` 或用户主动问环境时**向用户汇报阶段 P（含实例名称 / 类型 / `browser_id`、是否 Edge 扩展优先通道、台账路径）；其余情况不主动汇报。
8. `channel=readonly/offline` 的等价收尾检查：`Glob` 一次 `~/.workbuddy/blobs` 确认本次没有新增图片；无新增即可结束，不必写进回复。

**不跳过 `check`，但只探测一次**：即使上次跑过、台账已存在也重新探测（插件可能被卸载、扩展可能断开），但探测失败不得反复追问用户。

## 准备现场（仅 `route=scene` / 用户主动要实况运行且差一步就绪时需要用户本人做）

1. 若 Edge 扩展未连接：按第 3 节，在「设置 > 智能体 > 浏览器操控」安装并启用 **WorkBuddy Edge 扩展程序**，保持 Edge 打开。
2. 在受控标签里打开 `https://www.zhihuishu.com/` 并**本人登录**（账号 / 短信验证码 / 微信扫码均可，助手不代输、不回显、不保存）。
3. 浏览器窗口**最大化**、缩放保持 **100%**，不要最小化或遮挡。
4. 回复「继续」，助手重跑探测转 `direct`。

汇报时明确说「环境已就绪，只差您本人登录」或「只差您启用 Edge 扩展」，不要说成「环境有问题」；**但这句话不能替代用户本次问的页面信息或答案清单**。沙箱 / 免确认场景下不出示这段引导。

## 准备与收尾的边界（分级）

- 只写本技能自有目录与工作区 `.workbuddy/mastery/`；不改系统 PATH、不装系统级软件、不需要管理员权限；不删除任何**运行前已存在**的文件。
- **截图清理只走 `scripts/cleanup_screenshots.py`**：仅实况通道 `begin` 建清单、收尾 `finish` 只删白名单目录内本次运行新增的图片，逐文件删除；禁止整目录清空 `~/.workbuddy/blobs`、禁止通配符批量删除、禁止删台账 / 清单之外的文件、禁止扫描用户剪贴板图片。C/D 通道无截图产物，跳过 begin / finish，也不汇报清理结果。
- 不代替用户登录、不点击 UAC / 安装器 / 密码框、不未经用户明确同意执行全局安装；**不代替用户安装 / 启用浏览器扩展**。
- **不因为「内置 IAB 可用」就默认选它**：实况通道以登录态与 `user_tabs` 能力为准。
- **不因为「A/B 通道不可用」就停止**：这是 v1.3.x 的关键例外，沙箱 / 演练环境落 C/D 继续交付。
- 环境类失败一律「先自动修一次、修不了就降级」，不得反复追问用户、不得把决策权推回用户。
- 方案 B 的所有绝对路径在运行时动态解析（`expanduser("~")` / `<CWD>` / `<SKILL_DIR>`），**禁止硬编码用户名、盘符或版本目录名**；本技能不设环境自检脚本、也不生成环境文件。

## 方案 B：浏览器工具不可用时的桌面接管

1. 对方案 B 的条件执行同一轮「检查 → 准备 → 复检」，只做一次。
2. 缺失的 `computer-use` / `desktop-control` 技能可用 `search_and_install_skills` 尝试一次；沙箱无法安装不代表任务失败。
3. 用 `computer-use`（截图 + 坐标点击）或 `desktop-control`（无障碍树 + `ref`）接管用户已打开的浏览器窗口。
4. 每个动作前必须截图取坐标，动作后立即再次截图验证；禁止连续盲操作。
5. 该分支占用真实鼠标键盘，开始前提示用户不要同时使用鼠标。
6. **方案 A 与方案 B 都不可用 → 落 C/D 通道继续交付，不停止、不输出阻塞项清单**。「不改用 HTTP 抓取、命令行浏览器或任何绕过手段」只禁止**绕过登录态操作真实平台 / 写入数据 / 代答计分考核**，不禁止 C/D 通道用 `WebFetch` / `WebSearch` 查公开信息、用 `Read` 读本地台账、基于用户题面做离线推演。

## 方案 D：离线演练交付（工具全缺时的主路径）

适用：`mcp__browser__*` schema 全部加载不到、连接器列表为空、内置 IAB 无实例、方案 B 桌面层未安装、插件无法安装（沙箱典型）。

1. 不询问课程、不索要提交授权、不要求安装扩展、不要求回复「继续」。
2. 直接按用户提问范围取 `references/offline.md` 的模板：页面标题与提示/异常、5 档颜色与跳过 / 待补判定、缺口双口径汇总、逐题演练答案清单、「看答案时怎么填」。
3. 每项标注「实测已知（2026-11-27 实跑记录）/ 推断 / 本次未采集」；没采到的热力图数值如实写「本次未采集」，不编造本次实测。
4. 演练不触发真红线（不调题库、不读隐藏答案、不代答计分考核），也**不因环境缺失停工**。

## 常见故障

| 现象 | 处理 |
|---|---|
| `browsers_list` / `user_open_tabs` / `tabs_claim` / `cua_click` schema 全部加载不到、连接器列表为空 | **正常沙箱场景**，落 `channel=offline`，直接按用户提问范围交付；不引导安装、不追问 |
| `browsers_list` 返回空 / 只有 IAB（`type=desktop`） | 实况需 Edge 扩展连接；用户未要求实况或已声明免确认 → 落 C/D；用户要实跑且非沙箱 → 按第 3 节引导安装启用，不默认用 IAB |
| `user_open_tabs` 找不到智慧树标签 | 先确认选的是 Edge 扩展实例（含 `user_tabs`）；再 `tabs_new` + `tab_goto` 打开官网；登录态在另一个浏览器实例则改查该实例 |
| 拿第一个 `browser_id` 后 `user_open_tabs` 无已登录标签 | 误取内置 IAB；按字段重挑 Edge 扩展实例并重新 `tabs_claim` |
| `extension_disconnected` / `host_restarted` / `browser_not_found` | 从 `browsers_list` 重新确认同一 Edge 实例，不复用旧 `tab_id`、不跨实例混用；恢复不了仍要交付离线部分 |
| IAB 降级分支出现登录页 | IAB 不共享登录态；请用户本人在 IAB 登录，或落 C/D，不自动重登 |
| `tabs_claim` 后 `tabs_list` 里状态变 `selected:false` | 正常，用 `tab_focus` 或重新 `tabs_claim`；每轮动作前确认 |
| 截图超时 | `tab_reload` 后恢复；期间标题 / URL 仍可读 |
| 滚动超时 | `dom_cua_scroll` / 键盘 `PageDown` / reload 后重试 |
| 课程卡片点了没反应 | 首次点击常不生效，重试一次或合并进 `cua_execute` |
| 点课程 / 掌握度分析后看不到新页面 | 开了新标签，`user_open_tabs` → `tabs_claim` |
| 换了电脑 / 用户名变了 | 重新探测，台账与路径重新解析，禁止沿用旧路径 |
| Python 不可用 | 台账降级为对话内表格；不阻塞主流程 |
| 找不到截图清单 | 实况通道漏跑 `begin`；本次不追加清理（会误删历史缓存）。C/D 通道本来就不该有清单，不算故障 |

## 隐私

阶段 P 只探测工具可用性、实例类型与能力字段、目录可写性，不读取、不记录 Cookie / Token / 账号 / 验证码 / 浏览器配置文件内容。台账只存课程名、模块 / 列、知识点标题、掌握度数值与浏览器通道标识。离线交付引用技能内实测记录时不得回显用户姓名等个人信息，必要时用「<姓名>」占位。
