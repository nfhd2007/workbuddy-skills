#!/usr/bin/env node
'use strict';
/**
 * itest.js — iTEST（爱考试 / Unipus）考试助手 · 桌面操控编排层
 *
 * 为什么不用 CDP：iTEST 作答页有切屏监测，重启浏览器会丢作答状态；
 * 桌面操控可以接管用户当前已登录、已打开的页面。代价是读题靠视觉、
 * 每屏都要起 PowerShell + 截图 + 模型读图，单屏开销不小，
 * 所以限时卷必须做时间预算与分档（见 references/timed-mode.md）。
 *
 * 脚本只做确定性动作（截图、点坐标、粘贴、按键、批量执行）。
 * 读题与判题由模型看截图 / 无障碍树完成，产出两份文件：
 *   screen.json  —— 当前这一屏的题目、选项坐标、输入框坐标、导航按钮坐标、timer 计时快照
 *   answers.json —— 题号 → 答案
 *
 * 子命令：
 *   info                                    前台窗口 / 光标 / 屏幕尺寸
 *   shot   --out f [--region x,y,w,h]       截图（整屏或区域）
 *   click  --x N --y N [--clicks 1]         点一下
 *   type   --text "..." [--raw]             输入文本（默认剪贴板粘贴）
 *   key    --combo "ctrl+a"                 按键组合，可重复 --combo
 *   activate [--title iTEST]                把 iTEST 窗口带到前台
 *   uia    --out f [--title iTEST]          导出无障碍树（文本 + 坐标）
 *   clock  --screen s.json | --mode M --remaining N [--total T] [--answered A] [--reset]
 *                                       记录计时快照到 shots/clock.json（倒计时 / 正向计时 / 未知）
 *                                       --reset 或换卷（形态变化 / 距上次 >2h）会重置节奏与模式
 *   budget [--answered N] [--screens N]    算剩余 / 已用 / 每题均耗 / 预计还需，输出 [MODE=...]
 *   guard  --screen s.json                  检查正式考试红线特征 + 附带限时模式提示
 *   fill   --screen s.json --answers a.json [--dry]   按坐标批量作答
 *   verify --screen s.json --answers a.json           检查答案是否落在当前屏
 *   next   --screen s.json                  点「下一题」
 *   submit --screen s.json [--yes]          点交卷（默认 dry-run；--yes 才真点）
 *   postsubmit [--out f.json]            交卷后报告录音大小 + 输出待询问标记（绝不删文件）
 *   cleanup [--file f.wav] [--keep N] [--apply] [--force]
 *                                       做完题后清理 audio/ 录音（默认 dry-run；--apply 才真删）
 *
 * 环境变量：ITEST_PS（PowerShell 路径）、ITEST_TITLE（窗口标题关键字，默认 iTEST）
 */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const PS = process.env.ITEST_PS ||
  path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
const ACT = path.join(__dirname, 'act.ps1');
const UIA = path.join(__dirname, 'uia.ps1');
const TITLE = process.env.ITEST_TITLE || 'iTEST';

// 正式考试红线：出现这些词，停止自动作答/提交（不提供绕过开关）
const RED_FLAG_RE = /监考|考试码|人脸识别|人脸抓拍|屏幕抓拍|切屏抓拍|随机抓拍/;

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > -1 ? process.argv[i + 1] : d; };
const has = (n) => process.argv.includes('--' + n);

function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function runPs(script, op, payload, timeout = 120000) {
  const args = ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script];
  if (op) args.push('-Op', op);
  const r = spawnSync(PS, args, {
    input: JSON.stringify(payload || {}),
    encoding: 'utf8',
    timeout,
    maxBuffer: 16 * 1024 * 1024,
  });
  if (r.error) throw r.error;
  const out = (r.stdout || '').replace(/^\uFEFF/, '').trim();
  const last = out.split(/\r?\n/).filter(Boolean).pop() || '{}';
  let j;
  try { j = JSON.parse(last); } catch (e) {
    throw new Error(`脚本返回非 JSON：${out.slice(0, 400)} ${(r.stderr || '').slice(0, 400)}`);
  }
  if (!j.ok) throw new Error(`动作失败：${JSON.stringify(j)}`);
  return j;
}

const act = (op, payload) => runPs(ACT, op, payload);

function must(p, hint) {
  const abs = path.resolve(p);
  if (!fs.existsSync(abs)) throw new Error(`找不到文件 ${abs}${hint ? ' —— ' + hint : ''}`);
  return JSON.parse(fs.readFileSync(abs, 'utf8'));
}

function saveJson(p, data) {
  const abs = path.resolve(p);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, JSON.stringify(data, null, 1), 'utf8');
  return abs;
}

/** 把 screen.json 里的可见文字拼起来，做红线判断 */
function screenText(screen) {
  const parts = [screen.text || ''];
  for (const q of screen.questions || []) {
    parts.push(q.stem || '');
    for (const o of q.options || []) parts.push(o.text || '');
  }
  return parts.join('\n');
}

/* ---------------- 限时周测：计时快照 / 时间预算 / 分档 ---------------- */
const CLOCK_FILE = () => path.resolve('shots/clock.json');
const BUDGET_FILE = () => path.resolve('shots/budget.json');
const PACE_FILE = () => path.resolve('shots/pace.json');

// 预计耗时 = 未答题数 × 每题均耗 × 安全系数；缓冲留给弹层 / 网络 / 平台自动交卷
const SAFETY_FACTOR = 1.4;
const MODE_RATIO = 1.5;
const MODE_ORDER = { full: 0, timed: 1, rescue: 2 };

function readJsonIfExists(p, fallback) {
  try {
    const abs = path.resolve(p);
    if (!fs.existsSync(abs)) return fallback;
    return JSON.parse(fs.readFileSync(abs, 'utf8'));
  } catch (_) { return fallback; }
}

function fmtClock(s) {
  const n = Math.max(0, Math.round(Number(s) || 0));
  const h = Math.floor(n / 3600);
  const m = Math.floor((n % 3600) / 60);
  const sec = n % 60;
  const pad = (v) => String(v).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

/**
 * clock：把「读图得到的计时快照」落盘。首屏一次即可，
 * 之后 budget 用 deadlineAt - now 推算剩余，不必每屏重读秒数。
 * 优先取 screen.json 的 timer 字段，命令行参数兜底。
 */
function cmdClock() {
  const screenPath = arg('screen');
  const t = screenPath && fs.existsSync(path.resolve(screenPath))
    ? (must(screenPath).timer || {})
    : {};
  const mode = String(arg('mode', t.mode || 'unknown')).toLowerCase();
  if (!['countdown', 'countup', 'unknown'].includes(mode)) {
    throw new Error('--mode 只能是 countdown / countup / unknown');
  }
  const remaining = Number(arg('remaining', t.remainingSeconds));
  const total = Number(arg('total', t.totalQuestions || 0)) || 0;
  const answered = Number(arg('answered', t.answeredQuestions || 0)) || 0;
  if (mode === 'countdown' && (!Number.isFinite(remaining) || remaining <= 0)) {
    throw new Error('倒计时必须给 --remaining 秒数（或写进 screen.json 的 timer.remainingSeconds）');
  }

  const prev = readJsonIfExists(CLOCK_FILE(), {});
  const now = Date.now();
  // 显式 --reset、换卷（形态变化）、或距上次开卷超过 2 小时，都视为新卷
  const fresh = has('reset') || !prev.startedAt || prev.mode !== mode ||
    (now - (prev.startedAt || 0) > 2 * 3600 * 1000);
  const snap = {
    mode,
    display: t.display || arg('display', ''),
    remainingSecondsAtCapture: mode === 'countdown' ? Math.round(remaining) : null,
    capturedAt: now,
    startedAt: fresh ? now : prev.startedAt,
    deadlineAt: mode === 'countdown' ? now + Math.round(remaining) * 1000 : null,
    autoSubmit: t.autoSubmit !== undefined ? !!t.autoSubmit : (mode === 'countdown'),
    totalQuestions: total,
    answeredQuestionsAtCapture: answered,
  };
  saveJson(CLOCK_FILE(), snap);
  // 新卷必须同时清空节奏样本与上一卷的模式，否则 rescue 会粘到新的无限时卷上
  if (fresh) {
    saveJson(PACE_FILE(), { startedAt: snap.startedAt, samples: [] });
    saveJson(BUDGET_FILE(), { mode: null, resetAt: stamp(now), reason: 'new-paper' });
    console.log('（已按新卷重置节奏样本与时间预算）');
  }

  console.log('=== 计时快照 ===');
  console.log('形态: ' + {
    countdown: '倒计时（整卷总时钟）',
    countup: '正向计时（无限时）',
    unknown: '未知（按限时保守处理）',
  }[mode]);
  if (mode === 'countdown') {
    console.log(`抓取时剩余: ${fmtClock(remaining)}   推算截止: ${stamp(snap.deadlineAt)}   归零自动交卷: ${snap.autoSubmit ? '是' : '否'}`);
  }
  console.log(`题量: ${total || '未知'}   已答: ${answered}`);
  console.log(`→ ${CLOCK_FILE()}`);
  console.log('下一步：scripts/run.sh budget --answered ' + answered);
  return snap;
}

/** 纯函数：由「剩余 / 预计还需」决定模式，clock / budget / guard 共用 */
function decideMode(clock, remainingSeconds, estimatedNeededSeconds) {
  if (!clock || clock.mode === 'countup') return 'full';
  if (clock.mode === 'unknown') return 'timed';
  if (!Number.isFinite(remainingSeconds) || remainingSeconds <= 0) return 'rescue';
  const buffer = Math.max(90, (estimatedNeededSeconds || 0) * 0.15);
  if (remainingSeconds <= buffer) return 'rescue';
  if (!Number.isFinite(estimatedNeededSeconds)) return 'timed';
  if (remainingSeconds < estimatedNeededSeconds * MODE_RATIO) return 'timed';
  return 'full';
}

/**
 * budget：每一屏循环开头跑一次。用累计进度算每题均耗，
 * 动态估「预计还需」，输出 [MODE=...]。时长不固定，阈值全部动态算，
 * 模式只往更紧的方向切（full → timed → rescue 不回退）。
 */
function cmdBudget() {
  const clock = readJsonIfExists(CLOCK_FILE(), null);
  const answered = Number(arg('answered', 0)) || 0;
  const screens = Number(arg('screens', 0)) || 0;
  const now = Date.now();
  if (!clock) {
    saveJson(BUDGET_FILE(), { mode: 'timed', reason: 'no-clock' });
    console.log('=== 时间预算 ===');
    console.log('没有 shots/clock.json：先跑 clock 记录计时快照。');
    console.log('[MODE=timed] 未判明计时形态前，一律按限时保守处理。');
    console.log('[ACTION_REQUIRED] 读第一张截图判断倒计时 / 正向计时，再跑 clock --screen ...');
    console.log(`→ ${BUDGET_FILE()}`);
    return;
  }

  const elapsed = Math.max(0, (now - (clock.startedAt || clock.capturedAt)) / 1000);
  const remaining = clock.mode === 'countdown' && clock.deadlineAt
    ? Math.max(0, (clock.deadlineAt - now) / 1000)
    : null;
  const total = Number(clock.totalQuestions || 0) || 0;
  const left = total > 0 ? Math.max(0, total - answered) : null;

  const pace = readJsonIfExists(PACE_FILE(), { startedAt: clock.startedAt, samples: [] });
  pace.samples = (pace.samples || []).filter((s) => s && Number.isFinite(s.at));
  pace.samples.push({ at: now, answered, screens });
  if (pace.samples.length > 200) pace.samples = pace.samples.slice(-200);
  saveJson(PACE_FILE(), pace);

  const perQuestion = answered > 0 ? elapsed / answered : null;
  const perScreen = screens > 0 ? elapsed / screens : null;
  let estimated = null;
  if (left !== null && perQuestion) estimated = left * perQuestion * SAFETY_FACTOR;
  else if (perScreen) estimated = 4 * perScreen * SAFETY_FACTOR;
  if (estimated === null) {
    const estScreens = left !== null ? Math.max(1, Math.ceil(left / 2)) : 4;
    estimated = estScreens * 45 * SAFETY_FACTOR;   // 无样本时按每屏 45 秒保守估
  }

  const suggested = decideMode(clock, remaining === null ? Infinity : remaining, estimated);
  const prevMode = readJsonIfExists(BUDGET_FILE(), {}).mode;
  const mode = (prevMode && MODE_ORDER[prevMode] > MODE_ORDER[suggested]) ? prevMode : suggested;

  const report = {
    at: stamp(now),
    timerMode: clock.mode,
    autoSubmit: !!clock.autoSubmit,
    elapsedSeconds: Math.round(elapsed),
    remainingSeconds: remaining === null ? null : Math.round(remaining),
    deadlineAt: clock.deadlineAt ? stamp(clock.deadlineAt) : null,
    totalQuestions: total || null,
    answered,
    questionsLeft: left,
    secondsPerQuestion: perQuestion ? +perQuestion.toFixed(1) : null,
    secondsPerScreen: perScreen ? +perScreen.toFixed(1) : null,
    estimatedNeededSeconds: Math.round(estimated),
    mode,
    suggestedMode: suggested,
    modeSticky: mode !== suggested,
  };
  saveJson(BUDGET_FILE(), report);

  console.log('=== 时间预算 ===');
  console.log('计时形态: ' + {
    countdown: '倒计时（归零自动交卷）',
    countup: '正向计时（无限时）',
    unknown: '未知（按限时保守处理）',
  }[clock.mode] + (clock.deadlineAt ? `   截止: ${stamp(clock.deadlineAt)}` : ''));
  console.log(`剩余: ${remaining === null ? '不适用' : fmtClock(remaining)}   已用: ${fmtClock(elapsed)}   进度: ${answered}${total ? '/' + total : ''} 题`);
  console.log(`每题均耗: ${report.secondsPerQuestion === null ? '样本不足' : report.secondsPerQuestion + 's'}   预计还需: ${fmtClock(estimated)}（含 1.4× 余量）`);
  if (mode !== suggested) console.log(`（本次建议 ${suggested}，但模式只往更紧的方向切，沿用 ${mode}）`);
  console.log(`[MODE=${mode}] ` + {
    full: '时间充裕，走完整流水线（双答案交叉 / 文本量化 / 逐屏复核）',
    timed: '时间偏紧：砍掉质量关卡，优先保覆盖率；详见 references/timed-mode.md',
    rescue: '保底模式：所有未答题先给最优解填满，存疑题标注后补',
  }[mode]);
  if (clock.mode === 'countdown' && (mode === 'rescue' || (remaining !== null && remaining <= 120))) {
    console.log('[ACTION_REQUIRED] 剩余时间不足，平台归零会自动交卷。立刻保底填满并告知用户还有几题未答；是否主动交卷必须由用户明确同意。');
  }
  if (clock.mode === 'unknown') {
    console.log('[ACTION_REQUIRED] 计时形态未判明，重新截图确认倒计时 / 正向计时，再跑 clock --screen ...');
  }
  console.log(`→ ${BUDGET_FILE()}`);
  return report;
}

/* ---------------- 子命令 ---------------- */
function cmdInfo() {
  const r = act('info');
  console.log(JSON.stringify(r, null, 1));
}

function cmdShot() {
  const out = path.resolve(arg('out', 'shots/shot.png'));
  const payload = { path: out };
  if (arg('region')) {
    const [x, y, width, height] = arg('region').split(',').map(Number);
    payload.region = { x, y, width, height };
  }
  const r = act('screenshot', payload);
  console.log(`${r.path}  ${r.width}x${r.height}`);
}

function cmdMove() {
  const x = Number(arg('x'));
  const y = Number(arg('y'));
  if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error('用法: move --x 100 --y 200');
  act('move', { x, y });
  console.log(`光标移到 (${x},${y})`);
}

function cmdClick() {
  const x = Number(arg('x'));
  const y = Number(arg('y'));
  if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error('用法: click --x 100 --y 200');
  act('click', { x, y, clicks: Number(arg('clicks', 1)) });
  console.log(`点击 (${x},${y})`);
}

function cmdScroll() {
  const x = Number(arg('x', 1280));
  const y = Number(arg('y', 800));
  const clicks = Number(arg('clicks', -3));
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(clicks)) {
    throw new Error('用法: scroll --x 1280 --y 800 --clicks -5');
  }
  act('scroll', { x, y, clicks });
  console.log(`滚动 (${x},${y}) ${clicks} 格`);
}

function cmdType() {
  const text = arg('text');
  if (!text) throw new Error('用法: type --text "..."');
  if (has('raw')) act('type', { text });
  else act('paste', { text });
  console.log(`已写入 ${text.length} 字（${has('raw') ? '逐字输入' : '剪贴板粘贴'}）`);
}

function cmdKey() {
  const combos = [];
  process.argv.forEach((v, i) => { if (v === '--combo' && process.argv[i + 1]) combos.push(process.argv[i + 1]); });
  const keys = combos.length ? combos : [arg('combo', 'enter')];
  act('key', { keys });
  console.log('按键: ' + keys.join(', '));
}

function cmdActivate() {
  const r = act('activate', { title: arg('title', TITLE) });
  console.log(`已激活：${r.title}`);
}

function cmdTopmost() {
  const off = process.argv.includes('--off');
  const r = act('topmost', { title: arg('title', TITLE), off });
  console.log(off ? `已取消置顶：${r.title}` : `已置顶：${r.title}`);
}

function cmdMinimize() {
  const front = process.argv.includes('--front');
  const r = front
    ? act('minimize', { front: true })
    : act('minimize', { title: arg('title', TITLE) });
  console.log(`已最小化：${r.title}`);
}

function cmdUia() {
  const out = path.resolve(arg('out', 'shots/uia.json'));
  const r = runPs(UIA, null, { title: arg('title', TITLE), out }, 90000);
  console.log(`无障碍树：${r.named}/${r.total} 个命名元素 → ${out}`);
}

function cmdGuard() {
  const screen = must(arg('screen'), '先用 shot + uia 产出这一屏的 screen.json');
  const text = screenText(screen);
  const hits = [...new Set((text.match(new RegExp(RED_FLAG_RE.source, 'g')) || []))];
  const clock = readJsonIfExists(CLOCK_FILE(), null);
  const budget = readJsonIfExists(BUDGET_FILE(), {});
  const suggestedMode = budget.mode || (clock ? (clock.mode === 'countup' ? 'full' : 'timed') : 'unknown');
  const result = {
    blocked: hits.length > 0,
    hits,
    screenChars: text.length,
    timerMode: clock ? clock.mode : 'unknown',
    autoSubmit: clock ? !!clock.autoSubmit : false,
    suggestedMode,
  };
  saveJson(arg('out', 'shots/guard.json'), result);
  console.log(JSON.stringify(result));
  if (result.blocked) {
    console.log('⚠ 检测到正式考试特征：' + hits.join('、'));
    console.log('  本助手仅用于自主训练、课程周测与开放性测验，不规避监考/抓拍。请停止自动作答。');
  }
  if (clock && clock.mode === 'countdown') {
    console.log('⏱ 限时周测（作业性质，无监考特征）：不拦截，但必须按 budget 给出的 [MODE=...] 执行；归零会自动交卷。');
    console.log('  当前建议模式: ' + suggestedMode + '；本屏若还没跑 budget，先跑一次。');
  } else if (!clock) {
    console.log('⏱ 未记录计时形态：先用 clock --screen ... 判定倒计时 / 正向计时，再跑 budget。');
  }
  return result;
}

/**
 * fill：把 answers.json 翻译成动作序列，一次 batch 执行。
 * screen.json 结构见 SKILL.md。
 */
function cmdFill() {
  const screen = must(arg('screen'), '先用 shot + uia 产出这一屏的 screen.json');
  const answers = must(arg('answers'));
  const dry = has('dry');

  const qmap = new Map((screen.questions || []).map((q) => [String(q.no), q]));
  const inputs = new Map((screen.inputs || []).map((i) => [String(i.no), i]));
  const actions = [];
  const log = [];
  const warnings = [];

  // 填空题（选词填字母 / 段落匹配填段落字母 / 短文填词）也走输入框，不当成可点选项
  const INPUT_TYPES = new Set(['banked', 'matching', 'blank']);

  const pasteInto = (no, inp, text) => {
    if (!inp || !Number.isFinite(Number(inp.x)) || !Number.isFinite(Number(inp.y))) {
      warnings.push(`#${no} 找不到输入框坐标`);
      return;
    }
    const x = Math.round(Number(inp.x));
    const y = Math.round(Number(inp.y));
    actions.push({ op: 'click', x, y });
    actions.push({ op: 'sleep', ms: 180 });
    actions.push({ op: 'key', keys: ['ctrl+a'] });
    actions.push({ op: 'sleep', ms: 80 });
    actions.push({ op: 'paste', text });
    actions.push({ op: 'sleep', ms: 220 });
    log.push(`#${no} 填入 ${text} @(${x},${y})`);
  };

  for (const [no, spec] of Object.entries(answers)) {
    const q = qmap.get(String(no));
    const type = String(spec.type || '').toLowerCase();
    const raw = (spec.answer || []).map((s) => String(s));
    const inp = inputs.get(String(no)) || (q && q.input);
    const hasOptions = q && Array.isArray(q.options) && q.options.length;
    // 填空题答案走输入框；letter 统一大写，单词保留原大小写
    const treatAsInput = INPUT_TYPES.has(type) || (!hasOptions && !!inp);
    const letters = raw.map((s) => {
      if (!treatAsInput) return s.toUpperCase();
      if (type === 'blank') return s;
      return /^[A-Za-z]$/.test(s) ? s.toUpperCase() : s;
    });

    if (letters.length) {
      if (treatAsInput) {
        pasteInto(no, inp, letters.join(''));
        continue;
      }
      if (!hasOptions) {
        warnings.push(`#${no} 当前屏没有这道选择题，也没有输入框，跳过`);
        continue;
      }
      for (const L of letters) {
        const opt = q.options.find((o) => String(o.letter).toUpperCase() === L);
        if (!opt) {
          warnings.push(`#${no} 选项 ${L} 不在页面（页面只有 ${q.options.map((o) => o.letter).join('')}）`);
          continue;
        }
        if (!Number.isFinite(Number(opt.x)) || !Number.isFinite(Number(opt.y))) {
          warnings.push(`#${no} 选项 ${L} 缺坐标`);
          continue;
        }
        const x = Math.round(Number(opt.x));
        const y = Math.round(Number(opt.y));
        actions.push({ op: 'click', x, y });
        log.push(`#${no} 点 ${L} @(${x},${y})`);
      }
      continue;
    }

    const text = spec.text !== undefined ? String(spec.text) : (spec.texts || []).join('\n');
    if (!text) {
      warnings.push(`#${no} 既没有 answer 也没有 text`);
      continue;
    }
    pasteInto(no, inp, text);
  }

  if (dry) {
    console.log('[dry-run] 计划 ' + actions.length + ' 个动作：');
    log.forEach((l) => console.log('  ' + l));
    warnings.forEach((w) => console.log('  ⚠ ' + w));
    return;
  }
  if (!actions.length) {
    console.log('没有可执行动作');
    warnings.forEach((w) => console.log('⚠ ' + w));
    return;
  }
  const r = act('batch', { actions });
  console.log(log.join('\n'));
  if (warnings.length) warnings.forEach((w) => console.log('⚠ ' + w));
  console.log(`已执行 ${r.count} 个动作`);
}

function cmdVerify() {
  const screen = must(arg('screen'));
  const answers = must(arg('answers'));
  const onScreen = new Set([
    ...(screen.questions || []).map((q) => String(q.no)),
    ...(screen.inputs || []).map((i) => String(i.no)),
  ]);
  const missing = Object.keys(answers).filter((no) => !onScreen.has(String(no)));
  const covered = (screen.questions || []).filter((q) => answers[String(q.no)]);
  const result = {
    screenQuestions: (screen.questions || []).length,
    answersTotal: Object.keys(answers).length,
    answeredOnScreen: covered.length,
    answersNotOnScreen: missing,
    blankOnScreen: (screen.questions || []).filter((q) => !answers[String(q.no)]).map((q) => q.no),
  };
  const p = saveJson(arg('out', 'shots/verify.json'), result);
  console.log(JSON.stringify(result));
  console.log(`→ ${p}`);
  console.log('提示：勾选是否点亮、文本是否落入，必须 shot 截图后看图确认，脚本无法代劳。');
}

function cmdNext() {
  const screen = must(arg('screen'));
  const t = (screen.nav || {}).next;
  if (!t || !Number.isFinite(Number(t.x))) throw new Error('screen.json 的 nav.next 缺坐标');
  act('click', { x: Math.round(Number(t.x)), y: Math.round(Number(t.y)) });
  console.log(`点击「下一题」@(${t.x},${t.y})`);
}

function cmdSubmit() {
  const screen = must(arg('screen'));
  const btn = (screen.nav || {}).submit;
  if (!btn || !Number.isFinite(Number(btn.x))) throw new Error('screen.json 的 nav.submit 缺坐标');

  const hits = [...new Set((screenText(screen).match(new RegExp(RED_FLAG_RE.source, 'g')) || []))];
  if (hits.length) throw new Error(`检测到正式考试特征（${hits.join('、')}），拒绝自动交卷`);

  const clock = readJsonIfExists(CLOCK_FILE(), null);
  if (clock && clock.mode === 'countdown' && clock.deadlineAt) {
    const leftSec = Math.max(0, (clock.deadlineAt - Date.now()) / 1000);
    if (leftSec <= 120) {
      console.log(`⏱ 距自动交卷仅剩 ${fmtClock(leftSec)}（归零自动交卷，不可撤销）。`);
      console.log('[ACTION_REQUIRED] 先确认未答题是否已保底填满；是否现在主动交卷必须由用户明确同意，不要自行决定。');
    }
  }

  if (!has('yes')) {
    console.log(`[dry-run] 将点击「交卷」@(${btn.x},${btn.y})；确认无误后加 --yes`);
    return;
  }
  act('click', { x: Math.round(Number(btn.x)), y: Math.round(Number(btn.y)) });
  sleepSync(1500);
  const c = (screen.nav || {}).confirm;
  if (c && Number.isFinite(Number(c.x))) {
    act('click', { x: Math.round(Number(c.x)), y: Math.round(Number(c.y)) });
    sleepSync(1200);
    console.log('已点击确认按钮');
  } else {
    console.log('未提供 nav.confirm 坐标：请在弹层出现后人工点「确定 / 继续交卷」');
  }
  const out = path.resolve(arg('out', 'shots/after_submit.png'));
  act('screenshot', { path: out });
  console.log('交卷后截图: ' + out);

  // 交卷完成后自动产出录音占用报告；删不删交由用户决定（见 cmdPostSubmit）
  try {
    cmdPostSubmit();
  } catch (e) {
    console.log('（录音报告生成失败，不影响交卷结果：' + e.message + '）');
  }
}

/* ---------------- 录音：扫描 / 报告 / 清理 ---------------- */
const mb = (n) => (n / 1048576).toFixed(1) + ' MB';
const stamp = (t) => new Date(t).toLocaleString('zh-CN', { hour12: false });

/**
 * 扫描 audio/ 下的 .wav 录音，按修改时间升序返回。
 * 安全边界：只认技能目录内的普通文件、排除符号链接、不递归。
 * only 非空时只查这一个文件（值必须是纯文件名，防路径穿越）。
 */
function scanAudio(only) {
  const audioDir = path.resolve(__dirname, '..', 'audio');
  const ext = /\.wav$/i;

  if (only && (only !== path.basename(only) || /[\\/]/.test(only) || only === '..' || only === '.')) {
    throw new Error('--file 只能是 audio/ 目录里的文件名，不能带路径');
  }

  let candidates = [];
  if (only) {
    if (!ext.test(only)) throw new Error('--file 只接受 .wav 文件');
    const p = path.join(audioDir, only);
    if (!fs.existsSync(p)) throw new Error(`audio/ 下找不到 ${only}`);
    candidates = [p];
  } else if (fs.existsSync(audioDir)) {
    candidates = fs.readdirSync(audioDir, { withFileTypes: true })
      .filter((e) => e.isFile() && ext.test(e.name))
      .map((e) => path.join(audioDir, e.name));
  }

  const inside = (p) => path.resolve(p).startsWith(audioDir + path.sep);
  const files = candidates
    .filter((p) => {
      if (!inside(p) || !ext.test(p)) return false;
      try {
        const st = fs.lstatSync(p);
        return st.isFile() && !st.isSymbolicLink();
      } catch (_) { return false; }
    })
    .map((p) => {
      const st = fs.statSync(p);
      return { path: p, name: path.basename(p), bytes: st.size, mtime: st.mtimeMs };
    })
    .sort((a, b) => a.mtime - b.mtime);

  return { audioDir, files };
}

/**
 * postsubmit — 交卷后的收尾报告：只统计录音大小，**不删任何文件**。
 *
 * 命令行脚本无法向用户提问，所以输出 [ACTION_REQUIRED] 标记：
 * 模型读到后必须用 AskUserQuestion 明确询问用户是否删除，
 * 只有得到明确同意才执行 cleanup --apply。
 */
function cmdPostSubmit() {
  const { audioDir, files } = scanAudio();
  const total = files.reduce((s, f) => s + f.bytes, 0);
  const report = {
    stage: 'post-submit',
    audioDir,
    fileCount: files.length,
    totalBytes: total,
    totalHuman: mb(total),
    files: files.map((f) => ({ name: f.name, bytes: f.bytes, human: mb(f.bytes), mtime: stamp(f.mtime) })),
    deleteCommand: 'scripts/run.sh cleanup --apply',
    willDelete: false,
  };
  const out = saveJson(path.resolve(arg('out', 'shots/postsubmit.json')), report);

  console.log('=== 交卷后 · 录音占用报告 ===');
  if (!files.length) {
    console.log('audio/ 下没有 .wav 录音，无需询问删除。');
    console.log('→ ' + out);
    return report;
  }
  console.log(`共 ${files.length} 个录音，合计 ${mb(total)}：`);
  files.forEach((f) => console.log(`  - ${f.name}  ${mb(f.bytes)}  ${stamp(f.mtime)}`));
  console.log('');
  console.log('[ACTION_REQUIRED] 请把上面的占用情况告知用户，并明确询问：是否需要删除这些录音？');
  console.log('  · 用户明确同意    → 执行 scripts/run.sh cleanup --apply（可加 --keep 1 保留一份）');
  console.log('  · 用户拒绝/未回答 → 什么都不要删，直接结束');
  console.log('  · 本命令本身绝不删除任何文件');
  console.log('→ 报告 JSON: ' + out);
  return report;
}

/**
 * cleanup — 做完题后清理 audio/ 下的回环录音。
 *
 * 安全约定（删掉就回听不了，必须保守）：
 *   - 只处理技能目录 audio/ 内的 .wav 普通文件；不递归、不删目录、不接受任意路径
 *   - 默认 dry-run，必须显式 --apply 才真删
 *   - 60 秒内刚写入的文件视为「可能仍在录制」，默认跳过
 *   - --keep N 保留最新 N 份，便于回听复核
 */
function cmdCleanup() {
  const { audioDir, files } = scanAudio(arg('file'));
  const keep = Math.max(0, Number(arg('keep', 0)) || 0);
  const force = has('force');
  const now = Date.now();
  const kept = keep > 0 ? files.slice(-keep) : [];
  const targets = [];
  const skipped = [];
  for (const f of files) {
    if (kept.indexOf(f) > -1) { skipped.push({ ...f, why: `--keep ${keep} 保留最新一份` }); continue; }
    if (!force && now - f.mtime < 60000) {
      skipped.push({ ...f, why: '60 秒内刚写入，疑似仍在录制（确认后可加 --force）' });
      continue;
    }
    targets.push(f);
  }

  console.log('清理范围：' + audioDir);
  if (!files.length) {
    console.log('audio/ 下没有 .wav 录音，无需清理。');
    return;
  }
  console.log(`发现 ${files.length} 个录音，合计 ${mb(files.reduce((s, f) => s + f.bytes, 0))}`);
  console.log('将删除：');
  if (!targets.length) console.log('  （无）');
  targets.forEach((f) => console.log(`  - ${f.name}  ${mb(f.bytes)}  ${stamp(f.mtime)}`));
  if (skipped.length) {
    console.log('跳过：');
    skipped.forEach((f) => console.log(`  - ${f.name}  ${mb(f.bytes)}  ${f.why}`));
  }

  if (!has('apply')) {
    console.log(`\n[dry-run] 以上 ${targets.length} 个文件尚未删除。`);
    console.log('⚠ 删除不可恢复。请确认答案已复核、不再需要回听，再加 --apply 执行。');
    console.log('  想留最新一份回听：加 --keep 1');
    return;
  }
  if (!targets.length) {
    console.log('没有可删除的文件。');
    return;
  }

  let freed = 0;
  const failed = [];
  for (const f of targets) {
    try {
      fs.unlinkSync(f.path);
      freed += f.bytes;
      console.log('  已删除 ' + f.name);
    } catch (e) {
      failed.push(`${f.name}: ${e.message}`);
    }
  }
  console.log(`\n完成：删除 ${targets.length - failed.length}/${targets.length} 个，释放 ${mb(freed)}`);
  failed.forEach((m) => console.log('  ✗ ' + m));
  if (failed.length) throw new Error('部分文件删除失败，见上');
}

/* ---------------- 入口 ---------------- */
(function main() {
  const cmd = process.argv[2] || 'info';
  try {
    if (cmd === 'info') cmdInfo();
    else if (cmd === 'shot') cmdShot();
    else if (cmd === 'move') cmdMove();
    else if (cmd === 'click') cmdClick();
    else if (cmd === 'scroll') cmdScroll();
    else if (cmd === 'type') cmdType();
    else if (cmd === 'key') cmdKey();
    else if (cmd === 'activate') cmdActivate();
    else if (cmd === 'topmost') cmdTopmost();
    else if (cmd === 'minimize') cmdMinimize();
    else if (cmd === 'uia') cmdUia();
    else if (cmd === 'clock') cmdClock();
    else if (cmd === 'budget') cmdBudget();
    else if (cmd === 'guard') cmdGuard();
    else if (cmd === 'fill') cmdFill();
    else if (cmd === 'verify') cmdVerify();
    else if (cmd === 'next') cmdNext();
    else if (cmd === 'submit') cmdSubmit();
    else if (cmd === 'postsubmit') cmdPostSubmit();
    else if (cmd === 'cleanup') cmdCleanup();
    else {
      console.log('未知子命令: ' + cmd);
      console.log('可用: info shot move click scroll type key activate topmost minimize uia clock budget guard fill verify next submit postsubmit cleanup');
      process.exit(2);
    }
  } catch (e) {
    console.error('ERR: ' + e.message);
    process.exit(1);
  }
})();
