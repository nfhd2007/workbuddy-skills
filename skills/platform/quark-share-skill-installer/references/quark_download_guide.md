# 夸克分享技能安装器 · 分享链接下载指南

本文件是「夸克分享技能安装器」（技术标识 `quark-share-skill-installer`）的参考文档，供执行阶段 1 时按需加载。目标是**把分享里的 .zip 真正落到本机磁盘**，而不是转存到自己的网盘。

## 1. 链接形态

| 形态 | 示例 | 说明 |
| --- | --- | --- |
| 基础分享 | `https://pan.quark.cn/s/1a2b3c4d5e6f` | 末段是 `pwd_id` |
| 带提取码 | `https://pan.quark.cn/s/1a2b3c4d5e6f?pwd=ab12` | 也可能由分享者单独给出 4 位提取码 |
| 带目录定位 | `https://pan.quark.cn/s/<pwd_id>#/list/share/<token>-<fid>` | 直接指向分享内的某个子目录 |
| 纯 pwd_id | `1a2b3c4d5e6f` | 脚本也接受裸 ID |
| 短链 / 口令 | 「复制链接并打开夸克」的一段文字 | 从文字里抠出 `pan.quark.cn/s/...` 部分 |

处理要点：

- `quark_share_download.py` 用正则提取 `pwd_id` 与 `?pwd=`，会忽略 `#` 后的 fragment，不会把查询串吞进 ID。
- 提取码与 `pwd_id` 不是一回事：前者是访问口令，后者是分享 ID。
- 分享可能是**单个文件**，也可能是**文件夹**。脚本会递归列目录（深度 3 / 上限 500 条）找 `.zip`；多个 zip 时会拒绝猜测并列出候选，用 `--keyword` 或 `--fid` 指定（注意分卷包 `xxx.zip.001` 不在处理范围）。

## 2. 四条取文件途径

| 途径 | 适用 | 优点 | 代价 |
| --- | --- | --- | --- |
| **A. 浏览器扩展取包（v1.4.0 默认）** | 有可接管的浏览器窗口（用户自己的 Edge / Chrome 最佳） | 用浏览器自带登录态，不需要 Cookie；不写用户网盘；不接管鼠标键盘；下载走原生流程落到标准下载目录 | 依赖浏览器已运行且扩展可接管；浏览器不返回下载结果，落点必须扫盘确认 |
| **D. 手动下载（兜底）** | 扩展接不了窗口、或点了下载没有文件落盘 | 只需 Python + 脚本 + 目录，全新电脑也能用 | 需要用户点几下 |
| **B. 桌面操控（legacy，`--route gui`）** | 页面强制拉起 PC 客户端、浏览器点不到系统弹窗 | 能操作系统级对话框 | 接管鼠标键盘、按坐标猜位置、稳定性差 |
| **C. 转存 + 直链 API（legacy，`--route api`）** | 有有效 Cookie、需无人值守、且同意向自己网盘写入 | 全程脚本、支持提取码与目录递归 | 依赖 Cookie；会写用户网盘并消耗转存次数；整链未端到端验证 |

默认 A，A 不可用退 D；B/C 只在用户明确要求时用 `--route` 强制指定，不再自动选用。A 的分步见第 3 节，D 见第 4 节，B/C 见第 5–7 节。

## 3. 途径 A · 浏览器扩展取包（默认）

用 WorkBuddy 浏览器扩展接管**用户已登录的浏览器窗口**，在分享页点该文件行的「下载」图标。整个过程不碰 Cookie、不写用户网盘。

### 前置条件

- 浏览器**已在运行且有窗口**。扩展通过 native host 接管标签页；浏览器只有后台进程时，`user_open_tabs` 会返回 `no current window`。
- 优先选用户自己的 Edge / Chrome（`type=extension`、带 `user_tabs`）：登录态现成，通常连提取码都省了。

### 分步

1. **列浏览器**：`browsers_list`，取 `type="extension"` 且 `capabilities` 含 `user_tabs` 的那一项。**不要选内置浏览器**（`type="desktop"`），原因见本节末的实测对比。
2. **拿标签页**：
   - 已有分享页 → `user_open_tabs` 找到 → `tabs_claim` 接管；
   - 没有 → `tabs_new` 打开分享链接。
   - 若返回 `no current window`：请用户自己打开浏览器，再重试。**不要擅自启动用户的浏览器**。
3. **看页面**：`tab_screenshot`。三种情况分别处理：
   - 提取码输入框 → 填码（链接带 `?pwd=` 时通常已自动带上），点「确定 / 提取文件」；
   - 登录墙或会员弹窗挡住列表 → 先关弹窗；确需登录则交给用户本人（红线 15）；
   - 文件列表已出现 `.zip` → 继续。
4. **先记时间戳**：`date +%s`（PowerShell 用 `[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()`），保存这个整数，第 6 步原样传给 `--since`。**不要加 `@` 前缀**。
5. **点下载图标**：
   - 图标**只在鼠标悬停文件行时才出现**。先 `cua_move` 到行内（例如 `(x=文件名列, y=行中心)`），再 `tab_screenshot` 定位图标位置（一般在文件名与「大小」列之间），最后 `cua_click` 点图标本体。
   - **校验点击是否生效**：对比前后截图。若只有该行被选中、勾选框翻转，说明点在行上了——图标要往右再调几像素重试。
   - **绝不点「转存」「保存到我的网盘」「打开客户端」**：那是写用户账号，不是下载（红线 14）。
6. **扫盘确认落点**（必须，不能省）：
   ```bash
   "<PY路径>" "<SKILL_DIR>/scripts/find_quark_zip.py" \
     --dir "<用户下载目录>" --since <第4步的整数> --wait 15 --json
   ```
   浏览器不返回下载结果，也不暴露保存路径；重复下载会生成 `xxx (1).zip`，脚本按最新取，不按文件名匹配。
7. **判失败**：30 秒内没有新文件，或 `ok=false` → 转第 4 节手动下载。不要反复重点下载图标。

### 实测对比（2026-11-24，同一分享页、同一台机器）

| 通道 | 结果 |
| --- | --- |
| 内置浏览器（`type=desktop`） | 点下载图标多次，磁盘无任何新文件；导航到直接返回 zip 的地址时工具调用超时（「等待浏览器预览打开」）。下载可能已发生，但**浏览器通道被卡死，Agent 拿不到结果**，只能由用户自己去找文件。历史同类操作的文件落在与下载无关的工作区目录 `某个与下载无关的工作目录\`，不是 `~/Downloads` |
| 扩展浏览器（Edge，已登录） | 一次点击即成功，5 秒内落盘 `~/Downloads/quark-share-skill-installer-1.3.7 (1).zip`，扫盘识别、审查 0 错误 |

结论：内置浏览器只在没有任何扩展浏览器可用时作最后手段，且必须当场告诉用户「下载可能已开始，但结果不可见，需要你自己确认文件位置」。

### 常见坑

| 现象 | 处理 |
| --- | --- |
| `no current window` | 浏览器没开窗口，请用户打开后重试 |
| 点了图标没有文件 | 先确认点的是图标不是行；多次无效转手动下载 |
| 下载后工具调用超时 | 用了内置浏览器，换扩展浏览器重做 |
| 文件名带 ` (1)` | 正常，重复下载自动改名，按最新取 |
| `--since` 无法解析 | 去掉 `@`，用纯 epoch 数字 |

## 4. 途径 B · 用 computer-use 操作浏览器（legacy）

> **前置禁令：绝不使用虚拟桌面 / 隔离桌面。** 只能在用户的**主桌面**上操作（`gui_screenshot` / 任务目标都用 `window_id: "screen"`）。任何「新建隔离桌面」「切换到 child session」的模式一律不用——它会替换用户的桌面环境，实测存在**损坏壁纸**的风险，且不可逆。如果某能力只在虚拟桌面下可用，就别用它，转第 4 节之外的路径（手动下载）。
>
> **开工前必查**：`gui_list_windows` 返回里若存在 `kind: "child_session"` 的「独立桌面」，说明宿主的「默认独立桌面」开关正生效，此时 `create_task` 即使传 `window_id: "screen"` 也会被路由到那个桌面。**遇到这种情况就不创建任务**，请用户到「设置 → 电脑控制」关掉「默认独立桌面」，或改走手动下载。绝不要调 `gui_child_session_open`、不要把 `child_session` 当目标、不要用 `gui_child_session_cleanup { force: true }` 抢会话。
>
> 另外两条：动手前取得用户同意；主桌面操作会接管鼠标键盘，开场先说「接下来几秒请不要动鼠标」。

本机 `computer-use` 技能提供 `info / screenshot / activate / click / type / key / scroll`，后端是 PowerShell 脚本。三条硬规矩：JSON 走 stdin 管道、Windows 路径反斜杠在 JSON 里双写、每次调用只输出一行 JSON。

标准循环：**每做一步，先截图确认，做完再截图确认**。

1. 探路与激活

   ```
   info {}                          # 看显示器边界、前台窗口标题
   activate {"title":"Edge"}        # 标题子串匹配，最小化窗口会自动还原
   screenshot {"path":"C:\\Users\\...\\shot1.png"}
   ```

   截图必须用图像查看能力真正打开，不能只看返回的尺寸就宣称看到了。

2. 打开分享链接

   - `key {"keys":["ctrl+l"]}` 聚焦地址栏；或先点击地址栏坐标。
   - `type {"text":"https://pan.quark.cn/s/xxxx\n"}` —— `type` 里的 `\n` 即回车。
   - 截图确认页面加载完成（分享标题、文件列表出现）。

3. 输入提取码

   - 截图定位输入框 → `click` → `type {"text":"ab12"}` → 点击「提取文件 / 确定」。
   - 若无需提取码，跳过。
   - **密码 / 验证码 / 支付类输入框一律不代填**，交还用户本人。

4. 定位目标 .zip

   - 列表长时用 `scroll {"x":...,"y":...,"clicks":-3}` 向下滚动，每次滚动后再截图。
   - 分享是文件夹时，双击进入子目录，重复截图确认。
   - 记下目标文件名，供 `find_quark_zip.py --keyword` 使用。

5. 点击「下载」

   - **必须区分**：「转存到我的网盘」「保存到网盘」「存到我的夸克」只是云端转存，不产生本地文件；需要的按钮文案是「下载」「下载到本地」「直接下载」。
   - 勾选文件后点下载；若弹出「打开夸克客户端」，优先看是否有「仍用浏览器下载」；没有则转途径 B。
   - 若浏览器开启「下载前询问保存位置」，会弹出另存为对话框：确认路径后再点保存。这属于「确定」类操作，先向用户确认。

6. 确认下载完成

   - 截图看下载栏是否显示完成，或看下载目录里是否出现 `.crdownload` / `.part`。
   - 把结果交给 `find_quark_zip.py` 做最终判定（文件大小稳定 + 有效 zip），**不要**仅凭肉眼判断。

## 5. 途径 B' · 用 desktop-control（无障碍树）

仅当本机已安装 `agent-desktop` CLI 时使用，先跑 `agent-desktop status` 与 `agent-desktop skills get platform`。

```
agent-desktop snapshot --skeleton --app "Edge" -i --compact
agent-desktop click '@s8f3k2p9:e12'
agent-desktop snapshot --root '@s8f3k2p9:e3' -i --compact
```

规则：`ref` 必须带快照 ID；界面变化后旧 ref 失效要重新快照；出错时只有 `error.disposition == retry` 且 `safe == not_delivered` 才允许重试；默认无头模式，不要为了「救场」切 `--headed`；PowerShell 里 `@` 是 splatting 运算符，每个 ref 都要加引号。本路径不涉及桌面切换，但仍受同一条禁令约束：**不得为了让 CLI 跑起来而创建或切到虚拟桌面**。

优点是可以按按钮文本（「下载」「提取文件」）定位，不依赖坐标；缺点是浏览器页面的无障碍树有时层级很深，需要 `--root` 逐层钻取。

## 6. 途径 B2 · 夸克 PC 客户端

- 网页版点击下载后若拉起客户端，切换到客户端窗口继续（用 `activate` 或 `agent-desktop` 的窗口切换）。
- 客户端的下载目录在「设置 → 下载设置」里，可能不是 `~/Downloads`；用 `find_quark_zip.py --dir` 显式指定该目录。
- 客户端可能默认「先转存再下载」，确认下载任务确实完成、文件在磁盘上。
- 大文件下载耗时较长，`--wait` 适当调大（如 300 秒）。

## 7. 途径 C · 内置直链 API 下载

实现在 `scripts/quark_share_download.py`，只用标准库 `urllib`。链路：

| 步 | 接口 | 状态 |
| --- | --- | --- |
| 1 | `POST https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc&uc_param_str=` body `{pwd_id, passcode}` → `data.stoken` | 已由 `quark-drive` 实测 |
| 2 | `GET .../share/sharepage/detail?...&pwd_id=&pdir_fid=&stoken=&_page=&_page_size=50&_sort=...` → `data.list` | 已由 `quark-drive` 实测 |
| 3 | `POST https://drive-h.quark.cn/1/clouddrive/share/sharepage/save` body `{pwd_id, stoken, pdir_fid, to_pdir_fid:"0", pdir_save_all:false, scene:"link"}` → `data.task_id` | 已由 `quark-drive` 实测 |
| 4 | `GET .../task?task_id=&retry_index=N` → `data.status==2`，`data.save_as.save_as_top_fids[]` | 已由 `quark-drive` 实测 |
| 5 | `POST .../file/download` body `{fids:[fid]}` → `data[].download_url` | 路由已探测存在（GET→405，POST→401）；返回字段形状未端到端验证 |
| 6 | `GET download_url`（带 Cookie + `Referer: https://pan.quark.cn/`）→ 本地 .zip | 依赖步 5 |
| 7 | `POST .../file/delete` body `{action:2, filelist:[fid], to_trash:true}` 清理副本 | 同步 3-4 的来源 |

**为什么不是直接 `sharepage/download`**：2026-11-22 实测，`POST /share/sharepage/download` 返回
`{"status":404,"error":"Not Found","message":"No message available","path":"/1/clouddrive/share/sharepage/download"}`，
与故意写错的路由（`.../definitely-not-a-route`）响应**逐字段一致**，GET 亦同；而 `POST /file/download`
返回业务包 `{"status":401,"code":31001,"message":"require login ..."}`、GET 返回 `405 Method Not Allowed`。
结论：前者是**不存在的路由**，不是"尚未验证"。因此自动下载改为"转存 → 自有网盘取直链"，且默认关闭。

### Cookie 来源（优先级）

`--cookie-file` > 环境变量 `QUARK_COOKIE` > 同目录 `cookie.txt` > `quark-drive` 技能的 `scripts/cookie.txt`。

最后一个位置不是写死的 `~/.workbuddy/skills`，而是由 `scripts/_skills_paths.py` 统一解析：本技能所在根 → `QSI_SKILLS_DIR` → `<config>/skills` → `~/.workbuddy/skills`。`preflight.py` 的 `cookie` 检查、`quark_drive_skill` 探测和本脚本的 `load_cookie()` **import 的是同一个模块**，不是两套长得像的实现——否则 `QSI_SKILLS_DIR` 指向工作区 `.skills` 时，预检会说“没 Cookie”从而把 `route` 判成 `gui`，明明登录态就在那儿却绕开 API 路径；`WORKBUDDY_CONFIG_DIR` 改过时则反过来，预检说“有 Cookie”、下载却 401。

加载失败时（技能包缺文件）两个脚本都会以退出码 2 报“缺少 `scripts/_skills_paths.py`”，而不是扔一段 traceback。

`quark-drive` 的 `get_cookie.py` 可自动开浏览器检测登录态并抓取（依赖 `agent-browser`）。**Cookie 是账号钥匙**：脚本只在内存中使用，绝不打印、不写日志、不进 JSON 输出。签名直链含临时凭证，同样不输出，只回显下载域名。

### 常用命令

```bash
# 先只列内容（只走已验证接口，用来确认登录态/提取码/目标文件）
"<PY路径>" "<SKILL_DIR>/scripts/quark_share_download.py" "<分享链接>" --list-only --json

# 完整下载：必须显式同意"转存到自己网盘"这一步（会写账号、消耗转存次数）
# 不加 --allow-save-to-drive 时脚本直接拒绝——分享文件没有可用的直链接口。
# 不传 --out-dir 时落在 <config>/runtimes/quark-installer/downloads，即 ~/.workbuddy 内
"<PY路径>" "<SKILL_DIR>/scripts/quark_share_download.py" \
  "https://pan.quark.cn/s/1a2b3c4d5e6f?pwd=ab12" --allow-save-to-drive \
  --out-dir "$HOME/.workbuddy/runtimes/quark-installer/downloads" --json

# 多个 zip 时消歧
"<PY路径>" "<SKILL_DIR>/scripts/quark_share_download.py" "<分享链接>" --keyword my-skill --json
"<PY路径>" "<SKILL_DIR>/scripts/quark_share_download.py" "<分享链接>" --fid <32位fid> --json
```

其他参数：`--passcode`（覆盖链接里的 `?pwd=`）、`--keep-saved`（下载后保留网盘副本，默认会移入回收站）、`--max-depth`、`--max-size`、`--timeout`。

### 实现要点

- **分页**：`detail` 按 `_page` / `_page_size=50` 翻页，用 `_metadata.total` 判断终止，最多 20 页。
- **递归**：对 `dir=true` 的条目用其 `fid` 作 `pdir_fid` 再请求，深度 3、总条目 500，每次请求间隔 50ms。
- **不猜文件**：只认 `.zip` 后缀；多个候选直接报错列出，等 `--keyword` / `--fid` 指定。
- **落盘**：先写 `*.part`，完成后用 `zipfile.is_zipfile` 校验再改名；同名文件自动加 `(1)` 后缀，绝不覆盖已有下载。
- **大小上限**：200 MB（与安装器一致），防止误下大文件。
- **凭据不外泄**：错误与 JSON 输出中不含 Cookie、提取码值、完整直链。

### 这条链的可信边界

- **已实测**：`token` / `detail` / `save`（drive-h）/ `/task` 轮询——来自 `quark-drive` 技能的抓包与实测。
- **已探测路由存在性**：`/file/download`（GET→405、POST→401 业务包）、`/file/delete`。
- **未端到端验证**：`file/download` 的返回字段形状（脚本按 `data[].download_url` 解析，并兼容 `data.download_url`）、
  以及"转存 → 定位副本 fid → 取直链 → 下载 → 回收站"整条链。
- **明确不存在**：`sharepage/download`。它返回的是网关级 404，与乱写的路由响应一致。

首次接入真实链接时：

1. 先跑 `--list-only`，确认 `code=0`、能看到分享文件清单（这一步可信）。
2. 征得用户同意后再加 `--allow-save-to-drive` 跑完整下载。
3. 若 `转存失败` / `取下载直链失败` / `定位不到副本 fid`，**不要反复重试、不要换参数硬试**，直接转浏览器取包（第 3 节）或手动下载（第 4 节）。
4. 若拿到 HTML 错误页，脚本会以「不是有效 zip」拒绝；多为 Cookie 过期，刷新后重试一次，否则转 GUI。
5. 下载成功后核对 `transfer.trashed`：为 `false` 说明网盘里那份副本没清掉，需要提醒用户手动删除。

脚本 JSON 输出里的 `verified_steps` / `unverified_steps` / `warning` 会如实标注，向用户转述时不要把它说成「已实测可用」。

### 与 quark-drive 技能的关系

端点、风控头、`drive-h` vs `drive-pc`、错误码（41000/41008/41009/41017）等知识来自该技能的 API 参考文档（其 references 目录下的 `api_reference.md`）与 README 踩坑合集。本技能**不 import 它的模块**（市场技能可能被更新或卸载），只复用相同的 Cookie 约定与端点知识，并额外补齐了它缺失的两点：**提取码传递**与**实际下载落盘**。

## 8. 常见坑

| 坑 | 表现与处理 |
| --- | --- |
| 链接失效 | 「分享已取消 / 已过期」或 `41009`，向分享者索要新链接 |
| 提取码错误 | `41000 提取码不符合规范`；向用户索取正确值，不反复试错触发风控 |
| Cookie 过期 | 所有接口 `code!=0` / 403 / 302；刷新 Cookie（关键字段为 `__pus`、`__puus`、`__kp`、`__kps` 四个） |
| 下载域 auth expired | JSON 接口能用、下载直链返回 HTML；pds 域校验更严，刷新 Cookie 并带 `Referer` |
| 转存 / 取直链失败 | 步 3-5 报错、拿不到 `download_url` 或定位不到副本 fid；改走第 3 节浏览器取包，别死磕，也别换参数硬试 |
| 浏览器 `no current window` | 没开窗口，请用户打开浏览器后重试；不要擅自启动用户的浏览器 |
| 点下载后没有新文件 | 先确认点的是下载图标而非文件行（行被选中=点偏了，图标往右调几像素）；多次无效转手动下载 |
| 下载后工具调用超时 | 典型是用了内置浏览器，它会被下载动作卡死；换扩展浏览器 |
| 下载文件名带 ` (1)` | 重复下载的正常改名，按最新取即可 |
| 未登录 | 网页版下载要求登录；让用户本人在浏览器登录 |
| 点成「转存」 | 网盘里多了文件、本地没有；回分享页点「下载」 |
| 下载未完成 | 文件是 `.crdownload` 或大小持续增长；交给 `find_quark_zip.py --wait` |
| 分卷 / 改后缀 | `xxx.zip.001`、`xxx.zip` 实为 rar、后缀被改成 `.qk`；只处理单个有效 zip |
| 文件名乱码 | 中文 ZIP 常用 GBK 编码；安装脚本按归档内路径处理，报告里如实展示 |
| 限速 / 需会员 | 夸克对大文件非会员限速；`--wait` 留足时间，必要时改用客户端 |
| 分享里混有多个 zip | 脚本列出候选要求指定；安装器阶段 3 也会列出全部技能，先确认是否全部安装 |

## 9. 隐私

- 分享链接、提取码、Cookie 都属于临时凭据，只用于当次下载，不写入技能文件、不写进长期日志、不外传、不粘贴到对话里。
- 下载直链含临时签名，不回显完整 URL。
- 桌面截图与无障碍树快照可能包含屏幕上其它私密内容，仅用于当次定位，用后不留存到公开位置。
- 批量请求保持间隔，不并发，避免触发风控连累账号。
