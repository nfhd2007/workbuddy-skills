# 实战清单：从训练列表一路到作答

> 2026-11-21 已用真实听力训练卷跑通全流程，坐标见 `itest-ui.md`。
> 原则：**一屏一确认，绝不交卷**。交卷只由用户自己点。
> 听力卷若要让助手「听」：见 `audio-capture.md`（回环录制 + 云端转写，实验性，仅训练卷，首次只做纯录音演练）。

## 〇、动手前

```bash
cd ~/.workbuddy/skills/itest-assistant
scripts/run.sh info          # 必须看到 2560x1600；若是 1707x1067 说明 act.ps1 丢了 BOM
scripts/run.sh activate --title iTEST
scripts/run.sh key --combo "win+up"     # 最大化，坐标才稳定
scripts/run.sh shot --out shots/p0.png
```

`info` 里 `primaryScreen` 不是 2560×1600 就停下修 BOM（见文末故障表）。

看 `p0.png` 确认：

1. 页面是不是「训练 - 模考训练」，目标试卷名称对不对；
2. 有没有「考试码 / 监考 / 人脸识别 / 抓拍」——**有就停**，不自动作答；
3. iTEST 是否完整可见（没被 WorkBuddy 盖住）；
4. **顶部计时条是倒计时还是正向计时**（每卷重判，别沿用上一卷结论）。

**限时卷开场三步**（判定为倒计时后立刻做，完整口径见 `references/timed-mode.md`）：

```bash
scripts/run.sh clock --screen shots/screen1.json   # 把读图得到的计时快照落盘
scripts/run.sh budget --answered 0                 # 看 [MODE=...]
```

之后**每一屏循环开头都跑一次** `budget --answered <已答题数>`，照 `[MODE=...]` 执行：

| 模式 | 怎么做 |
| --- | --- |
| `full` | 时间充裕，走完整流水线 |
| `timed` | 砍掉双答案交叉、文本多轮打磨、逐屏复核，优先保覆盖率；抽样复核保留 |
| `rescue` | 所有未答题先给最优解**保底填满**，存疑题标注后补，不留空 |

归零平台会自动交卷、未答题直接空白。看到 `[ACTION_REQUIRED]` 必须立刻告知用户剩余时间、未答题数与自动交卷风险；是否主动交卷由用户明确同意。限时下**不要启动听力回环录制**（整卷实测 41 分钟）。

## 一、进入答题页（训练卷实测路径）

| 步 | 页面 | 点什么 | 备注 |
| --- | --- | --- | --- |
| 1 | 模考训练列表 | 试卷行「继续模考」 | 坐标见 itest-ui.md |
| 2 | 个人信息确认 / 须知 | 「下一步」 | 提醒用户核对学号姓名 |
| 3 | 键盘检测 | 点输入框 → 打几个字 → 「检查正常」 | 不输入时按钮是禁用的 |
| 4 | 耳机检测 | 点播放 → 等 28 秒 → 「检查正常」 | 问用户"听得到吗"，听不到就别替他通过 |
| 5 | 考试信息 | 「开始考试」 | 每次先重新截图，窗口位置会变 |
| 6 | 加载成功 | 「确定」 | |

**每一步点完都 `shot` 确认页面真的前进了。** 上一屏的坐标不能拿到下一屏用——第 2～5 步是弹出窗口，位置会移动。

**麦克风**：Section B/C 或翻页时可能要求麦克风。**不代点「允许」**，问用户。

## 二、每一屏怎么作答

```bash
scripts/run.sh shot --out shots/p1.png        # 先看图
```

按截图写 `shots/screenN.json`（结构见 `assets/screen.example.json`），然后：

```bash
scripts/run.sh guard  --screen shots/screenN.json           # 红线
scripts/run.sh fill   --screen shots/screenN.json --answers answers.json --dry
scripts/run.sh fill   --screen shots/screenN.json --answers answers.json
scripts/run.sh shot   --out shots/after1.png                # 复核：勾亮没亮
```

**第一屏必须人工看图复核**，确认落点准了再往下。

### 翻屏

**用答题卡跳题，不要用「下一题」。**
实测「下一题」点 4 次都没反应；答题卡点题号 100% 生效（跳转后自动收起）。

```bash
scripts/run.sh click --x 1078 --y 135     # 开答题卡
scripts/run.sh click --x 958  --y 301     # 点 3 号题 → 跳到第 3-4 题
```

题号坐标：**第十节全卷实战重新标定为间距 60px**（Section A 首格 (846,307)，B (846,436)，C (846,564)）。第三节早期记录的 55px 已废弃，用 55 会偏 26px 直接落空；以当前截图重新量为准。

### 听力题

- 顶部「点击开始听力考试」@ (1232, 319) 才开始播放。
- **播放中页面锁定在音频对应题，只观察不操作**，容易点错题。
- 听不到音频 → 答案只能由用户给，助手只负责填。

### 填空题族（选词填空 / 段落信息匹配 / 短文填词）

一屏一空 + 「请输入答案…」的题，**先读 `references/question-types.md`**，然后：

1. 把短文全文、词库 A–O、段落 A–O 收齐（多张截图先拼成完整文本），**整篇一次解完再逐屏填**。
2. 建 `屏幕题号 | 文中空号 | 答案 | 依据` 映射表；`inputs[].no` 用屏幕题号，`1/10` 进度和文中空号都不是题号。
3. 有词库填字母，有段落标号填段落字母，句内空无词库填一个单词并核对词形。
4. 判完另存 `check.json` 跑 `node scripts/answercheck.js check.json --partial`，退出码 0 才进 `fill`。
5. 逐屏截图复核字母/单词有没有落进输入框；存疑题列给用户，不硬猜。

## 三、文本题（翻译 / 写作）

```bash
node scripts/textcheck.js answers/q41.txt    # 退出码 0 才继续
```

最多改 3 轮，术语/数字/结论不动。

## 四、交卷（默认不做）

```bash
scripts/run.sh submit --screen shots/screenN.json        # dry-run，只报坐标
```

**只有用户明确说"交"才加 `--yes`。** 训练卷可重做、正式考试不可，交前一定再问一次。

## 五、复盘

能看报告就截图读错题；提示「考试尚未结束，无法查看成绩」就如实说，不猜分数。

## 六、收尾：交卷后报告 + 询问

走 `submit --yes` 交卷时，命令末尾会**自动**打印「录音占用报告」并输出 `[ACTION_REQUIRED]`。看到后：

1. 把文件数和合计大小告诉用户；
2. 用 AskUserQuestion 询问：`全部删除` / `保留最新一份` / `不删`；
3. 只有答"删"才执行对应命令，其余什么都不做。

| 回答 | 命令 |
| --- | --- |
| 全部删除 | `scripts/run.sh cleanup --apply` |
| 保留最新一份 | `scripts/run.sh cleanup --keep 1 --apply` |
| 不删 / 未回答 | 不执行 |

用户自己点交卷时，主动补跑 `scripts/run.sh postsubmit` 再走上面流程。**报告绝不删文件**。详见 `audio-capture.md`。

## 常见故障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `run.sh info` 报 `动作失败：{}` | `act.ps1` 丢了 UTF-8 BOM，中文被 GBK 打散 | 用 PowerShell 转成 UTF8Encoding($true)，再跑 info 验证 |
| `info` 显示 1707×1067 | 同上是 BOM 丢失，DPI 声明没生效 | 同上 |
| 点击完全没反应 | ① 窗口未聚焦（首次点击只激活）② 坐标来自旧截图 | 再点一次；重新 `shot` 取坐标 |
| 截图里是 WorkBuddy | iTEST 被遮挡 | `activate` 后重截 |
| 「下一题」点不动 | 该按钮本身不响应（实测 4 次） | 改用答题卡跳题 |
| 弹「未检测到麦克风」 | 浏览器未授权麦克风 | 问用户是否允许，不自作主张 |
| 选项点了不变色 | 点到了行外 | 点圆点 (x≈673) 或行中心 |
| UIA 坐标差几百像素 | 窗口非最大化 / 被移动 | 最大化后重跑 UIA，仅做文字校对 |
| 字没进输入框 | 点在框外或只读 | 重新截图确认框位置 |
| `cleanup` 说「疑似仍在录制」 | 文件 60 秒内刚写入 | 等录制结束再跑，或确认后加 `--force` |
| 交卷后没弹录音报告 | `submit` 是 dry-run（没加 `--yes`），或用户自己点的交卷 | 手动跑 `scripts/run.sh postsubmit` |
| `budget` 说没有 `shots/clock.json` | 首屏没跑 `clock` | 读图判定倒计时 / 正向计时后跑 `clock --screen shots/screen1.json` |
| 倒计时快归零、还有题没填 | 时间预算不足 | 照 `[MODE=rescue]` 先保底填满、存疑后补，立刻告知用户；是否主动交卷由用户明确同意 |
| 换了新卷但 `budget` 仍显示上一卷的 rescue | 节奏与模式没重置 | 跑 `clock --screen ... --reset`，会清空节奏样本与旧模式 |
