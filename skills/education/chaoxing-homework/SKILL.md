---
name: chaoxing-homework
display_name: 学习通作业助手
display_name_en: Chaoxing Homework Assistant
description: "通过 CDP 接管用户已登录的 Edge 浏览器，在学习通（超星）网页版中自动定位指定课程作业，跨新旧两代页面模板抽取题目、作答客观题与文本题；对文本答案做 AI 味与 AIGC 判定率优化并用量化脚本把关，客观题按双答案交叉法自检正确率达到 95% 以上后才提交，提交后读取批阅结果复盘错题。当用户说「帮我做/完成学习通或超星的作业」「把这门课的作业写了」「登学习通把 XX 作业交了」时使用。"
description_zh: "通过 CDP 接管用户已登录的 Edge 浏览器，在学习通（超星）网页版中自动定位指定课程作业，跨新旧两代页面模板抽取题目、作答客观题与文本题；对文本答案做 AI 味与 AIGC 判定率优化并用量化脚本把关，客观题按双答案交叉法自检正确率达到 95% 以上后才提交，提交后读取批阅结果复盘错题。当用户说「帮我做/完成学习通或超星的作业」「把这门课的作业写了」「登学习通把 XX 作业交了」时使用。"
description_en: "Automates Chaoxing (Xuexitong) homework in the logged-in web app via CDP: locates the assignment, extracts and answers single/multiple-choice and essay questions across both legacy and mooc2 page templates, rewrites essays to reduce AI-detection and plagiarism signals with a quantitative pre-submit check, verifies objective answers by cross-checking until >=95% confidence, then submits and reviews the graded result. Use when the user says \"do my Chaoxing/Xuexitong homework\" or \"submit assignment XX for me\"."
category: education
version: "1.0.0"
author: 薄肌男孩
triggers:
- "学习通作业"
- "超星作业"
- "帮我做作业"
- "把这门课的作业写了"
- "登学习通交作业"
- "chaoxing homework"
- "xuexitong assignment"
---

# 登录学习通完成作业

## 总览

用用户本机 Edge（调试端口 9222）接管已登录的学习通网页版，把「找作业 → 作答 → 降 AI 味 → 正确率自检 → 提交 → 回报」串成一条可复现的流水线。脚本只做确定性动作（抽题、填写、复核、截图、提交），答案判断和文字改写由模型完成。

**安全边界**：不代用户输入账号密码、不处理验证码/扫码，登录由用户本人在浏览器里完成；提交是不可撤销动作，必须先过质量双关卡。

## 前置条件

1. Edge 已启动并开启 `--remote-debugging-port=9222`。
   - 正常环境下：`explorer.exe "<skill>/scripts/launch_edge.bat"`（沙箱会话无法直接弹 GUI，必须经 explorer 委托到用户桌面）。
   - 脚本会自动打开 `https://i.chaoxing.com` 并检测端口；若输出 `PORT_NOT_READY`，等 3 秒再跑一次检测，仍失败则让用户手动开 Edge。
2. 用户已在该 Edge 窗口中完成学习通登录（网页版与桌面版登录态不共享，第一次一定需要扫码）。
3. `scripts/run.sh status` 能打印出 `loggedIn: true`，再往下走。

## 工作流程

### 1. 登录与定位作业

```bash
scripts/run.sh status                      # 确认已登录、当前页是否作业页、模板版本
```

`status` 的三个关键字段先看清，能省掉后面所有瞎试：

- `template: mooc2 | legacy` —— 两套 DOM 不通用的模板（新版 `/mooc2/work/dowork`，旧版 `doHomeWorkNew`）；
- `submitted: true` —— 页面已是批阅/详情页（有「查看详情/重做/提交时间」），**不要再往里填**；
- `error: NO_PERMISSION_3004` —— 链接缺 `enc`，手拼 URL 是拿不到的。

**新版作业列表不要再手拼 `getAllWork`（必 3004）**，按这四步拿：

1. 打开通知页 `https://mooc1-1.chaoxing.com/mooc-ans/visit/interaction`；
2. 抓目标课程的 `a[href]`（里面才有完整的 9 位 `clazzid` 与 `cpi`）；
3. 进课程页后读 `document.querySelector('iframe').src` —— 即 `mooc2/work/list` 作业列表；
4. `scripts/run.sh list` 打印每份作业的「名称 + 状态 + 作答 URL」，挑未交的那份。

拿到的 `workId` 即作业唯一标识。进页后 `status` 确认 URL 含 `dowork`（或旧版 `doHomeWorkNew`）再往下走。

课程 ID 常量、两代 DOM 的完整对照、提交机制都写在 `references/chaoxing-dom.md`，页面结构变化时的排查也在这里。

### 2. 抽题

```bash
scripts/run.sh extract --out .cx/questions.json
```

产出每题的 `index / type(single|multi|text) / question / options[letter,text] / texts[当前值]`。

识别数为 0 时按 `references/chaoxing-dom.md` 的「识别失败排查」处理，不要硬猜 DOM。

### 3. 作答（不提交）

逐题给出答案，写入 `answers.json`（结构见 `assets/answers.example.json`）：

```json
{ "1": {"type":"single","answer":["C"]},
  "2": {"type":"multi","answer":["A","C"]},
  "14": {"type":"text","text":"改写后的简答"},
  "15": {"type":"text","texts":["空1","空2"]} }
```

- **字母必须是页面显示的字母 A/B/C/D**，不是 `input.value`。该平台的 value 与显示字母经常乱序，`cx.js` 已按 label 首字母匹配，但仍要在 `verify` 时复核。
- 客观题按知识作答；SQL/代码类把语句写完整可执行，不加多余解释。
- `scripts/run.sh fill --answers answers.json`

### 4. 文本题降 AI 味（改写后再写入）

先写一版答案，再按 `references/answer-quality.md` 的规则重写：去套话（首先/其次/综上）、长短句交替、加具体细节、打破平行结构、中文全角标点、不要 Markdown 痕迹。术语、公式、字段名保持原样，**改写不得改变结论**。

改写后用 `fill` 覆盖写入（原生 setter + input/change 事件已封装），确认 `textLen` 落在合理区间（简答 ≥80 字，按题目字数要求核对）。

**改写必须有闭环，不能凭感觉交付**：

```bash
node scripts/textcheck.js .cx/q5.txt        # 测这一篇
node scripts/textcheck.js --dir .cx/txt     # 批量
```

退出码 0 才算通过（人写度 ≥75 且无 HIGH 项）。未通过时按报告里的「待改」逐条修，修完再测，**最多 3 轮**；3 轮仍不过，把报告贴给用户看，让他决定是否按当前版本提交。常见卡点是「句长 CV 偏低」「短句占比为 0」——直接加一两句 4–8 字的话最快。

### 5. 正确率自检（硬门槛：≥95%）

```bash
scripts/run.sh verify --out .cx/verify.json
```

1. `summary.pending` 必须为空。
2. 按 `references/answer-quality.md` 的**双答案交叉法**独立重做一遍，逐题 diff；只攻分歧题，多选按选项逐个判真假。
3. 计算存疑题占比：`存疑数 / 总题数 ≤ 5%` 才允许提交。10 题以内的作业要求 0 存疑。
4. 存疑题先自行修正并重新 `fill`；修完再 `verify` 一次。
5. **仍超 5% 就停下**，把存疑题目、两种判断及理由列给用户，等指示；不要为了「完成任务」强行提交。

**文本关**（有简答题时必跑）：`textcheck.js` 退出码为 0。两关都过才允许进入提交。

```bash
scripts/run.sh shot --out .cx/before_submit.png   # 提交前留档，肉眼扫一遍
```

### 6. 提交

```bash
scripts/run.sh submit          # 真实点击提交 + 处理确认弹层
scripts/run.sh submit --text   # 只预览：在二次确认前停手
```

新版页面的提交流程与坑（细节见 `references/chaoxing-dom.md`）：

1. 点 `.sub-button` 里的「提交」（新版 onclick 没有 `submitWork` 类关键词，只能靠文案匹配）；
2. 弹「确认提交？」层，底部有两个 `a.jb_btn` —— **其中 `#hintOk` 是隐藏的**，脚本已用 `:visible` + 排除 `#hintOk` + 校验 `boundingBox` 处理；
3. 确认层**必须用真实鼠标点击**（`locator.click()`），在页面里 `a.click()` 无效，弹层不会关；
4. 成功则跳 `/mooc2/work/prompt`，正文含「提交时间 / 查看详情」，脚本会顺带抓分数。

- 只在第 5 步全绿后才执行；**不要**因为「先跑一下看看」而提前提交。
- 有次数限制的作业失败一次就停，先 `shot` 看现场再决定，不要盲目重试。
- 提交成功后再 `status` 读一次，确认 `submitted: true` / 列表页状态变「已完成」。

### 7. 批阅复盘（提交后必做）

```bash
scripts/run.sh review --out .cx/review.json
```

在 `/mooc2/work/view` 详情页读取每题「我的答案 / 正确答案 / 得分」，输出错题清单。用途有两个：

- **如实汇报**：分数只能说明错了几题，复盘才能告诉用户错在哪、为什么错；
- **沉淀口径**：错题若属于「出题人口径」问题（教科书常识与本题答案不一致），当天记进 `references/chaoxing-dom.md` 的「出题口径」一节，同课程后续作业直接复用。

进入方式：用 `list` 拿到的 URL 打开已交那份，会自动从 `task` 302 到 `view`。

## 命令速查

| 命令                                     | 作用                          |
| --------------------------------------- | ---------------------------- |
| `scripts/run.sh status`                | URL / 登录态 / 模板版本 / 是否已交      |
| `scripts/run.sh list`                  | 作业列表（名称、状态、作答 URL）          |
| `scripts/run.sh extract --out q.json`  | 抽题（自动识别新版/旧版 DOM）            |
| `scripts/run.sh fill --answers a.json` | 填写（不提交）                     |
| `scripts/run.sh verify --out v.json`   | 复核填写完整性（含隐藏字段校验）            |
| `scripts/run.sh shot --out x.png`      | 整页截图                        |
| `scripts/run.sh submit [--text]`       | 真实点击提交并处理确认层                |
| `scripts/run.sh review --out r.json`   | 批阅复盘：我的答案/正确答案/得分/错题        |
| `scripts/run.sh eval --code "…"`       | 页面内执行任意 JS（排查/导航）           |
| `node scripts/textcheck.js <f> [--json]` | 文本 AI 味量化检测 + AIGC 特征评分    |
| `node scripts/lint.js`                 | **发布前自检**：frontmatter/路径/编码/隐私 |

环境变量：`CX_CDP`（默认 `http://127.0.0.1:9222`）、`CX_PAGE_HINT`（默认匹配 `doHomeWorkNew|dowork`）。
`run.sh` 自动定位 node 与 playwright-core；若报找不到模块，设 `NODE_BIN` 或 `NODE_PATH` 指向已有的 `node_modules`。

## 输出要求

提交完成后，用中文回报，包含三块，不要贴原始 JSON：

1. **完成了哪项作业**：课程名、作业名、题型与题量、提交时间、提交状态（成功/失败原因）。
2. **正确率**：客观题 `已确认/总数` 与百分比；存疑题清单（题号 + 最终选择 + 一句话理由）；文本题的字数与改写要点（只说做了哪些降 AI 处理，不复述全文）。
   - 文本题要报「字数 + 人写度检测分」，并说明改了哪几类特征（拆句/删连接词/加细节/去套话）。
   - 提交后用 `review` 拿到的真实错题要写出来：题号、我选什么、正确答案是什么、错因一句话。**不要只用分数代替复盘**，也不要凭猜测罗列错题——没跑 `review` 就不写错题。
3. **本次重点内容**：3–6 条知识点，写成「概念 → 本题怎么考的」的形式，便于复习；有易错点（NULL 比较、BETWEEN 边界、聚合函数与 GROUP BY 的关系之类）单独点出来。

若中途停下（未提交），明确说明卡在哪一步、已填多少、需要用户决策什么，并给出 `shot` 截图路径。

## 发布到开放平台前

改完技能一定要跑一次自检，退出码 0 才算可上架：

```bash
node scripts/lint.js
```

**开放平台 frontmatter 必填字段**（缺一个就报「解析失败」）：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| `name` | 唯一标识，kebab-case，与目录名一致 | `chaoxing-homework` |
| `version` | 三段式语义版本，**必须加引号** | `"1.0.0"` |
| `display_name` | 中文展示名 | `学习通作业助手` |
| `display_name_en` | 英文展示名（不能含中文） | `Chaoxing Homework Assistant` |
| `description` | 旧版字段，与 `description_zh` 保持一致 | 中文，含「当用户说…」 |
| `description_zh` | 中文描述，30–1024 字符 | 同上 |
| `description_en` | 英文描述（不能含中文） | 英文 |
| `category` | 分类 | `education` |
| `triggers` | 触发词列表 | 中英混排 |

两个高频坑：
- `version: 1.0` 会被 YAML 解析成**浮点数 1**，`version: 1` 会变成整数——平台按字符串比对，直接判非法。**一定要写 `"1.0.0"` 并加引号。**
- 描述里出现英文半角双引号要转义（`\"`），否则会提前闭合字符串导致解析失败。

它会卡住这几类**上线后才暴露**的问题：

- `---` 被写成 `\---`、带尾随空格、或 frontmatter 内部有空行 → 平台报「frontmatter 无法解析」；
- `.md/.js/.sh` 是 CRLF → Linux/macOS 下 bash 报 `bad interpreter`；
- 文件带 UTF-8 BOM → 首行解析成 `﻿---`；
- `SKILL.md` 里引用不存在的 `scripts/` `references/` 路径；
- 残留运行产物（`cx_*.json`、截图）或真实 `courseId` / `enc` 签名串。

`.gitignore` 已忽略运行产物，提交前确认 `git status` 没有 `cx_*` 文件。

## 资源

- `scripts/cx.js`：全部动作的 CLI 实现（抽题/填写/复核/截图/提交/列表/复盘/求值），新旧两套 DOM 均已适配。
- `scripts/launch_edge.bat`：以 9222 调试端口启动独立 profile 的 Edge。
- `scripts/run.sh`：定位 node 与 playwright-core 的包装器。
- `references/chaoxing-dom.md`：两代页面模板对照、作业定位四步法、DOM 与勾选类名坑、提交机制、批阅复盘、**出题人口径陷阱**、故障排查。
- `scripts/lint.js`：发布前自检（frontmatter 边界与 YAML、name/description 规范、脚本语法、路径引用、BOM/CRLF、隐私串）。
- `scripts/textcheck.js`：文本 AI 味量化检测（句长 CV / 套话密度 / 句首重复 / 四字格 / 段落均匀度 / 口语痕迹 / 短句占比），退出码即门槛。
- `references/answer-quality.md`：正确率双答案交叉法、**降 AIGC 判定率的 7 个改法与查重控制**、三档改写范例。
- `assets/answers.example.json`：answers.json 的字段结构与示例。
