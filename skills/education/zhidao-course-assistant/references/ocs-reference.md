# OCS 网课助手调研记录

调研日期：2026-11-21。资料来源：GitHub 仓库 API、raw 源码、项目内 `CLAUDE.md` 指向的 `project-context.md`、官方文档站首页。

> **阅读范围说明**：`packages/scripts/src/projects/zhs.ts` 全文约 82,671 字符，本次只取到前约 15,000 字符的摘录（含处理器类定义与 `ZHSProject` 导出开头）；`common.ts`、`zhs.configs.ts`、`study.ts`、`project-context.md`、README 为完整读取。以下结论均基于上述已读部分，未通读 `zhs.ts` 全文，不作全文性断言。

## 一、项目清单

| 仓库 | 定位 | 关键事实 |
| --- | --- | --- |
| https://github.com/ocsjs/ocsjs | OCS 网课助手主脚本（油猴 / 脚本猫） | 5.1k stars、367 forks、TypeScript、MIT、默认分支 `5.0`；描述明确支持超星、知道智慧树、职教云、智慧职教、中国大学 MOOC |
| https://github.com/ocsjs/ocs-desktop | OCS 桌面端 | 263 stars、TypeScript；Electron + Vue 3 + Playwright 的用户脚本一键启动器，支持浏览器多开/分身、自动安装用户脚本 |
| https://github.com/ocsjs/ocs-docs | 官方文档仓库 | MIT |
| https://docs.ocsjs.com | 官网/文档 | 平台列表、桌面端教程、题库与脚本说明 |

`ocs-desktop` 的 README 自述功能：一键刷课、多账号刷课、浏览器多开/分身、浏览器管理、自动登录，支持 Windows / Linux / macOS。其 `project-context.md` 记录的核心机制包括：Playwright `launchPersistentContext` + 独立 `userDataDir`、用户脚本自动安装更新、vm 沙盒 + Proxy 权限体系（`page:read` / `page:write` / `network` / `storage`）、ddddocr 验证码识别、**Playwright 定时截图写盘后由本地服务器提供**的浏览器监控、Electron + Vue 3 双模式界面。

> 注意：`ocs-desktop` 仓库 API 未返回 license 字段，**不要声称它是 MIT**；明确 MIT 的是 `ocsjs/ocsjs` 与 `ocsjs/ocs-docs`。

## 二、与本技能直接相关的发现

1. **`polymas.com` 就是 OCS 的适配域名**。`ZHSProject = Project.create({ name: '知到智慧树', domains: ['zhihuishu.com', 'polymas.com'], ... })`，`polymas.com` 的注释是「2025下半学期新系统: AI智慧课程」。这印证了实跑结论：AI智慧课程中心属于智慧树体系。
2. **有专门的 Hike 处理器**。`class Hike`（注释「2025-9月份教学空间-AI智慧学习页面，新系统」）用 `.source-icon` 判断 `hasJob()`、用 `i.select` 过滤已完成、用 `.active-file` 定位当前；`class HikeV2` 用 `.el-tree-node` + `label.success` + `.is-current`。说明该站点至少存在两版 UI，且 OCS 也是按版本分别适配。
3. **智慧树 MOOC 学习页在 OCS 里被单列**。`remote_not_required_pages` 含 `wisdom-mooc.zhihuishu.com`；`skipStudyTimeWarnDialog` 的注释明确写「新智慧学习页面 (`wisdom-mooc.zhihuishu.com/study/index`)」并说明会有**习惯分/学习时长提示弹窗**——可作为本技能 `DIALOG` 的一个候选类型（尚未实跑确认）。`WishdomH5` 处理器针对该页，用 `.chapter-content .chapter-item`、`.finish-icon`、`.current` 组织任务列表。
4. **统一处理器接口 `ZHSProcessor`**：`getCourseName()` / `getChapterName()` / `hasJob()` / `getNext({ next, restudy })` / `hideDialog()` / `handleTestDialog()` / `switchPlaybackRate()`；按 UI 版本实现 `StudyVideoH5`、`FusionCourseH5`、`StudyPlusH5`、`WishdomH5`、`Hike`、`HikeV2`。
5. **`getNext` 的连播抽象**（各处理器同名同构）：取任务节点列表 → 若非 `restudy`，过滤掉已完成项（`.time_icofinish` / `.isFinish` / `.finish-icon` / `label.success` / `i.select` / `progress-num === '100%'` / 进度 `必学 x/y` 已满）→ 找到当前项（`.current_play` / `.current` / `.activeNode` / `.active-file` / `.is-current`）→ 返回其后一项；找不到则返回列表首个。列表为空即无待学任务。
6. **配置是声明式的 `Config` 对象**，按命名空间收敛（`zhs.study`），设置中心与运行脚本共享同一份值。与播放相关的默认值（`utils/zhs.configs.ts`）：

   | 配置 | 默认值 | 备注 |
   | --- | --- | --- |
   | `playbackRate` | `1` | 选项仅 1 / 1.25 / 1.5，注释「智慧树倍速最高只能 1.5x，超出有封号风险」 |
   | `reloadWhenError` | `true` | 视频黑屏/加载失败自动刷新 3 次 |
   | `stopTime` | `'0'`（关闭） | 可选 0.5h / 1h / 2h 定时停止 |
   | `switchMode` | `'job'` | 只跳必学章节 vs 顺序跳转 |
   | `skipStudyTimeWarnDialog` | `false` | 忽略习惯分弹窗 |
   | `volume` / `definition` / `restudy` | 定义在 `utils/configs.ts` 并引入设置中心 | 音量/清晰度/复习模式 |

7. **等待与轮询工具**（`utils/study.ts`）：`waitForMedia()` 每 200ms 探测 `video`/`audio`，默认 3 分钟超时；`waitFor()` 默认 1000ms 轮询，带 `isRunning` 防重入、`cleanup()` 统一清理、可选 `timeout_seconds` 与 `timeout_message`。`waitForElement()` 支持「探测式等待」（`.catch(() => undefined)`）与「必须存在」两种用法。
8. **进度统计原则**（`common.ts`）：`count(results)` 从结果数组派生 `total / requested / resolved`，注释写明「计数一律由结果数组派生，不单独存储，避免与结果数据不同步」。
9. **通知分级**（`common.ts`）：`only-notify` / `notify-and-voice` / `all` / `no-notify`，说明「只有重要事情发生时会发送系统通知，尽量避免用户受到骚扰」。
10. **环境约束提示**（`zhs.configs.ts` 的 `studyNotes`）：不要最小化浏览器/关闭屏幕（可能导致脚本暂停）；浏览器缩放建议调到合适大小（如 50%）避免元素遮挡无法点击；章节测验/掌握度需观看完视频后手动打开；兴趣课会自动下一个，不提供脚本。
11. **桌面端监控也走截图**：`project-context.md` 记载「浏览器监控改为 Playwright 定时截图（写盘后由本地服务器提供）」——与本技能「截图识别 + 坐标点击」的观察循环思路一致，可作为该路线可行性的旁证。

## 三、借鉴清单（已落到本技能）

| OCS 做法 | 落到本技能的位置 |
| --- | --- |
| `Project{domains}` + `Script{matches}` 按域名/页面路由 | 「站点分工」+「按页面版本分派」：先判页面版本再选信号来源，不写死一套选择器 |
| `ZHSProcessor` 统一接口 | 「按页面版本分派」的职责映射表（`hasJob` / `getNext` / `hideDialog` / 名称读取） |
| `getNext` 过滤已完成 + 定位当前 + 取下一项 | 第 3 步 `ENDED` 动作、`ALL_DONE` 判定 |
| `restudy` 默认关闭、只跳未完成项 | 「默认参数」新增复习模式；强化「不重播已完成视频」 |
| `reloadWhenError`、`stopTime` | 「默认参数」新增异常自动刷新（上限 2 次）；单次最长运行 120 分钟 |
| `waitFor` 防重入 + 超时 | 观察循环「上一轮未结束不启动下一轮」、`UNKNOWN` 连续上限 |
| 进度由记录数组派生 | `ledger.py summary` 的设计原则（不从独立计数字段取数） |
| 分级通知、仅重要事件提醒 | 「进度台账与提醒」：汇总与提醒放在收尾/异常时，不逐轮打扰 |
| 不要最小化、注意缩放 | 「状态判定」与「失败处理」里对后台播放、坐标点击怕分辨率变化的谨慎表述 |

## 四、明确不借鉴（对照硬性边界）

| OCS 具备的能力 | 本技能的处理 |
| --- | --- |
| 自动答题、题库接口、在线搜题、随机选项、按提交率自动交卷 | **排除**。代答计分测验 / 作业 / 考试；遇计分考核、「测试」节点立即停、零点击。新增的答题辅助只对非计分练习按可见 DOM 逐题点击填写，不调用题库 / 搜题接口、不随机选项、不自动交卷，见 `answer-assist.md` |
| `handleTestDialog()` 随机选项并关闭/提交弹窗测验 | **排除**。`VERIFICATION` 优先，不做任何点击 |
| ddddocr 验证码识别、滑块破解 | **排除**。不绕过验证码、人脸/摄像头 |
| 官网自述「可绕过智慧树、中国大学 MOOC 的脚本检测」 | **排除**。不绕过风控校验 |
| 多账号、浏览器多开/分身、自动登录、凭据加密保存 | **排除**。单会话、用户本人手动登录、不读不存账号密码 |
| 倍速 > 1.5x（部分平台通用配置最高 16x） | **排除**。OCS 自身标注封号风险，本技能不做倍速干预 |
| 页面内注入 JS、CSS 选择器取元素、篡改播放器属性与心跳 | **排除且技术上做不到**。浏览器工具无 `evaluate` / `execute_script` |

**本技能不包含 OCS 的任何源码**，只借鉴了工程组织方式。参考项目的能力范围不代表本技能的许可范围，一切以 `SKILL.md` 的「硬性边界」为准。

## 五、来自源码的候选线索（未验证，不可直接当依据）

以下是 OCS 源码里的选择器/文案，**未经本技能实跑确认**，且本技能无 JS 能力、不能按 CSS 选择器取元素，因此仅作为将来有未完成视频课程时的观察线索：

- 完成标记候选：`.finish-icon`、`.isFinish`、`.time_icofinish`、`label.success`、`i.select`、进度 `100%`、`必学 x/y`。本技能实跑已确认的是**截图上的圆形 ✓ 勾选**，两者是否对应未验证。
- 当前项候选：`.current`、`.current_play`、`.activeNode`、`.active-file`、`.is-current`。
- 任务列表候选：`.chapter-content .chapter-item`、`.clearfix.video`、`.resources-item`、`.source-icon`、`.el-tree-node`。
- 弹窗候选：习惯分/学习时长提示、`.el-dialog__wrapper`、`.el-overlay`、`.ai-class-exercise-dialog`（后者属考核类，**命中即停**，不得关闭）。
- 页面分版线索：`Hike` 与 `HikeV2` 并存，说明 polymas 侧至少有新旧两版 DOM；本技能遇到认不出的结构一律 `UNKNOWN`。

> 使用规则：这些线索只能用来**指导看什么**，不能用来**代替观察结果**。任何写入 `site-notes.md`「已确认」栏的内容，必须来自本技能自己的实跑截图或 DOM 快照。
