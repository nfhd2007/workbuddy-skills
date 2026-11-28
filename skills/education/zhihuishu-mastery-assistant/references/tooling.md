# 浏览器工具速查与失败处理

> 所有浏览器工具通过工具检索加载 schema 后调用；**参数以 schema 为准**，本文件只是速查。除 `browsers_list` 外多数工具要求整数 `browser_id` 与 `tab_id`，来自 `browsers_list` / `user_open_tabs` / `tabs_claim` 返回值。
> **实况通道默认：WorkBuddy Edge 扩展程序**（`type=extension` / `family=edge` / `user_tabs`）。内置 IAB 不共享登录态、无 `user_tabs`，仅在用户明确同意本人重新登录时降级使用。
> **v1.3.1 口径**：本文件的实例选择、坐标点击、截图清理**全部只约束 A/B 实况通道**。`mcp__browser__*` 工具加载不到时，按「工具全缺时的替代调用链」落 C/D，不阻断交付、不引导安装、不追问用户。

## 实例识别与选择（仅 A 实况通道）

### 实测返回（2026-11-27）

`mcp__browser__browsers_list({})` 返回：

| browser_id | name | type | family | metadata | capabilities | 判定 |
|---|---|---|---|---|---|---|
| 1 | `WorkBuddy Browser` | `desktop` | — | `tab_model: multi_tab` | navigation / screenshot / cua / batch / dom_cua / visibility | 内置 IAB，**无 `user_tabs`** |
| **2** | **`Microsoft Edge`** | **`extension`** | **`edge`** | `extension_id` / `extension_version: 0.2.8` / `profile: Default` | navigation / screenshot / cua / batch / dom_cua / **`user_tabs`** | **本技能默认通道** |

### 选择规则

1. 遍历返回数组，选 **`type == "extension"` 且 `family == "edge"`（或 `name` 含 `Microsoft Edge`）且 `capabilities` 含 `"user_tabs"`** 的实例，取其 `browser_id`。
2. 用 `mcp__browser__browser_info(browser_id)` 复核能力与标签模式，确认 `user_tabs` 存在。
3. **绝不按数组顺序取第一个 `browser_id`**——实测第一个就是内置 IAB，误取后 `user_open_tabs` 里不会有用户已登录的智慧树标签，整条链路会误判为「未登录」。
4. Edge 扩展不可用时按优先级降级：`type=extension` 的其他浏览器扩展（Chrome / QQ 浏览器，需用户明确指定）→ 内置 IAB（需用户明确同意在 IAB 里本人重新登录）→ 方案 B 桌面动作层 → **C/D 只读 / 离线通道**。前三次降级在实况汇报里写明影响；C/D 通道不汇报阶段 P。
5. **全程复用同一个 `browser_id`**；`tab_id` 只在该实例内有效，不跨实例混用。遇 `stale_tab` / `browser_not_found` / `extension_disconnected` / `host_restarted`，从 `browsers_list` 重新确认同一个 Edge 实例并重新 `tabs_claim`，不复用旧标识。

### 选中后的校验清单

- [ ] `browser_info` 显示 `user_tabs` 能力；`user_open_tabs` 能列出用户已打开的标签。
- [ ] 在 `user_open_tabs` 里能找到 `zhihuishu.com` 相关标签，或 `tabs_new` 后首页右上出现用户名。
- [ ] 实况汇报中记录实例名称 / 类型 / `browser_id` / 是否为 Edge 扩展优先通道。

## 工具层探测（阶段 P，只探测一次）

1. 检索 `mcp__browser__browsers_list` 与 `mcp__browser__browser_info` 的 schema。能加载 → A 通道候选。
2. **检索不到 → 直接记「不可用」，落 C/D 通道继续交付**。仅当用户主动要实况运行、且未声明沙箱 / 免确认时，才用 `list_installed_plugins` 查 `workbuddy-browser-use` 状态并引导一次；不得反复追问、不得把「装好插件再回复继续」当作对用户提问的回答。
3. `browsers_list` 里**没有 Edge 扩展实例** → 引导用户在「设置 > 智能体 > 浏览器操控」找到 Microsoft Edge，点「**前往安装**」安装并启用 **WorkBuddy Edge 扩展程序**，保持 Edge 打开后重跑阶段 P（仅限可安装、用户要实跑的场景）。内置浏览器不可用时**不要求**安装外部扩展；但内置浏览器**不是**本技能的目标通道。
4. `browsers_list` 完全为空且插件无法启用 → 自动降级方案 B（桌面动作层）；方案 B 也不可用 → 落 C/D，**不停止**。
5. 遇 `stale_tab` / `browser_not_found` / `extension_disconnected` / `host_restarted` → 从 `browsers_list` 重新开始，不复用旧标识。

**登录态在用户的 Edge 里** → 实况运行必须用 Edge 扩展实例的 `user_open_tabs` + `tabs_claim` 接管用户标签，内置 IAB 会话不共享登录态。

## 工具全缺时的替代调用链（C/D 通道）

当 `browsers_list` / `user_open_tabs` / `tabs_claim` / `tab_screenshot` / `cua_click` 等 schema 全部取不到、连接器列表为空时，用下面这条链路继续交付，**不停工、不绕过登录态**：

| 目的 | 替代调用 |
|---|---|
| 公开页面信息 / 权威表述核对 | `WebFetch` / `WebSearch`（只读，不登录、不写入平台） |
| 历史台账 / 实跑记录 / 过往演练答案 | `Read` 台账 JSON、`knowledge_search`、`conversation_search` |
| 用户提供的题面 / 截图 / 答案清单 | 直接作为逐题推演输入，无需任何浏览器工具 |
| 页面标题 / 提示异常 / 颜色档位模板 | `Read` `references/site-map.md` 与 `references/offline.md` |
| 收尾检查 | `Glob` 一次 `~/.workbuddy/blobs` 确认本次无新增图片；**不需要 `cleanup_screenshots.py begin` / `finish`** |
| 可选安装兜底 | `search_plugins` / `suggest_plugin_install` / `search_and_install_skills` 只尝试一次；沙箱无法安装即落 D，不要求用户操作 |

**禁止**：用命令行浏览器、CDP 服务、HTTP 直接带登录态去操作真实平台写入数据或代答计分考核。**允许**：C/D 通道的只读公开信息查询、本地台账读取与基于用户题面的离线推演。

## 会话与标签

| 工具 | 参数 | 作用 |
|---|---|---|
| `mcp__browser__browsers_list` | `{}` | 列出已连接浏览器实例及能力（**按字段选 Edge 扩展，不取第一个**） |
| `mcp__browser__browser_info` | `browser_id` | 协议、能力、限制（复核 `user_tabs`） |
| `mcp__browser__user_open_tabs` | `browser_id` | 列出**可接管的用户标签**（新开的课程页 / 分析页在这里找；仅扩展型实例支持） |
| `mcp__browser__tabs_claim` | `browser_id, tab_id` | 接管 `user_open_tabs` 返回的标签 |
| `mcp__browser__tabs_new` | `browser_id, url?` | 新建 / 获取受控标签 |
| `mcp__browser__tabs_list` | `browser_id` | 列出本会话受控标签 |
| `mcp__browser__tabs_selected` | `browser_id` | 当前选中的受控标签 |
| `mcp__browser__tabs_get` | `browser_id, tab_id` | 取单个受控标签 |
| `mcp__browser__tab_goto` | `browser_id, tab_id, url` | 导航到绝对 http(s) URL（断点续跑直达用） |
| `mcp__browser__tab_reload` | `browser_id, tab_id` | 重新加载（截图超时后恢复） |
| `mcp__browser__tab_focus` | `browser_id, tab_id` | 把真实用户标签带到前台 |
| `mcp__browser__tab_title` / `tab_url` | `browser_id, tab_id` | 读标题 / URL |
| `mcp__browser__tab_screenshot` | `browser_id, tab_id, format?, full_page?, quality?, clip?` | 截图，默认 jpeg；建议 `format="png"` |
| `mcp__browser__tabs_finalize` | `browser_id, keep?` | 按 provider 策略结束受控标签（**本技能收尾默认不调用**；如确需调用必须带 `keep` 保留用户标签） |

`tab_back` / `tab_forward` / `tabs_close` 名称已知但参数未固化，调用前先加载 schema。

## DOM 快照与动作

| 工具 | 参数 | 作用 |
|---|---|---|
| `mcp__browser__dom_cua_get_visible_dom` | `browser_id, tab_id` | 可见 DOM 快照，含快照作用域内 `node_id` |
| `mcp__browser__dom_cua_click` | `browser_id, tab_id, node_id` | 点最近一次快照中的节点（**仅首页「我的学堂」可用**） |
| `mcp__browser__dom_cua_type` | `browser_id, tab_id, text` | 向焦点元素输入文本 |
| `mcp__browser__dom_cua_keypress` | `browser_id, tab_id, keys` | 在焦点元素发送按键 |
| `mcp__browser__dom_cua_scroll` | `browser_id, tab_id, x, y, node_id?` | 滚动（`cua_scroll` 超时时的替代） |
| `mcp__browser__cua_click` | `browser_id, tab_id, x, y, button?, keypress?` | 按 CSS 像素坐标点击（**本技能实况主力**） |
| `mcp__browser__cua_scroll` | `browser_id, tab_id, x, y, scroll_x, scroll_y` | 按坐标滚动（正数向下） |
| `mcp__browser__cua_execute` | `browser_id, tab_id, actions[]` | 顺序执行 1–100 个坐标动作 / 截图 |

`cua_execute` 的 `actions[]` 元素按 `type` 区分：

- `click` / `double_click` / `move` → 需要 `x, y`
- `drag` → 需要 `path[]`（2–256 个 `{x,y}`）
- `scroll` → 需要 `x, y, scroll_x, scroll_y`
- `keypress` → 需要 `keys`（字符串或数组，≤8），如 `"PageDown"` / `"End"`
- `type` → 需要 `text`
- `screenshot` → 可带 `clip{x,y,width,height}` / `format` / `full_page` / `quality`

坐标类动作可附加 `keypress`，点击类可指定 `button`。

## 能力边界（必须记住）

1. **不能执行 JavaScript**：无 `evaluate` / `execute_script` / 注入。不能读隐藏答案、不能调接口、不能改页面状态。
2. **没有 wait / sleep 工具**：等待靠「动作后再截一张图」实现，不要高频轮询给页面施压。
3. **`node_id` 生命周期**：只在生成它的那次快照内有效；界面变化、导航、重新快照后旧 id 作废。本技能除首页外基本用不上。
4. **截图必须真的看**：`tab_screenshot` 返回图像内容，要实际查看，不能只看尺寸就宣称已确认。
5. **不要猜参数**：未在上表固化的工具先加载 schema。
6. **`full_page` 实测不可靠**：返回仍是单屏视口图，且可能与当前视口坐标不一致；扫描热力图用「滚动 + 普通截图」，不要用 full_page 量坐标。
7. **与 WorkBuddy Browser Use 官方通用原则的偏差**：官方建议「未指定浏览器时优先内置 IAB」「优先读 DOM 点击」。本技能实况运行按官方例外「需要登录态时选择扩展浏览器」覆盖为**默认 Edge 扩展**；且实测除首页外 DOM 快照只有 0–1 个节点，因此以**截图 + 坐标**为主。加载官方 browser-use 技能后不要据此改回 IAB / DOM 优先。
8. **「只使用 `mcp__browser__*` 工具」仅限 A/B 实况通道**：不使用命令行浏览器、CDP 服务或其他带登录态的浏览器控制方式。C/D 通道走「工具全缺时的替代调用链」，只读与离线推演不受此限。

## 本链路实测的失败处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `mcp__browser__*` 工具 schema 全部加载不到 / 连接器列表为空 | 沙箱或未启用插件 | **正常场景**，落 `channel=offline` 按提问范围交付；不引导安装、不追问、不停止 |
| `browsers_list` 只有 `WorkBuddy Browser` / 没有 Edge 扩展 | 扩展未安装或未连接 | 用户要实跑且可安装 → 引导「设置 > 智能体 > 浏览器操控 > Microsoft Edge > 前往安装」并启用；否则落 C/D，不默认用 IAB |
| 取了第一个 `browser_id`，`user_open_tabs` 找不到已登录标签 | 误取内置 IAB（无 `user_tabs`） | 按 `type=extension` + `family=edge` + `user_tabs` 重挑实例并重新 `tabs_claim` |
| `extension_disconnected` / `host_restarted` | 扩展宿主重启 | 从 `browsers_list` 重新确认同一 Edge 实例，不复用旧 `tab_id`，不跨实例混用；恢复不了仍交付离线部分 |
| 点课程卡片后「页面没变」 | 首次点击常只触发图片懒加载 | 重试一次；或把「点击 + 截图」放进 `cua_execute` |
| 点课程 / 掌握度分析后出现新标签 | 平台用 `window.open` | `user_open_tabs` 找新标签 → `tabs_claim`；**不要连点**，实测连点开出 2 个重复标签 |
| 受控状态周期性丢失 | 登录 / reload / claim 其他标签后 | 每轮动作前 `tabs_list` 确认，不在则重新 `user_open_tabs` + `tabs_claim` |
| `tab_screenshot` 报 `provider invocation timed out` | provider 偶发 | `tab_reload` 后恢复；期间标题与 URL 仍可读，页面没崩 |
| `cua_scroll` 连续报超时 | provider 滚动通道不稳 | 改 `dom_cua_scroll` → 键盘 `PageDown` / `End` → reload 后重试；**每次滚动后截图确认位置** |
| `cua_execute` 内嵌截图是半透明中间态 | 浮层淡入 / 淡出动画 | 动作后**单独再 `tab_screenshot` 一次**再判定 |
| 点「去提升」后「浮层消失、页面没变」 | 自测题浮层异步加载 | 再截一张图，不要判定失败、不要连点 |
| 点「提交」后仍是题目 | 提交异步 / 结果页加载 | 再截一张图，不要连点「提交」 |
| URL 与画面不一致（如 `chooseOrgan` 显示课程中心） | SPA 路由滞后 | **以截图为准**，不要立刻读 URL 下结论 |
| 浮层遮住相邻格子 | 白色浮层覆盖约 250×190px | 点远处空白或换一列再点；不要点在浮层内部 |
| 顶部大「去提升」无反应 | 实测点两次无变化 | 不依赖它，主路径是热力图格子 |
| 截图里出现登录页 / 「请重新登录」 | 会话失效 | 停止实况，提示用户本人重新登录，不自动重登；仍按 `delivery` 交付离线可答部分 |

## 坐标系

- `cua_click` 用 **CSS 像素**，截图左上角为 (0,0)；实测基准 1699×888，来自 **Edge 扩展接管的用户 Edge 窗口**。截图上量到的坐标直接点，不做换算。
- 前提：窗口最大化、贴 (0,0)、不被遮挡、缩放 100%。窗口移动后全部坐标作废，必须重新截图。
- **换浏览器通道（尤其是降级到 IAB）时视口可能不同，所有基准坐标一律作废，重新现量。**
- 本技能不混用桌面截图工具（避免物理像素 / 逻辑像素不一致）。

## 方案 B：桌面动作层（自动降级，仍非交付前提）

当 `mcp__browser` 完全不可用时，按 `references/environment.md` 准备 `computer-use` / `desktop-control`，改用「截图 + 坐标点击」接管用户已打开的浏览器窗口：

- 每个动作前必须截图取坐标，动作后立即再次截图验证；禁止连续盲操作、禁止凭记忆坐标点击。
- 该分支占用真实鼠标键盘，开始前提示用户不要同时使用鼠标。
- 所有绝对路径在运行时动态解析：`~/.workbuddy/blobs` 用 `expanduser("~")`、台账用 `<CWD>`、脚本用 `<SKILL_DIR>`（见 `scripts/cleanup_screenshots.py` 的白名单目录解析），**禁止硬编码用户名、盘符或版本目录名**。方案 B 不引入额外的环境探测脚本，`scripts/` 下只有 `cleanup_screenshots.py` / `mastery.py` / `lint.py` 三个内置脚本。
- **方案 A 与方案 B 都不可用 → 落 C/D 通道继续交付，不停止、不输出阻塞项清单**；「不改用 HTTP 抓取、命令行浏览器或任何绕过手段」只禁止绕过登录态操作真实平台 / 写入数据 / 代答计分考核。

## 截图落盘与收尾自动清理（仅 A/B 实况通道）

`tab_screenshot` / `cua_execute` 内嵌 screenshot 返回的是 MCP 图像内容，WorkBuddy 平台会把它落盘到 `~/.workbuddy/blobs/<2 字符前缀>/<sha>.png`。该目录是**全局共享缓存**，其它会话 / 技能的图片也在里面，文件名是内容哈希，看不出属于哪次运行；一次完整掌握度运行可产生几十到上百张。

- **禁止**整目录删除 / `rm -rf` / `shutil.rmtree` / 通配符批量删除 / 连带清空 `~/.workbuddy/clipboard-images`（里面多为用户自己粘贴的图片）。
- 统一走 `scripts/cleanup_screenshots.py`（纯标准库）：`begin` 记录起始时间与白名单目录（默认仅 `~/.workbuddy/blobs`，路径动态解析）、`add` 登记截图工具返回的落盘路径或 `file://` URI、`list` 只读复核、`finish` 逐文件删除「本次运行新增」的图片并在成功后删除清单。
- **`begin` 仅在实况通道首次截图之前执行；`finish` 仅在实况通道且确实产生过截图时执行**——包括 `ALL_DONE`、达到上限、用户叫停、dry-run、红线特征、`SESSION_EXPIRED`、Edge 扩展断开。C/D 通道无截图产物，跳过 begin / finish，也不汇报清理结果；等价收尾检查是 `Glob` 一次 `~/.workbuddy/blobs`。详见 SKILL.md「截图缓存与清理策略」与工作流程第 9 步。
- **清理不优先于汇报**：先按用户提问范围把答案交齐，清理结果只是可省略的末尾补充项。
- `finish` 前先 `list`：若待删数量明显超过本次截图次数（或出现与掌握度页面无关的图片），改用 `finish --keep` 只列不删、保留清单并报告，避免误删同一时段其它会话的图片。
- `--max-delete` 默认 500，超限脚本会拒绝删除；每 10 个一组删除并校验，失败即停不盲删。
- 删除的是本地缓存副本，不影响平台服务端数据与台账；历史对话里已渲染的缩略图可能不再显示。需要复盘就用 `finish --keep`。

## 隐私

DOM 快照与截图可能包含姓名、课程与学习数据。不要把快照、截图、台账内容写进公开日志或对外传输；台账默认只存课程名、模块 / 列、知识点标题、掌握度数值与浏览器通道标识，不存账号、Cookie、Token。**运行结束自动清理本次截图缓存也是隐私保护的一环**：含个人学习数据的页面截图不应长期留在 `~/.workbuddy/blobs` 里，但清理必须按上节的白名单 + 逐文件方式进行，不能扩大到其它会话的图片。C/D 通道不产生截图，因此没有清理义务。
