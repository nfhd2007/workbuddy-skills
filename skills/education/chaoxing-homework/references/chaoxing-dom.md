# 学习通（超星）作业页 DOM 与踩坑备忘

## 环境事实（先读，能省掉一半试错）

- **必须用网页版**。学习通 Windows 桌面版是 Electron 且有防调试保护，带 `--remote-debugging-port` 启动会立即退出。
- **网页版与桌面版登录状态不共享**，第一次必须让用户扫码或输密码，脚本不碰账号密码。
- 在 Agent 沙箱里直接 `start msedge` 往往不弹窗（沙箱会话无交互桌面）。用 `explorer.exe "…\scripts\launch_edge.bat"` 把启动动作委托给用户桌面会话。`explorer.exe` 直接传参数无效，必须先有 .bat。
- CDP 端口固定 `9222`，`--user-data-dir` 用独立目录（`%LOCALAPPDATA%\cx-edge-profile`），这样不影响用户日常浏览器，且登录 cookie 能长期复用。
- 接管方式：`chromium.connectOverCDP('http://127.0.0.1:9222')`，取 `contexts()[0].pages()`，**不要** `browser.close()` 关掉用户的浏览器——playwright 关闭 CDP 连接不会杀进程，但仍要避免 `ctx.close()`。

## 两代页面模板（这是最根本的分叉，先判版本再谈其他）

2026 年 10 月实测：同一账号下，老课程走旧版，新开课程走 **mooc2 新版**。两套 DOM 几乎无交集，脚本必须双写。

| | 旧版 legacy | 新版 mooc2（当前主流） |
| --- | --- | --- |
| 作答页 | `/mooc-ans/work/doHomeWorkNew` | `/mooc-ans/mooc2/work/dowork` |
| 详情/批阅页 | `…/work/selectWorkQuestionYiPiYue` | `/mooc-ans/mooc2/work/view` |
| 题目容器 | `div.TiMu` | `div.questionLi`（带 `id="question{id}"`、`typename="单选题"`） |
| 题面 | `.Zy_TItle` | 容器内 `h3.mark_name` |
| 选项 | `ul.Zy_ulTop li` + `input[type=radio]` | `div.answerBg`（`onclick="addChoice(this)"`）+ `span.num_option[data="A"]` |
| 有无原生 input | 有 | **没有**，纯 div + 类名 |
| 勾选状态 | `input.checked` | `.num_option` 的类名含 `check_answer`（**不在** `.answerBg` 上） |
| 答案隐藏字段 | — | `input#answer{qid}`（另有 `answertype{qid}`，务必排除） |

`cx.js status` 会打印 `template: legacy | mooc2`；`extract` 的 `questions[].type` 已归一化为 `single/multi/text`。

## 关键 URL 与「怎么拿到作业」

| 用途 | 形如 |
| --- | --- |
| 登录 | `https://i.chaoxing.com` → 跳 `passport2.chaoxing.com` |
| 通知/课程列表 | `https://mooc1-1.chaoxing.com/mooc-ans/visit/interaction` —— 所有课程的真实 `clazzid` 从这里取 |
| 课程主页 | `…/mooc-ans/visit/stucoursemiddle?courseid=…&clazzid=…&vc=1&cpi=…&ismooc2=1&v=2` |
| **作业列表（新版）** | 课程主页里的 iframe：`https://mooc1.chaoxing.com/mooc2/work/list?courseId=…&classId=…&cpi=…&ut=s&stuenc=…&enc=…` |
| 作业作答 | 列表页每个 `li[data]` 的 URL，形如 `…/mooc2/work/task?…&workId=…&answerId=…&enc=…`（访问后 302 到 `dowork`） |

**不要手拼 URL**，三个坑都踩过：

1. `…/work/getAllWork?courseId=…&clazzid=…&cpi=…` 直接访问返回 `3004 您长时间没有操作，或没有此页面访问权限`——`enc` 是服务端签发的，拼不出来。
2. `clazzid` **不是** `153` 这种短号，而是 9 位长号（如 `15xxxxxxxx`）；通知页 href 里的才是完整的。写错照样 3004。
3. 正确姿势：`interaction` 页 → 抓课程 `a[href]` → 进课程页 → 读 `document.querySelector('iframe').src` → 打开列表页 → `run.sh list` 拿每份作业的 `li[data]`。

以上四个参数**每个账号都不同**，必须现场从通知页 / 课程页 iframe 取，不要硬编码：
- `courseId`：课程唯一 ID
- `clazzId`（URL 里也叫 `classId`）：9 位班级 ID
- `cpi`：平台侧的课程实例参数，与账号绑定
- `enc` / `stuenc`：服务端签发的签名串，**无法手算**，只能从页面 href 或 iframe src 原样复制

把课程参数写进脚本或用 `--course=…&--class=…` 传参都可以，但不要把别人的 ID 固化成默认值。

## 题目容器（识别失败排查）

`cx.js extract` 已同时覆盖两套。若 `题目数: 0`，按以下顺序排，**不要盲目猜选择器**：

1. `run.sh status`：看 `template`、`error`、`submitted` 三个字段。
   - `submitted: true` → 已经交过了（页面有「查看详情/重做/提交时间」），不是 DOM 问题。
   - `error: NO_PERMISSION_3004` → 链接缺 enc，回到上一节重新取。
2. 若 `template: mooc2` 但 `hasQuestion: false`，可能是题目在 iframe 里或脚本未加载完，`sleep 3` 再跑一次。
3. 真要换选择器：`run.sh eval --code "[...document.querySelectorAll('[class*=question]')].map(e=>e.tagName+'.'+e.className)"`，把真实 class 补进 `questionNodes()`。

## 最大的坑一：选项字母 ≠ input.value

旧版表单里 `input.value` 常是 `0/1/2/3` 或题库乱序 ID，**和页面显示的 A/B/C/D 不一一对应**；新版干脆没有 input。

正确做法：字母只从可见元素取——新版取 `span.num_option` 的 `data` 属性，旧版取最近 `li/label` 的首字母。`cx.js letterOf()` 已封装。`fill` 后用 `verify` 复核**被点亮的字母**，不要只信 fill 日志。

## 最大的坑二：新版选项的点击与勾选判定

- 必须点 **`.answerBg` 本身**（它的 `onclick="addChoice(this)"` 才是注册逻辑的入口）。点里面的 `span.num_option` 无效。
- 勾选后类名加在 **`.num_option`** 上（`class="choice406023552 num_option fl check_answer"`），`.answerBg` 的类名不变。判断「是否已选」要查 `.num_option`，查 `.answerBg` 会永远返回 false，导致 `verify` 全部 `pending`。
- 多选也用同一个 `check_answer` 类，不要找 `check_answer_dx`（那是别的模板）。
- 隐藏字段 `input#answer{qid}` 与勾选同步，可做第二道校验，但注意 `document.querySelector('input[id^=answer]')` 会**先命中 `answertype{qid}`**（值是 `0`），必须用 `#answer{qid}` 精确定位。

## 填空 / 简答

- 简单填空：`textarea` 或 `input[type=text]`，直接赋值不生效，必须走原型上的原生 setter 再派发 `input`+`change`（`cx.js` 已处理）。
- 简答/论述：多为 UEditor，即同源 `iframe[id^="ueditor"]`，写 `iframe.contentDocument.body.innerHTML`。写入后用户端提交时 UEditor 会同步，但**若题目在 iframe 内有独立字数统计**，需在 iframe 内再派发一次 `input`。
- 一题多空按 `fields[i]` 顺序对应，answers.json 用 `texts: ["空1","空2"]`。

## 提交（新版实测，2026-10）

旧版流程（供对照）：点「提交作业」→ `validateTime` 风控 → `WAY.box` 确认层（「确定」）→ `submitCheckTimes` → `form1submit` → `confirmSubmitWork`。

**新版流程**：

1. 顶部 `.sub-button` 里的「提交」（`onclick` 里**没有** `submitWork` 之类的关键词，靠文案匹配）。
2. 弹出 `.popWord` 文案「确认提交？」，底部 `.popBottom` 内有两个 `a.jb_btn`。
3. 点确认层里的「提交」→ 跳转 `/mooc2/work/prompt`，页面显示分数与「查看详情」。

三个必须注意的点：

- **确认层不能用 DOM `.click()`**。`page.evaluate(() => a.click())` 点了没反应（弹层仍在），必须用 playwright 的 `locator.click()` 发真实鼠标事件。
- **不能用 `locator('.popBottom a.jb_btn').last()`**。该层里有隐藏的 `#hintOk`（`display:none`），`last()` 会命中它，然后卡满 30s 超时报 `element is not visible`。要用 `:visible` 过滤 + 排掉 `id=hintOk` + 检查 `boundingBox()`。
- **成功判定**：URL 跳到 `/mooc2/work/prompt` 或正文出现「提交时间 / 查看详情」；分数可在同一段正文里用 `/([\d.]+)\s*分/` 抓。

`submit` 失败先 `shot` 看现场，**不要盲目重试**——有次数的作业会被扣次数。已提交页的「重做」按钮**绝不点**（会作废本次成绩）。

## 提交后必做：批阅复盘

`run.sh review`（在 `/mooc2/work/view` 详情页执行）读每题的：

- `.stuAnswerContent` 我的答案
- `.rightAnswerContent` 正确答案
- `.totalScore` 得分

输出 `cx_review.json` 与错题清单。**这是唯一可靠的错题来源**——平台不一定会通知，而「分数」只能告诉你有几题错。

价值：
- 当场知道自己错在哪，便于向用户如实汇报，而不是含糊说「分数 86.7」。
- 长期积累能发现**出题人口径**问题（见下节），下次同类题可直接按课程口径作答。

## 出题口径：教科书常识 ≠ 本题答案

实测三例，都是「知识点没错、但按出题人口径答错」：

| 题 | 常规理解 | 本题标准答案 | 说明 |
| --- | --- | --- | --- |
| 「大部分主要的 Linux 系统文件存放在？」 | `/lib`（库文件） | **`/bin`** | 题中「系统文件」指**可执行程序**；/lib 是共享库 |
| 「哪个定义了系统日志文件？」 | `/var/log/messages` | **`/etc/syslog.conf`** | 问的是「定义（配置）」，不是日志本身 |
| 「列出当前目录及子目录下所有 .txt」 | `find . -name "*.txt"` | **`ls *.txt`** | 选项里没有正确写法，只能选「最接近」的；D `find . ".txt"` 语法残缺 |

启示：
1. 选项里**没有完全正确的答案**时，选「出题人最可能想考的那条最简命令」，不要选语法最严谨但选项残缺的那条。
2. 遇到 `/bin` vs `/lib`、日志「文件」vs「配置文件」这类成对概念，按**题面动词**判断（「存放文件」→ 内容；「定义」→ 配置）。
3. 同一课程的多份作业会重复考同一批知识点，**复盘结果要回填到后续作业的判断里**。

## 交卷前必查

1. `verify` 的 `pending` 为空；
2. 每题 `chosen` 字母与答案一致（不是 value）；
3. 文本题的 `textLen` 合理（简答一般 ≥80 字，填空 ≥1）；
4. `shot` 肉眼扫一遍有没有渲染异常、题目折叠未加载。
