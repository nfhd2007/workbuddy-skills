# 工具参数速查（课程助手通用）

所有浏览器工具通过工具检索加载 schema 后调用；参数以 schema 为准。除 `browsers_list` 外，工具都要求整数 `browser_id`，多数还要求整数 `tab_id`，二者来自 `browsers_list` / `tabs_list` / `tabs_claim` 的返回值。

> 运行前先执行 `scripts/preflight.py check --json` 完成本机体检，并按下节做工具层探测。完整流程见 `references/environment.md`；本文件只负责工具参数与路径解析。

## 工具层探测（每次运行前必做）

1. 检索 `mcp__browser__browsers_list` 的 schema；能加载即代表 Browser Use 插件已连接、方案 A 可用。
2. 检索不到 → `list_installed_plugins` 查 `workbuddy-browser-use` 状态，引导用户在「设置 > 智能体 > 浏览器操控」启用。**内置浏览器（IAB）无需任何扩展**；仅复用外部 Chrome / Edge / QQ 浏览器登录态时才需安装扩展。
3. 仍不可用 → 按 SKILL.md 第 -2 步**自动降级方案 B**，并对方案 B 的条件跑一轮 `check → prepare → agent_actions`。
4. 遇到 `stale_tab` / `browser_not_found` / `extension_disconnected` / `host_restarted` → 从 `browsers_list` 重新开始，不复用旧标识。
5. 工具名与参数一律以加载到的 schema 为准，下表只是速查；未固化的工具先加载 schema，不要凭记忆猜。

## 会话与标签

| 工具 | 参数 | 作用 |
| --- | --- | --- |
| `mcp__browser__browsers_list` | `{}` | 列出已连接浏览器实例及其能力 |
| `mcp__browser__browser_info` | `browser_id` | 协议、能力、限制 |
| `mcp__browser__user_open_tabs` | `browser_id` | 列出可接管的用户标签 |
| `mcp__browser__tabs_claim` | `browser_id, tab_id` | 接管 `user_open_tabs` 返回的标签 |
| `mcp__browser__tabs_new` | `browser_id, url?` | 新建/获取受控标签 |
| `mcp__browser__tabs_list` | `browser_id` | 列出本会话受控标签 |
| `mcp__browser__tabs_selected` | `browser_id` | 当前选中的受控标签 |
| `mcp__browser__tabs_get` | `browser_id, tab_id` | 取单个受控标签 |
| `mcp__browser__tabs_finalize` | `browser_id, keep?` | 按 provider 策略结束受控标签；`keep` 元素含 `tab_id` 与 `status`（`deliverable` / `handoff`） |
| `mcp__browser__tab_goto` | `browser_id, tab_id, url` | 导航到绝对 http(s) URL |
| `mcp__browser__tab_reload` | `browser_id, tab_id` | 重新加载 |
| `mcp__browser__tab_focus` | `browser_id, tab_id` | 把真实用户标签带到前台 |
| `mcp__browser__tab_title` | `browser_id, tab_id` | 读标题 |
| `mcp__browser__tab_url` | `browser_id, tab_id` | 读当前 URL |
| `mcp__browser__tab_screenshot` | `browser_id, tab_id, format?, full_page?, quality?, clip?` | 截图，默认 jpeg |

`tab_back` / `tab_forward` / `tabs_close` 等名称已知但参数未在此固化，**调用前先加载 schema**。

## DOM 快照与动作

| 工具 | 参数 | 作用 |
| --- | --- | --- |
| `mcp__browser__dom_cua_get_visible_dom` | `browser_id, tab_id` | 返回过滤后的可见 DOM 快照，含快照作用域内的 `node_id` |
| `mcp__browser__dom_cua_click` | `browser_id, tab_id, node_id` | 点击最近一次快照中的节点 |
| `mcp__browser__dom_cua_double_click` | `browser_id, tab_id, node_id` | 双击节点 |
| `mcp__browser__dom_cua_type` | `browser_id, tab_id, text` | 向焦点元素输入文本 |
| `mcp__browser__dom_cua_keypress` | `browser_id, tab_id, keys` | 在焦点元素发送按键（字符串或数组，≤8） |
| `mcp__browser__dom_cua_scroll` | `browser_id, tab_id, x, y, node_id?` | 在视口中心或某节点滚动 |
| `mcp__browser__cua_click` | `browser_id, tab_id, x, y, button?, keypress?` | 按 CSS 像素坐标点击 |
| `mcp__browser__cua_keypress` | `browser_id, tab_id, keys` | 在受控标签发送按键 |
| `mcp__browser__cua_scroll` | `browser_id, tab_id, x, y, scroll_x, scroll_y, keypress?` | 按坐标滚动 |
| `mcp__browser__cua_execute` | `browser_id, tab_id, actions[]` | 顺序执行坐标动作序列（1–100 个） |

`cua_execute` 的 `actions[]` 元素按 `type` 区分：

- `click` / `double_click` / `move` → 需要 `x, y`（`move` 可带 `keys`）
- `drag` → 需要 `path[]`（2–256 个 `{x, y}` 点）
- `scroll` → 需要 `x, y, scroll_x, scroll_y`
- `keypress` → 需要 `keys`（字符串或数组，≤8）
- `type` → 需要 `text`（≤1000000 字符）
- `screenshot` → 可带 `clip{x,y,width,height}` / `format` / `full_page` / `quality`

坐标类动作可附加 `keypress`，点击类可指定 `button`（`left` / `middle` / `right` 或 1/2/3）。

## 能力边界（必须记住）

1. **没有执行 JavaScript 的能力**：无 `evaluate`、无 `execute_script`、无注入。不能读 `video.currentTime` / `ended` / `muted`，不能用 JS 静音、快进或发心跳。
2. **没有 wait / sleep 工具**：等待靠循环节奏控制，不要高频轮询给页面施压。
3. **`node_id` 生命周期**：只在生成它的那次快照内有效；界面变化、导航、重新快照后旧 id 作废。
4. **截图必须真的看**：`tab_screenshot` 返回图像内容，要实际查看，不能只看尺寸就宣称已确认。
5. **不要猜参数**：未在上表固化的工具，先加载 schema。

## 状态判定可用的信号

- 可见 DOM 文案：课程标题、小节序号、`已完成 / 未完成 / 学习进度 / 观看完成 / 下一节 / 继续学习 / 请重新登录 / 验证码 / 测验 / 考试`
- 按钮的可用/禁用状态（快照中的属性）
- 截图画面：播放器结束态、弹窗、登录页

`references/site-notes.md` 记录该站点实际文案；未填充时只认明确字样，其余归 `UNKNOWN`。

## 桌面备用分支（方案 B）：路径动态解析

**所有路径禁止硬编码**（不要出现具体用户名、盘符或版本目录名）。从 `preflight.py prepare --json` 返回的 `env_file` 指向的 `env-<技能名>.json` 中读取 `paths`，或随时重新解析：

```bash
python "<SKILL_DIR>/scripts/preflight.py" paths --json --workspace "<CWD>"
```

关键字段：`paths.computer_use_skill` / `paths.desktop_control_skill` / `paths.powershell` / `paths.npm` / `paths.npx` / `paths.agent_desktop` / `paths.browsers`。**换电脑、换用户名、技能重装或升级后都必须重新解析**，不得沿用任何旧路径。

- **`computer-use`**（仅 Windows）：调用 `<paths.computer_use_skill>/scripts/computer-use.ps1 -Op <op>`，解释器必须用 Windows PowerShell 5.1（`<paths.powershell>`，**不是 pwsh 7**）；JSON **必须通过 stdin 管道**传入，Windows 路径反斜杠在 JSON 中要双写。标准流程 `info → screenshot → 确定坐标 → 单个动作 → screenshot 验证`。
- **`desktop-control`**：`agent-desktop` CLI，缺失时 `npm install -g agent-desktop`（用户明确同意后可用 `prepare --allow-install` 自动安装），装完执行 `agent-desktop status` 验证；`ref` 必须带快照 ID（如 `@s8f3k2p9:e12`），PowerShell 中 `@` 需加引号；默认无头模式。技能目录取 `<paths.desktop_control_skill>`。
- 缺失的桌面技能由 WorkBuddy 用 `search_and_install_skills` 自动安装，安装后重新 `check --json` 确认。

两者都遵循「先看再动、一次一个动作、动作后验证」。桌面分支涉及真实鼠标键盘，开始前提示用户不要同时使用鼠标；系统级弹窗、密码框、不可撤销按钮一律不自行点击。条件清单、安装命令与报错处理见 `references/environment.md` 第七节与第十一节。

## 隐私

DOM 快照与截图可能包含课程页上的个人信息。不要把快照、截图、台账内容写进公开日志或对外传输；台账默认只存小节标题与状态，不存账号、Cookie、Token。`env-<技能名>.json` 只保存路径与环境信息，同样不含任何凭据或页面内容。
