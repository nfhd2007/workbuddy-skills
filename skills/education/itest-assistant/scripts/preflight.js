#!/usr/bin/env node
'use strict';
/**
 * preflight.js - iTEST assistant: Phase P environment preflight + auto-provision.
 *
 * Invoked by scripts/bootstrap.ps1 (Windows) / scripts/bootstrap.sh (Unix) AFTER a
 * usable Node.js interpreter has been resolved; can also be run directly with
 * any Node 16+ for a standalone health check. Standard library only.
 *
 * Condition layering (mirrors the proven quark-share-skill-installer playbook):
 *   - required : platform, Node, PowerShell 5.1, key files, .ps1 BOM, LF .sh,
 *                writable dirs, working desktop action layer. Auto-fixed when
 *                possible; all of them must pass for `ready` to be true.
 *   - route    : iTEST window/login, resolution, optional Python+soundcard,
 *                companion GUI skills, browser, network. NEVER block `ready`;
 *                they only decide `route` (direct / scene / degraded).
 *   - credential: Unipus account, exam code, captcha. Never touched, never
 *                echoed. Formal-exam red lines are enforced by `guard`.
 *
 * Minimum guarantee: a freshly installed WorkBuddy on Windows ships Node and
 * PowerShell 5.1; Phase P auto-fixes the .ps1 BOM + LF scripts + directories,
 * so `ready` becomes true with zero manual setup. iTEST login is a credential
 * (route layer) and is the only thing the user must do personally.
 *
 * Output: a single pure-ASCII JSON object on stdout (code-page proof); the full
 * readable UTF-8 Chinese report is written to `report_file` / `report_text_file`.
 */
const fs = require('fs');
const path = require('path');
const os = require('os');
const https = require('https');
const { spawnSync } = require('child_process');

const LOG_SEP = '||';
const BASE = { w: 2560, h: 1600 };
const MIN_FREE_BYTES = 200 * 1024 * 1024;
// ITEST_TITLE matches itest.js's own env var: lets a school-branded page title
// (which may not contain "iTEST") still be recognized as the correct scene.
const DEFAULT_TITLE_RE = /iTEST|爱考试|试题作答|Unipus|外研社|U校园/i;
let TITLE_RE = DEFAULT_TITLE_RE;
if (process.env.ITEST_TITLE) {
  try { TITLE_RE = new RegExp(process.env.ITEST_TITLE, 'i'); }
  catch (_) { /* keep default on invalid regex */ }
}

const argv = process.argv.slice(2);
const has = (n) => argv.includes('--' + n);
const val = (n, d) => { const i = argv.indexOf('--' + n); return (i > -1 && argv[i + 1] !== undefined) ? argv[i + 1] : d; };

function asciiEscape(s) {
  return String(s).replace(/[\u0080-\uffff]/g,
    (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}
function log(msg) { process.stderr.write('[preflight] ' + msg + '\n'); }

function cfgDir() {
  const v = (process.env.WORKBUDDY_CONFIG_DIR || '').trim();
  return v ? path.resolve(v) : path.join(os.homedir(), '.workbuddy');
}

const add = (checks, id, level, status, detail, fix) =>
  checks.push({ id, level, status, detail, fix: fix || '' });

function hasBom(buf) {
  return buf.length >= 3 && buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf;
}
function isUtf8(buf) {
  const s = buf.toString('utf8');
  return !s.includes('\uFFFD') && Buffer.from(s, 'utf8').equals(buf);
}

/** Probe a directory for writability; only ever deletes the probe file it created. */
function probeWritable(d, fix, autoFixed) {
  if (!fs.existsSync(d)) {
    if (!fix) return { status: 'block', detail: '目录不存在（--no-fix 未启用自动准备）', writable: false };
    try {
      fs.mkdirSync(d, { recursive: true });
      autoFixed.push('已创建目录: ' + d);
    } catch (e) {
      return { status: 'block', detail: '无法创建目录: ' + e.message, writable: false };
    }
  } else if (!fs.statSync(d).isDirectory()) {
    return { status: 'block', detail: '路径存在但不是目录', writable: false };
  }
  const probe = path.join(d, '.itest-preflight-' + process.pid + '.tmp');
  try {
    fs.writeFileSync(probe, 'ok', 'utf8');
    fs.unlinkSync(probe);
  } catch (e) {
    try { fs.unlinkSync(probe); } catch (_) { /* ignore */ }
    return { status: 'block', detail: '目录不可写: ' + e.message, writable: false };
  }
  const created = autoFixed.some((x) => x.indexOf('已创建目录: ' + d) === 0);
  return { status: created ? 'fixed' : 'ok', detail: created ? '已创建且可写' : '可写', writable: true };
}

function psPath() {
  if (process.env.ITEST_PS) return process.env.ITEST_PS;
  const root = process.env.SystemRoot || process.env.WINDIR || 'C:\\Windows';
  return path.join(root, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
}

/** Run a .ps1 action-layer op and return its last JSON line. */
function psInfo(ps, act) {
  const r = spawnSync(ps, ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', act, '-Op', 'info'],
    { input: '{}', encoding: 'utf8', timeout: 90000, maxBuffer: 8 * 1024 * 1024, windowsHide: true });
  if (r.error) throw r.error;
  const out = (r.stdout || '').replace(/^\uFEFF/, '').trim();
  const last = out.split(/\r?\n/).filter(Boolean).pop() || '{}';
  const j = JSON.parse(last);
  if (!j.ok) throw new Error('动作层返回失败: ' + JSON.stringify(j).slice(0, 200));
  return j;
}

function findPython() {
  const cands = [];
  if (process.env.PY_BIN) cands.push(process.env.PY_BIN);
  const res = process.env.WORKBUDDY_RESOURCES_PATH;
  if (res) cands.push(path.join(res, 'vendor', 'python', 'python.exe'));
  const pv = path.join(cfgDir(), 'binaries', 'python', 'versions');
  if (fs.existsSync(pv)) {
    for (const d of fs.readdirSync(pv).sort().reverse()) {
      cands.push(path.join(pv, d, 'python.exe'), path.join(pv, d, 'python'));
    }
  }
  for (const n of ['python3', 'python']) {
    const r = spawnSync(process.platform === 'win32' ? 'where' : 'which', [n], { encoding: 'utf8' });
    if (r.status === 0) { const p = (r.stdout || '').split(/\r?\n/).filter(Boolean)[0]; if (p) cands.push(p); }
  }
  return cands.find((c) => { try { return fs.existsSync(c); } catch (_) { return false; } }) || '';
}

function findBrowser() {
  const pf = process.env['ProgramFiles(x86)'] || process.env.ProgramFiles || 'C:/Program Files (x86)';
  const pfx = process.env.ProgramFiles || 'C:/Program Files';
  const cands = [
    path.join(pf, 'Microsoft/Edge/Application/msedge.exe'),
    path.join(pfx, 'Microsoft/Edge/Application/msedge.exe'),
    path.join(pf, 'Google/Chrome/Application/chrome.exe'),
    path.join(pfx, 'Google/Chrome/Application/chrome.exe'),
  ];
  return cands.find((c) => { try { return fs.existsSync(c); } catch (_) { return false; } }) || '';
}

function checkNetwork(url, timeoutMs) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok, detail) => { if (!done) { done = true; resolve({ ok, detail }); } };
    try {
      const req = https.get(url, { timeout: timeoutMs, headers: { 'user-agent': 'itest-preflight/1.0' } }, (res) => {
        res.resume(); finish(true, 'HTTP ' + res.statusCode);
      });
      req.on('timeout', () => { req.destroy(); finish(false, '连接超时'); });
      req.on('error', (e) => finish(false, e.code || e.message));
    } catch (e) { finish(false, e.message); }
  });
}

async function run() {
  const skillDir = path.resolve(val('skill-dir', path.join(__dirname, '..')));
  const cfg = cfgDir();
  const fix = !has('no-fix');
  const skipNet = has('skip-network');
  const scriptsDir = path.join(skillDir, 'scripts');
  const dirs = {
    skill: skillDir,
    scripts: scriptsDir,
    shots: path.join(skillDir, 'shots'),
    audio: path.join(skillDir, 'audio'),
    runtime: val('runtime-dir', path.join(cfg, 'runtimes', 'itest-assistant')),
  };

  const checks = [];
  const autoFixed = [];
  const hints = [];
  const blockers = [];
  const degraded = [];

  const ps = psPath();
  const act = path.join(scriptsDir, 'act.ps1');
  const isWin = process.platform === 'win32';

  /* ---------- REQUIRED: platform ---------- */
  if (isWin) {
    add(checks, 'platform', 'required', 'ok', 'Windows（Win32 桌面动作层可用，PowerShell 5.1 为系统组件）');
  } else {
    add(checks, 'platform', 'required', 'block', process.platform + '（非 Windows）',
      '桌面动作层 act.ps1 基于 Windows PowerShell 5.1 + Win32 API，仅支持 Windows 10 1809+；macOS / Linux 无法运行本技能。不要在非 Windows 上继续。');
  }

  /* ---------- REQUIRED: Node ---------- */
  const major = parseInt(process.versions.node, 10);
  add(checks, 'node_version', 'required', major >= 16 ? 'ok' : 'block',
    'Node.js v' + process.versions.node + '（最低要求 16）',
    major >= 16 ? '' : '升级 WorkBuddy，或用 ITEST_NODE_BIN / NODE_BIN 指向 Node 16+ 可执行文件');

  const requiredMods = ['fs', 'path', 'os', 'child_process', 'https', 'url', 'crypto', 'zlib'];
  const missingMods = requiredMods.filter((m) => { try { require(m); return false; } catch (_) { return true; } });
  add(checks, 'node_stdlib', 'required', missingMods.length ? 'block' : 'ok',
    missingMods.length ? '缺少模块: ' + missingMods.join(', ') : ('标准库 ' + requiredMods.length + ' 个模块全部可用'),
    missingMods.length ? '该 Node 不完整，换用官方完整发行版' : '');

  /* ---------- REQUIRED: PowerShell 5.1 ---------- */
  let psMajor = 0, psVersion = '';
  if (isWin) {
    if (!fs.existsSync(ps)) {
      add(checks, 'powershell', 'required', 'block', '未找到 ' + ps,
        '需要 Windows PowerShell 5.1（系统自带）。不要改用 pwsh 7（加载 System.Windows.Forms 会失败）；可用 ITEST_PS 指定路径。');
    } else {
      const r = spawnSync(ps, ['-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'],
        { encoding: 'utf8', timeout: 30000, windowsHide: true });
      psVersion = ((r.stdout || '').trim().split(/\r?\n/).filter(Boolean).pop() || '').trim();
      psMajor = parseInt(psVersion.split('.')[0], 10) || 0;
      if (psMajor === 5) {
        add(checks, 'powershell', 'required', 'ok', 'Windows PowerShell ' + psVersion + '（' + ps + '）');
      } else {
        add(checks, 'powershell', 'required', 'block', 'PowerShell ' + (psVersion || '未知'),
          '需要 5.1 而非 pwsh 7；请用 ITEST_PS 指向 C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe');
      }
    }
  } else {
    add(checks, 'powershell', 'required', 'warn', '非 Windows 平台，跳过 PowerShell 检查');
  }

  /* ---------- REQUIRED: key files ---------- */
  const keyFiles = [
    'SKILL.md', 'scripts/run.sh', 'scripts/bootstrap.ps1', 'scripts/bootstrap.sh',
    'scripts/itest.js', 'scripts/act.ps1', 'scripts/uia.ps1',
    'scripts/textcheck.js', 'scripts/answercheck.js', 'scripts/lint.js', 'scripts/preflight.js',
    'scripts/scale.js', 'scripts/record_loopback.py',
    'references/timed-mode.md', 'references/question-types.md', 'references/answer-quality.md',
    'references/itest-ui.md', 'references/audio-capture.md', 'references/walkthrough.md',
    'references/environment_setup.md', 'assets/screen.example.json', 'assets/answers.example.json',
  ];
  const missing = keyFiles.filter((f) => !fs.existsSync(path.join(skillDir, f)));
  add(checks, 'key_files', 'required', missing.length ? 'block' : 'ok',
    missing.length ? '缺失: ' + missing.join(', ') : ('关键文件 ' + keyFiles.length + ' 个齐全'),
    missing.length ? '重新完整解压技能包，不要只复制个别文件' : '');

  /* ---------- REQUIRED: .ps1 UTF-8 BOM (THE #1 fresh-machine killer) ---------- */
  for (const f of ['act.ps1', 'uia.ps1']) {
    const p = path.join(scriptsDir, f);
    if (!fs.existsSync(p)) continue;
    const buf = fs.readFileSync(p);
    if (hasBom(buf)) { add(checks, 'bom.' + f, 'required', 'ok', 'UTF-8 带 BOM，正常'); continue; }
    if (!isUtf8(buf)) {
      add(checks, 'bom.' + f, 'required', 'block', '文件不是合法 UTF-8（可能被另存成 GBK / UTF-16）',
        '从技能包 zip 重新解压这一个文件覆盖，不要手工另存');
      continue;
    }
    if (!fix) {
      add(checks, 'bom.' + f, 'required', 'block', '缺 UTF-8 BOM（--no-fix 未启用自动修复）',
        '去掉 --no-fix 重跑阶段 P 即会自动补写');
      continue;
    }
    fs.writeFileSync(p, Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), buf]));
    autoFixed.push('已自动补写 ' + f + ' 的 UTF-8 BOM（内容不变）');
    add(checks, 'bom.' + f, 'required', 'fixed',
      '缺 UTF-8 BOM，已自动补写；PowerShell 5.1 无 BOM 会按 GBK 读中文导致动作层返回 {}',
      '无需操作，已修复');
  }

  /* ---------- REQUIRED: LF line endings on .sh (the "bad interpreter" killer) ---------- */
  for (const f of ['run.sh', 'bootstrap.sh']) {
    const p = path.join(scriptsDir, f);
    if (!fs.existsSync(p)) continue;
    const buf = fs.readFileSync(p);
    if (!buf.includes(0x0d)) { add(checks, 'lf.' + f, 'required', 'ok', 'LF 行尾，正常'); continue; }
    if (!fix) {
      add(checks, 'lf.' + f, 'required', 'block', '含 CRLF（--no-fix 未启用自动修复）',
        '去掉 --no-fix 重跑阶段 P 即会自动转换成 LF');
      continue;
    }
    const cleaned = buf.toString('utf8').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    fs.writeFileSync(p, Buffer.from(cleaned, 'utf8'));
    autoFixed.push('已自动把 ' + f + ' 的 CRLF 转为 LF（避免 bash bad interpreter）');
    add(checks, 'lf.' + f, 'required', 'fixed', '含 CRLF，已自动转为 LF', '无需操作，已修复');
  }

  /* ---------- REQUIRED: writable directories ---------- */
  for (const k of ['shots', 'audio', 'runtime', 'scripts']) {
    const r = probeWritable(dirs[k], fix, autoFixed);
    add(checks, 'dir.' + k, 'required', r.status, dirs[k] + ': ' + r.detail,
      r.writable ? '' : '检查目录权限，或用 --runtime-dir 换到可写位置');
    if (!r.writable) blockers.push('[dir.' + k + '] ' + dirs[k] + ': ' + r.detail);
  }

  /* ---------- REQUIRED (soft): free disk space ---------- */
  let free = -1;
  try {
    const st = fs.statfsSync ? fs.statfsSync(dirs.runtime, { bigint: false }) : null;
    if (st) free = Number(st.bavail) * Number(st.bsize);
  } catch (_) { /* ignore */ }
  const diskOk = free < 0 || free >= MIN_FREE_BYTES;
  add(checks, 'disk_space', 'required', diskOk ? 'ok' : 'warn',
    free >= 0 ? ('可用空间 ' + Math.floor(free / 1024 / 1024) + ' MB') : '无法读取磁盘可用空间',
    diskOk ? '' : '清理运行时目录所在磁盘，至少保留 200 MB（便携 Node 约需 110 MB）');

  /* ---------- REQUIRED: JS scripts loadable by the resolved Node ---------- */
  const jsFiles = ['itest.js', 'answercheck.js', 'textcheck.js', 'lint.js', 'preflight.js', 'scale.js'];
  const badJs = [];
  for (const f of jsFiles) {
    const p = path.join(scriptsDir, f);
    if (!fs.existsSync(p)) continue;
    const r = spawnSync(process.execPath, ['--check', p], { encoding: 'utf8', timeout: 30000 });
    if (r.status !== 0) badJs.push(f);
  }
  add(checks, 'scripts_syntax', 'required', badJs.length ? 'block' : 'ok',
    badJs.length ? ('语法校验失败: ' + badJs.join(', ')) : ('已用解析到的 Node 对 ' + jsFiles.length + ' 个 JS 脚本执行 --check，全部通过'),
    badJs.length ? '重新分发技能包' : '');

  /* ---------- REQUIRED: desktop action layer actually works ---------- */
  let info = null;
  if (isWin && fs.existsSync(act) && fs.existsSync(ps)) {
    try {
      info = psInfo(ps, act);
      add(checks, 'action_layer', 'required', 'ok',
        'act.ps1 -Op info 返回合法 JSON（截图 / 点击 / 无障碍树可用）');
    } catch (e) {
      add(checks, 'action_layer', 'required', 'block', '动作层探测失败: ' + e.message,
        '最常见原因是 act.ps1 / uia.ps1 丢了 UTF-8 BOM；去掉 --no-fix 重跑阶段 P 会自动补写后再测。仍失败则确认是 Windows 桌面会话（非远程无头）。');
    }
  } else if (isWin) {
    add(checks, 'action_layer', 'required', 'block', '动作层依赖缺失（act.ps1 或 PowerShell 不存在）',
      '重新解压技能包 / 指定 ITEST_PS');
  } else {
    add(checks, 'action_layer', 'required', 'warn', '非 Windows 平台，跳过动作层探测');
  }

  /* ---------- ROUTE: resolution ---------- */
  let resolution = { base: BASE, current: null, match: true };
  if (info && info.primaryScreen) {
    const s = info.primaryScreen;
    resolution.current = { w: s.width, h: s.height, x: s.x || 0, y: s.y || 0 };
    resolution.match = (s.width === BASE.w && s.height === BASE.h);
    add(checks, 'resolution', 'route', resolution.match ? 'ok' : 'warn',
      '当前分辨率 ' + s.width + '×' + s.height + '（虚拟屏幕原点 ' + (s.x || 0) + ',' + (s.y || 0) + '）',
      resolution.match ? '' : '与 2560×1600 基准不同：预设坐标不可照抄。每屏重新截图量坐标（推荐，本就不需要换算）；或用 bash scripts/run.sh scale --auto --coords "x,y" 粗换算，详见 references/environment_setup.md');
    if (!resolution.match) degraded.push('分辨率与基准不同 → 每屏重新量坐标，不套用文档预设坐标');
    if (resolution.current.x !== 0 || resolution.current.y !== 0) {
      degraded.push('多显示器 / 虚拟屏幕原点非 (0,0) → 坐标以当前截图为准');
    }
  } else {
    add(checks, 'resolution', 'route', 'warn', '未能读取屏幕尺寸', '以第一张实际截图为准');
  }

  /* ---------- ROUTE: iTEST window / login (credential, cannot auto-prepare) ---------- */
  const fgTitle = (info && info.foreground && info.foreground.title) || '';
  const sceneReady = TITLE_RE.test(fgTitle);
  add(checks, 'itest_window', 'route', sceneReady ? 'ok' : 'warn',
    '前台窗口: ' + (fgTitle || '(无标题)'),
    sceneReady ? '' : '账号凭据不能自动准备：请用户本人在 Edge / Chrome 登录 iTEST，停在目标页，窗口最大化、不被遮挡、浏览器缩放 100%，然后重跑阶段 P。此为 route 层条件，不阻塞 ready。');
  if (!sceneReady) {
    hints.push('准备现场三步（用户本人完成，技能绝不代输账号密码 / 验证码）：① 登录 iTEST 并停在目标页 ② 窗口最大化、不要最小化 ③ 浏览器缩放调到 100%。');
    hints.push('可用 bash scripts/run.sh activate 把 iTEST 带到前台，topmost --title X 强制置顶（WorkBuddy 会抢焦点）。');
  }

  /* ---------- ROUTE: optional Python + soundcard (listening only) ---------- */
  const py = findPython();
  let listening = false;
  if (!py) {
    add(checks, 'listening', 'route', 'warn', '未找到 Python',
      '只影响「回环录制听力音频」这条实验链路；客观题 / 填空题 / 文本题作答完全不受影响。需要时安装 Python 后执行 pip install soundcard。');
    degraded.push('缺 Python → 跳过听力回环录制，听力题按用户给的答案填或跳过并标明');
  } else {
    const r = spawnSync(py, ['-c', 'import soundcard'], { encoding: 'utf8', timeout: 30000, windowsHide: true });
    listening = r.status === 0;
    add(checks, 'listening', 'route', listening ? 'ok' : 'warn',
      listening ? ('Python + soundcard 就绪（' + py + '）') : ('Python 可用但缺 soundcard（' + py + '）'),
      listening ? '' : '执行 "' + py + '" -m pip install soundcard，再跑 bash scripts/run.sh record --list 验证');
    if (!listening) degraded.push('缺 soundcard → 跳过听力回环录制（限时卷本就禁用该链路）');
  }

  /* ---------- ROUTE: companion GUI skills / CLI (optional alternates) ---------- */
  const cuSkill = fs.existsSync(path.join(cfg, 'skills', 'computer-use', 'SKILL.md'));
  const dcSkill = fs.existsSync(path.join(cfg, 'skills', 'desktop-control', 'SKILL.md'));
  const cuPlugin = fs.existsSync(path.join(cfg, 'plugins', 'cache', 'workbuddy-computer-use'));
  let agentDesktop = '';
  {
    const r = spawnSync(process.platform === 'win32' ? 'where' : 'which', ['agent-desktop'], { encoding: 'utf8' });
    if (r.status === 0) agentDesktop = (r.stdout || '').split(/\r?\n/).filter(Boolean)[0] || '';
  }
  const companionGui = Boolean(cuSkill || cuPlugin || dcSkill || agentDesktop);
  add(checks, 'companion_gui', 'route', companionGui ? 'ok' : 'warn',
    'computer-use=' + (cuSkill || cuPlugin ? '是' : '否') + ', desktop-control=' + (dcSkill ? '是' : '否') + ', agent-desktop=' + (agentDesktop ? '是' : '否'),
    '本技能自带 act.ps1 动作层，不依赖这些技能；它们只是内置动作层失效时的可选备用操控手段，缺失不影响作答');
  if (!companionGui) degraded.push('未装 computer-use / desktop-control / agent-desktop → 仅用内置 act.ps1 动作层（够用）');

  /* ---------- ROUTE: browser ---------- */
  const browser = findBrowser();
  add(checks, 'browser', 'route', browser ? 'ok' : 'warn', '浏览器: ' + (browser || '未检测到'),
    browser ? '' : 'iTEST 页面需要 Edge / Chrome；Windows 通常自带 Edge');
  if (!browser) degraded.push('未检测到 Edge / Chrome → 提醒用户确认可用浏览器');

  /* ---------- ROUTE: network (only needed for the portable-Node fallback) ---------- */
  let netOk = null, netDetail = '已跳过（--skip-network）';
  if (!skipNet) {
    const n = await checkNetwork('https://registry.npmmirror.com/-/binary/node/', 4000);
    netOk = n.ok; netDetail = n.detail;
  }
  add(checks, 'network', 'route', netOk === false ? 'warn' : 'ok',
    'Node 镜像连通性: ' + netDetail,
    netOk === false ? '仅影响「本机完全没有 Node 时自动下载便携版」这一兜底；本机已有 Node 则完全不受影响' : '');
  if (netOk === false) hints.push('网络不可达；若本机已有 WorkBuddy 自带 Node，可忽略。');

  /* ---------- decision ---------- */
  for (const c of checks) {
    if (c.level === 'required' && c.status === 'block') blockers.push('[' + c.id + '] ' + c.detail);
  }
  const ready = blockers.length === 0;
  let route, routeReason;
  if (!ready) {
    route = 'block';
    routeReason = '存在未修复的必需条件，暂不能继续；按 blockers[] 与 checks[].fix 处理后重跑阶段 P';
  } else if (!sceneReady) {
    route = 'scene';
    routeReason = '环境已就绪，但 iTEST 窗口 / 登录态未就绪。账号凭据不能自动准备，已自动降级为「请用户准备现场」路径：用户本人登录后重跑阶段 P 即转 direct。';
  } else if (degraded.length) {
    route = 'degraded';
    routeReason = '必需条件齐备且现场就绪，但可选能力有缺口，按降级口径直接使用：' + degraded.join('；');
  } else {
    route = 'direct';
    routeReason = '所有必需条件与路径条件齐备，直接进入工作流程第 0 步，无需任何手工配置';
  }
  if (route === 'direct' || route === 'degraded') {
    hints.push('第一张截图必须判定计时形态（倒计时 / 正向计时 / 读不清），每卷重判；随后 clock → budget --answered 0 拿 [MODE=...]。');
  }
  hints.push('交卷默认 dry-run；录音删除必须用户明确同意。正式考试（监考 / 考试码 / 人脸识别 / 抓拍）由 guard 拦截，直接拒绝自动作答。');

  /* ---------- assemble ---------- */
  const source = val('node-source', process.env.ITEST_NODE_SOURCE || 'unknown');
  const portable = has('node-portable') || process.env.ITEST_NODE_PORTABLE === '1';
  const bootLog = (process.env.ITEST_BOOTSTRAP_LOG || '').split(LOG_SEP).filter(Boolean);

  const report = {
    ok: ready,
    ready,
    stage: 'P',
    skill: 'itest-assistant',
    skill_dir: skillDir,
    platform: { system: process.platform, release: os.release(), arch: process.arch, node: process.versions.node },
    node: { cmd: process.execPath, version: process.versions.node, source, portable },
    powershell: { path: ps, version: psVersion, major: psMajor },
    run: { node_cmd: process.execPath, py_cmd: py, ps_cmd: ps },
    dirs,
    resolution,
    scene: { foreground_title: fgTitle, itest_window: sceneReady },
    checks,
    auto_fixed: autoFixed,
    bootstrap_log: bootLog,
    capabilities: {
      action_layer: Boolean(info),
      desktop_automation: Boolean(info) && isWin,
      scene_ready: sceneReady,
      resolution_match: resolution.match,
      listening,
      portable_node: portable,
      network: netOk,
      companion_gui: companionGui,
      browser: Boolean(browser),
      answer_check: !badJs.length,
    },
    degraded,
    route,
    route_reason: routeReason,
    hints,
    blockers,
    warning: '',
    report_file: '',
    report_text_file: '',
  };
  if (route === 'block') report.warning = '存在未修复的必需条件，暂不能继续；按 blockers 处理后重跑引导脚本';
  if (route === 'scene') report.warning = '环境已就绪，等待用户本人登录 iTEST 并准备现场';
  return report;
}

/** Human-readable Chinese text report, written as UTF-8 for file tools to read. */
function textReport(r) {
  const ICON = { ok: '[OK]', fixed: '[已自动修复]', warn: '[提示]', block: '[阻塞]' };
  const L = [];
  L.push('=== iTEST 助手 · 阶段 P 环境自检与自动准备 ===');
  L.push('');
  L.push('结论        : ' + (r.ready ? '可以开跑' : '暂不能开跑'));
  L.push('本次路由    : ' + r.route + '  — ' + r.route_reason);
  L.push('平台        : ' + r.platform.system + ' ' + r.platform.release + ' / ' + r.platform.arch);
  L.push('Node        : v' + r.node.version + '（来源 ' + r.node.source + (r.node.portable ? '，本次自动下载的便携版' : '') + '）');
  L.push('运行时命令  : ' + r.run.node_cmd);
  L.push('PowerShell  : ' + (r.powershell.version || (r.platform.system === 'win32' ? '未探测' : '非 Windows')));
  L.push('前台窗口    : ' + (r.scene.foreground_title || '(无标题)'));
  L.push('分辨率      : ' + (r.resolution.current ? (r.resolution.current.w + '×' + r.resolution.current.h + '（基准 ' + BASE.w + '×' + BASE.h + '）') : '未读取'));
  L.push('');
  L.push('--- 逐项检查 ---');
  for (const c of r.checks) {
    L.push('  ' + ICON[c.status] + ' [' + c.level + '] ' + c.id + '：' + c.detail);
    if (c.fix) L.push('        → ' + c.fix);
  }
  if (r.bootstrap_log.length) {
    L.push(''); L.push('--- 引导层记录 ---');
    for (const l of r.bootstrap_log) L.push('  · ' + l);
  }
  if (r.auto_fixed.length) {
    L.push(''); L.push('--- 本次自动补齐 ---');
    for (const a of r.auto_fixed) L.push('  · ' + a);
  }
  if (r.degraded.length) {
    L.push(''); L.push('--- 降级口径（不阻塞） ---');
    for (const d of r.degraded) L.push('  · ' + d);
  }
  if (r.blockers.length) {
    L.push(''); L.push('--- 阻塞项（必须处理） ---');
    for (const b of r.blockers) L.push('  · ' + b);
  }
  if (r.hints.length) {
    L.push(''); L.push('--- 操作提示 ---');
    for (const h of r.hints) L.push('  · ' + h);
  }
  L.push(''); L.push('----------------------------------------');
  L.push('OK ' + r.checks.filter((c) => c.status === 'ok').length +
    ' / 自动修复 ' + r.checks.filter((c) => c.status === 'fixed').length +
    ' / 提示 ' + r.checks.filter((c) => c.status === 'warn').length +
    ' / 阻塞 ' + r.checks.filter((c) => c.status === 'block').length);
  L.push('');
  L.push('下一步：' + (r.route === 'direct'
    ? '条件齐备，直接进入工作流程第 0 步（activate → shot → 判定计时形态）。'
    : r.route === 'degraded'
      ? '条件齐备，按上面的降级口径进入工作流程第 0 步。'
      : r.route === 'scene'
        ? '请用户本人登录 iTEST 并准备现场，然后重跑阶段 P；环境部分无需再做任何配置。'
        : '按 blockers[] 处理，再重跑阶段 P。不要带病开工。'));
  L.push('提醒：做题前把 iTEST 窗口最大化、浏览器缩放调到 100%；账号密码与验证码一律由用户本人操作。');
  return L.join('\n') + '\n';
}

(async () => {
  let report;
  try {
    report = await run();
  } catch (e) {
    report = {
      ok: false, ready: false, stage: 'P', skill: 'itest-assistant',
      error: 'preflight 自身异常: ' + e.message,
      node: { cmd: process.execPath, version: process.versions.node, source: 'unknown', portable: false },
      run: { node_cmd: process.execPath },
      checks: [], auto_fixed: [], bootstrap_log: [], degraded: [], hints: [],
      blockers: ['preflight 执行失败，请查看 stderr 诊断'], route: 'block',
      route_reason: '自检脚本异常', warning: '自检脚本异常',
      report_file: '', report_text_file: '',
    };
    log('preflight error: ' + e.message);
  }

  const readable = has('readable');
  const reportFile = val('report-file', '');
  const textFile = reportFile ? reportFile.replace(/\.json$/i, '') + '.txt' : '';
  // Set the fields BEFORE serializing, so the persisted JSON also tells the
  // agent where the readable Chinese report lives (not just stdout).
  report.report_file = '';
  report.report_text_file = '';
  if (reportFile) {
    try {
      fs.mkdirSync(path.dirname(reportFile), { recursive: true });
      report.report_file = reportFile;
      report.report_text_file = textFile;
      fs.writeFileSync(reportFile, JSON.stringify(report, null, 2), 'utf8');
      fs.writeFileSync(textFile, textReport(report), 'utf8');
    } catch (e) {
      log('cannot write report file: ' + e.message);
      report.report_file = ''; report.report_text_file = '';
    }
  }

  const json = JSON.stringify(report, null, 2);
  process.stdout.write((readable ? json : asciiEscape(json)) + '\n');
  process.exit(report.ready ? 0 : 1);
})();
