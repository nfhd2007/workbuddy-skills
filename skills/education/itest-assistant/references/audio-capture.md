# 听力音频采集（实验性，可行性已验证）

目的：把「听」翻译成「读」。录制系统正在播放的数字音频 → 转写成英文逐字稿 → 我读文字判断答案 → 复用已标定坐标点选。

## 边界（不可逾越）

- **只录「已经从渲染端点播放出来的声音」**，等价于把录音笔放在音箱旁。不改网页、不读 `<audio>` 元素、不翻网络请求、不下载受保护的音频文件、不绕过任何鉴权。
- **仅用于训练 / 模考卷**。正式考试一旦出现监考、人脸识别、抓拍、考试码，按 `SKILL.md` 安全边界直接拒绝自动作答，不因技术可行而放宽。
- 2026-11-21 已完成可行性验证，并在「四级听力模拟题（三）」整卷 25 题上实战跑通（见下方「全卷实战」）。链路仍是实验性的：逐屏坐标靠 `uia` 现取，未固化成自动命令。

## 依赖与设备

```bash
pip install soundcard        # 已装：soundcard 0.4.6 + numpy 2.5.5 + cffi 2.1.1（Python 3.13.14）
```

WASAPI 回环，**不需要**「立体声混音」设备，也不需要 ffmpeg。

实测 `record --list` 结果：

| 类型 | 设备名 | 说明 |
|---|---|---|
| 默认输出 / loopback | `耳机 (Lenovo EH140)` | 蓝牙耳机，当前默认输出 |
| loopback | `扬声器 (Senary Audio)` | 板载声卡 |
| 真麦克风 | `麦克风阵列 (英特尔智音技术)`、`耳机 (Lenovo EH140)` | 本方案不用 |

## 命令

```bash
# 列出回环设备
bash scripts/run.sh record --list

# 边播边录：录制开始后异步播放指定 wav，录满 N 秒
bash scripts/run.sh record --out audio/cap.wav --seconds 17 --play audio/ref.wav

# 指定回环设备（默认跟随系统默认输出）
bash scripts/run.sh record --out audio/cap.wav --seconds 60 --device "Senary"
```

输出 JSON 含 `peak` / `rms` / `nonzero_ratio` / `silence`，用来判断「到底录到没有」。`silence: false` 才算成功。

## 验证记录（2026-11-21）

**参照音频**：用 Windows SAPI 的 `Microsoft Zira Desktop - English (United States)` 合成，22.05kHz / 16bit / 单声道 / 14.14 秒。原文：

> Excuse me, could you tell me when the next train to Boston leaves? I am afraid the eight thirty has just been cancelled because of the storm. However, there is another one at nine fifteen from platform six.

刻意放进 `8:30` / `9:15` / `Boston` / `platform six` 这些四级听力易错点。

**回环录制结果**（默认输出 = 蓝牙耳机 `Lenovo EH140`）：

| 指标 | 值 |
|---|---|
| 采样 | 48kHz / 双声道 / 17 秒 |
| peak | 0.6718 |
| rms | 0.0861 |
| nonzero_ratio | 0.638 |
| silence | `false` |

录制时出现两次 `SoundcardRuntimeWarning: data discontinuity in recording`，但波形完整、转写结果未受影响，可忽略。若后续出现大面积断续，优先改用 `--device "Senary"` 板载端点。

**关键发现**：用户当时**听不到**这副蓝牙耳机（默认输出被抢占），但回环照样录到了完整音频——**耳朵收不到 ≠ 数字流抓不到**。这两件事互不干扰，也正好解释了为什么听不到不影响本方案。

## 转写引擎择优结论：用云端工具

对同一个 `cap.wav` 的转写结果：

```
[0:00.15–0:03.90] Excuse me, could you tell me when the next train to Boston leaves?
[0:04.62–0:08.32] I am afraid the 830 has just been cancelled because of the storm.
[0:09.14–0:13.24] However, there is another one at 915 from platform six.
```

- 逐字命中，仅数字写法不同（`eight thirty`→`830`、`nine fifteen`→`915`），语义完全一致。
- **自带时间戳分段**，直接解决「音频片段 ↔ 题号」对齐问题，不必自己写对齐逻辑。
- 直接吃 48kHz 双声道 wav，无需预转换；支持 wav/mp3/m4a/flac 等，最长 5 小时。
- 零安装成本。

**本地 FunASR 在这台 Windows 上不可用**（不是「装个包」能解决的）：

| 阻碍 | 说明 |
|---|---|
| `import fcntl` | `transcribe.py` 顶部硬依赖，Windows 无此模块，实测 `ModuleNotFoundError` |
| `/tmp/funasr_locks` | 锁目录写死 Unix 路径 |
| `ffmpeg` 切片段 | 脚本第 169 行调用，本机没有 ffmpeg |
| 依赖全缺 | funasr / onnxruntime / psutil / soundfile / librosa / torch / modelscope 均未安装 |
| 模型 | 首次还要下载 SenseVoiceSmall ~500MB（且是中小模型，英文连读/数字未必优于云端） |

结论：训练卷听力音频不涉及敏感隐私，本地化的收益不足以覆盖改造成本。**保留本地方案作为「音频不出本机」场景的备选，但需先重写 Windows 兼容层。**

## 接入答题流水线前的三个硬限制

1. **听力一次性顺序播放，不能暂停回放**。录砸了补不回来。第一次实战必须只做纯录音演练：不答题、不判断、不提交。
2. **ASR 会错**：数字、地名、连读弱读容易转错；`What does the man imply?` 这类弦外之音题，有逐字稿也不等于有答案。没把握的题必须标出来交用户定，不硬猜。
3. **准确率预期**：点选项那步是 100% 机械准确；「听懂 → 选对」是辅助判断，明显低于客观题自动填写，回报时要分开说。

## 全卷实战（2026-11-21 上午）

四级听力模拟题（三）25 题，整卷跑通：

| 项 | 实测 |
|---|---|
| 录制 | 41 分钟、48kHz 单声道、226MB、peak 0.816 / rms 0.058 / 非静音 |
| 转写 | 完整覆盖 Section A/B/C，含 Directions、全文与每道题的提问句，**时间戳可直接定位题号** |
| 时间轴 | A 第 1 遍 0:08–6:25、重复段 8:00–14:17、B 18:50–25:07、C 28:14–38:19 |
| 作答 | 25 题全部填完，答题卡全绿，**全程未交卷** |

**听力是分 Section 播的**：每次点「点击开始听力考试」只播当前 Section，播完停在原地、不自动续播；要先用答题卡切到下一 Section 的题号（8 / 16），再点播放。标签仍是 Section A 时点播放会从头重播（实测白录 7 分钟）。

答案依据逐字稿判断，**不是真实听觉**。25 题里 23 题把握较大，Q5、Q7 存疑，已在 `itest-ui.md` 注明依据与分歧点。

## 交卷后自动报告 + 询问

交卷一成功，`submit --yes` 末尾会自动调用 `postsubmit`，打印录音清单与合计大小，并输出 `[ACTION_REQUIRED]` 标记。**它只统计，不删任何文件。** 命令行无法向人提问，所以由模型读到标记后用 AskUserQuestion 询问用户，按回答执行：

| 用户回答 | 执行 |
| --- | --- |
| 全部删除 | `scripts/run.sh cleanup --apply` |
| 保留最新一份 | `scripts/run.sh cleanup --keep 1 --apply` |
| 不删 / 未回答 | 什么都不做 |

用户若自己点交卷（没走 `submit`），助手确认页面已交卷后主动跑一次 `postsubmit`，同样走询问流程。报告同时写入 `shots/postsubmit.json`（`stage` / `fileCount` / `totalBytes` / `totalHuman` / `files[]` / `willDelete: false`），便于模型读取。

## 做完题后清理录音

整卷复核通过、确认不再需要回听后，用 `cleanup` 释放空间（一整卷约 226MB）：

```bash
scripts/run.sh cleanup                                    # 默认 dry-run：列清单 + 合计大小，不删
scripts/run.sh cleanup --keep 1                           # 保留最新一份，其余列入删除计划
scripts/run.sh cleanup --apply                            # 显式确认后才真删
scripts/run.sh cleanup --file paper_20261121.wav --apply  # 只删指定文件
```

| 参数 | 作用 |
| --- | --- |
| 无 | dry-run 预览，**不删任何文件** |
| `--apply` | 真正执行删除（唯一会删文件的开关） |
| `--keep N` | 按修改时间保留最新 N 份，便于回听复核 |
| `--file f.wav` | 只处理这一个文件，值必须是纯文件名 |
| `--force` | 跳过「60 秒内刚写入」保护 |

安全设计：只认技能目录 `audio/` 内的 `.wav` 普通文件；不递归子目录、不删目录本身、不接受带路径的 `--file`（防路径穿越）、排除符号链接；60 秒内刚写入的文件默认跳过，避免删掉仍在录制的音频。删除后逐一校验并报告释放空间。

**为什么自动报告但不自动删**：删除不可恢复，而 ASR 转错的题（数字、连读、弦外之音）常常还要回听原文核对。所以 `submit` 只自动出报告 + 触发询问，删除必须由用户确认后显式执行。`lint.js` 有三条自检：`cleanup` 必须默认 dry-run、`postsubmit` 不得含删除操作、`submit` 必须联动 `postsubmit`。

## 尚未完成

- 未接入 `itest.js` 的 `fill / verify` 流水线（本次是逐屏 `uia` 取坐标 + 手工点选）。
- 交卷弹层未标定（按用户要求不提交）。
- 未验证超长音频（>1 小时）的转写稳定性。
