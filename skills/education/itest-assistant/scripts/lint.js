#!/usr/bin/env node
'use strict';
/**
 * lint.js — 技能发布前自检（WorkBuddy 开放平台上架用）
 *
 * 检查项：
 *   1. SKILL.md 是否存在、是否以 --- 独占一行开头、是否有闭合 ---
 *   2. frontmatter 能否被解析（内置极简 YAML 解析，覆盖 name/description/agent_created 这类标量）
 *   3. name 是否符合 kebab-case、是否与目录名一致
 *   4. description 长度是否在 20–1024 字符之间、是否包含触发词
 *   5. 所有 JS 脚本 node --check 语法
 *   6. SKILL.md 中引用的 scripts//references//assets/ 路径是否真实存在
 *   7. 编码：无 BOM；.md/.js/.sh 为 LF（.bat 允许 CRLF）
 *   8. 是否残留运行产物（cx_*.json / *.png）与明显隐私串
 *
 * 用法：node scripts/lint.js [技能目录]   退出码 0 = 可发布
 */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const errs = [];
const warns = [];
const oks = [];
const E = (m) => errs.push(m);
const W = (m) => warns.push(m);
const O = (m) => oks.push(m);

/* 1. 主文件 */
const skillPath = path.join(ROOT, 'SKILL.md');
if (!fs.existsSync(skillPath)) {
  console.error('✗ 找不到 SKILL.md');
  process.exit(1);
}
const raw = fs.readFileSync(skillPath, 'utf8');

/* 2. frontmatter 边界 */
if (raw.charCodeAt(0) === 0xfeff) E('SKILL.md 含 BOM（UTF-8 BOM），部分解析器会读成 \\ufeff---');
const text = raw.replace(/^\uFEFF/, '');
const lines = text.split('\n');
if (lines[0] !== '---') {
  E(`第 1 行不是独占的 ---，实际是: ${JSON.stringify(lines[0])}（常见错误：写成 \\--- 或前后有空格）`);
}
const closeIdx = lines.findIndex((l, i) => i > 0 && l === '---');
if (closeIdx < 0) E('缺少闭合的 --- 行（必须独占一行，不能有尾随空格）');

let fm = {};
let fmRaw = '';
if (lines[0] === '---' && closeIdx > 0) {
  const body = lines.slice(1, closeIdx);
  fmRaw = body.join('\n');
  let listCount = 0;
  body.forEach((l, i) => {
    if (!l.trim()) { if (i === 0 || i === body.length - 1) W('frontmatter 内存在空行，部分解析器会截断'); return; }
    // 列表项（缩进或顶格的 "- xxx"）与多行缩进行，都不是 key:value
    if (/^-(\s|$)/.test(l) || /^\s+\S/.test(l)) { listCount++; return; }
    const m = l.match(/^([A-Za-z_][\w-]*):\s*(.*)$/);
    if (!m) { E(`frontmatter 第 ${i + 2} 行不是合法 key: value → ${JSON.stringify(l)}`); return; }
    let v = m[2].trim();
    if ((v.startsWith('"') && !v.endsWith('"')) || (v.startsWith("'") && !v.endsWith("'"))) {
      E(`frontmatter 字段 ${m[1]} 的引号未闭合`);
    }
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    fm[m[1]] = v;
  });
  fm.__listItems = listCount;
  if (Object.keys(fm).length) O('frontmatter 解析成功: ' + Object.keys(fm).filter((k) => !k.startsWith('__')).join(', '));
}

/* 3. name */
const dirName = path.basename(ROOT);
if (!fm.name) E('缺少必填字段 name');
else {
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(fm.name)) E(`name "${fm.name}" 不符合 kebab-case（小写字母/数字，用 - 连接）`);
  else O(`name 合法: ${fm.name}`);
  if (fm.name !== dirName) W(`name(${fm.name}) 与目录名(${dirName}) 不一致，平台可能按目录名索引`);
}

/* 4. 平台必填字段（开放平台解析要求，缺一个就上不了架） */
const REQUIRED = [
  ['version', '版本号'],
  ['display_name', '中文展示名'],
  ['display_name_en', '英文展示名'],
  ['description', '描述（兼容旧版）'],
  ['description_zh', '中文描述'],
  ['description_en', '英文描述'],
];
REQUIRED.forEach(([k, label]) => {
  if (!fm[k] || !String(fm[k]).trim()) E(`缺少必填字段 ${k}（${label}）`);
});
// version 语义化版本
if (fm.version && !/^\d+\.\d+\.\d+(-[\w.]+)?$/.test(fm.version)) {
  // 关键：写成 1.0 会被 YAML 解析成浮点数 1，写成 1 会变成整数 —— 平台按字符串比对，直接判定非法
  E(`version "${fm.version}" 不符合语义化版本（必须三段式且加引号，如 version: "1.0.0"；写成 1.0 会被 YAML 解析成浮点数 1）`);
} else if (fm.version) {
  if (/^version:\s*[^"']/.test(fmRaw)) W('version 建议加引号（"1.0.0"），防止被 YAML 当成数字');
  O(`version ${fm.version}`);
}
// 展示名
[['display_name', '中文展示名'], ['display_name_en', '英文展示名']].forEach(([k, label]) => {
  if (!fm[k]) return;
  const v = fm[k];
  if ([...v].length > 40) W(`${k} 偏长（${[...v].length} 字符），展示时可能被截断`);
  if (k === 'display_name' && !/[\u4e00-\u9fa5]/.test(v)) W('display_name 建议用中文');
  if (k === 'display_name_en' && /[\u4e00-\u9fa5]/.test(v)) E('display_name_en 不应包含中文');
  if (v) O(`${label}: ${v}`);
});
// 描述长度与语言
[['description_zh', '中文描述', true], ['description_en', '英文描述', false]].forEach(([k, label, shouldBeZh]) => {
  const v = fm[k];
  if (!v) return;
  const len = [...v].length;
  if (len < 30) E(`${label}过短（${len} 字符），至少 30`);
  else if (len > 1024) E(`${label}过长（${len} 字符），上限约 1024`);
  else O(`${label} ${len} 字符`);
  const hasZh = /[\u4e00-\u9fa5]/.test(v);
  if (shouldBeZh && !hasZh) E(`${label} 应为中文`);
  if (!shouldBeZh && hasZh) E(`${label} 不应包含中文`);
  if (!/当用户|when the user|用户说/i.test(v)) W(`${label} 未写「当用户说…」式触发条件`);
});
// description 与 description_zh 一致性（前者是旧字段，应保持同步）
if (fm.description && fm.description_zh && fm.description !== fm.description_zh) {
  W('description 与 description_zh 不一致，建议保持相同内容以避免不同入口展示混乱');
}
// triggers
const hasTriggers = /^triggers:/m.test(fmRaw) && fm.__listItems > 0;
if (!hasTriggers) W('建议提供 triggers 列表，提升技能被正确触发的概率');
else O(`triggers ${fm.__listItems} 条`);
if (fm.category) O(`category: ${fm.category}`);

/* 5. JS 语法 */
const scriptsDir = path.join(ROOT, 'scripts');
if (fs.existsSync(scriptsDir)) {
  fs.readdirSync(scriptsDir).filter((f) => f.endsWith('.js')).forEach((f) => {
    try {
      execFileSync(process.execPath, ['--check', path.join(scriptsDir, f)], { stdio: 'pipe' });
      O(`语法通过: scripts/${f}`);
    } catch (e) { E(`语法错误: scripts/${f}\n${String(e.stderr || e.message).slice(0, 300)}`); }
  });
}

/* 6. 路径引用 */
const refs = [...text.matchAll(/(?:^|[\s`(（])((?:scripts|references|assets)\/[\w./-]+)/g)].map((m) => m[1]);
const uniq = [...new Set(refs)];
uniq.forEach((r) => {
  const clean = r.replace(/[.,)）]+$/, '');
  if (!fs.existsSync(path.join(ROOT, clean))) E(`SKILL.md 引用了不存在的路径: ${clean}`);
});
if (uniq.length) O(`检查 ${uniq.length} 处路径引用`);

/* 7. 编码换行 */
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => {
  const p = path.join(d, e.name);
  const SKIP = new Set(['.git', 'node_modules', '.archive', '.scratch', 'shots', 'audio']);
  if (SKIP.has(e.name)) return [];
  return e.isDirectory() ? walk(p) : [p];
});
walk(ROOT).forEach((p) => {
  const ext = path.extname(p).toLowerCase();
  if (!['.md', '.js', '.sh', '.json', '.bat'].includes(ext)) return;
  const buf = fs.readFileSync(p);
  const rel = path.relative(ROOT, p);
  if (ext !== '.bat' && buf.includes(0x0d)) E(`${rel} 含 CRLF，Linux/macOS 下 bash 会报 bad interpreter`);
  if (buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf) E(`${rel} 含 UTF-8 BOM`);
});

/* 8. 产物与隐私 */
const junk = walk(ROOT).filter((p) => /(itest_|cx_)(review|shot|verify|questions|answers)\.(json|png)$/.test(p) || /\.(scratch|\.cx)(\/|\\)/.test(p));
if (junk.length) W('存在运行产物，发布前应删除: ' + junk.map((p) => path.relative(ROOT, p)).join(', '));
const allText = walk(ROOT).filter((p) => /\.(md|js|json|sh)$/.test(p)).map((p) => fs.readFileSync(p, 'utf8')).join('\n');
// iTEST 账号数据：token(JWT)、sid、examId 签名串
if (/eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}/.test(allText)) E('文件中残留真实 JWT token，属于账号数据，务必删除');
if (/(stuenc|enc|token)=[0-9a-f]{16,}/.test(allText)) E('文件中残留真实 enc/token 签名串，属于账号数据，务必删除');
if (/(studentid|sid|examId|courseId)[=:]\s*\d{6,}/.test(allText)) W('文件中残留真实学号/考试ID，建议换成占位符');

/* 9. 收尾链路：postsubmit 只报告不删，cleanup 默认 dry-run，submit 联动 */
const orchestrator = path.join(scriptsDir, 'itest.js');
if (fs.existsSync(orchestrator)) {
  const src = fs.readFileSync(orchestrator, 'utf8');
  if (!/function cmdCleanup\(/.test(src)) {
    W('编排层缺少 cleanup 命令（做完题后无法清理录音）');
  } else if (!/if \(!has\('apply'\)\)/.test(src)) {
    E('cleanup 缺少默认 dry-run 保护：删除录音不可恢复，必须显式 --apply');
  } else {
    O('cleanup 默认 dry-run 保护存在');
  }
  if (!/function cmdPostSubmit\(/.test(src)) {
    W('编排层缺少 postsubmit 命令（交卷后不会报告录音大小）');
  } else {
    const psStart = src.indexOf('function cmdPostSubmit');
    const psEnd = src.indexOf('function cmdCleanup');
    const seg = (psStart > -1 && psEnd > psStart) ? src.slice(psStart, psEnd) : '';
    if (/unlinkSync|rmSync|unlink\(/.test(seg)) E('postsubmit 不允许删除文件：只能报告 + 询问');
    else O('postsubmit 只报告不删除');
    if (!/cmdPostSubmit\(\);/.test(src)) E('submit 交卷后未自动联动 postsubmit 录音报告');
    else O('submit 交卷后自动产出录音报告');
    if (!/\[ACTION_REQUIRED\]/.test(src)) W('postsubmit 缺少待询问标记，模型可能忘记向用户确认');
  }
  if (!/cleanup/.test(text)) W('SKILL.md 未提及 cleanup 命令');
  if (!/AskUserQuestion|询问用户/.test(text)) W('SKILL.md 未写明交卷后需询问用户是否删除');
}

/* 10. 限时能力自检：SKILL.md 与编排层必须保留分档策略，防止改版时丢失 */
const TIMED_KEYWORDS = ['倒计时', 'timed', 'rescue', '保底', 'clock', 'budget'];
const missingTimed = TIMED_KEYWORDS.filter((k) => !text.includes(k));
if (missingTimed.length) {
  E('SKILL.md 缺少限时策略关键词: ' + missingTimed.join('、') + '（限时周测归零会自动交卷，必须保留分档能力）');
} else {
  O('限时策略关键词齐全（倒计时 / timed / rescue / 保底 / clock / budget）');
}
if (fs.existsSync(path.join(ROOT, 'references', 'timed-mode.md'))) {
  O('references/timed-mode.md 存在');
} else {
  E('缺少 references/timed-mode.md（限时分档的详细操作口径）');
}
if (!/references\/timed-mode\.md/.test(text)) W('SKILL.md 未引用 references/timed-mode.md');
if (fs.existsSync(orchestrator)) {
  const src = fs.readFileSync(orchestrator, 'utf8');
  if (!/function cmdClock\(/.test(src)) E('编排层缺少 clock 命令（无法记录计时快照）');
  else O('clock 命令存在');
  if (!/function cmdBudget\(/.test(src)) E('编排层缺少 budget 命令（无法算时间预算）');
  else O('budget 命令存在');
  if (!/function decideMode\(/.test(src)) E('编排层缺少 decideMode（无法运行时自动分档）');
  else O('decideMode 分档函数存在');
  if (!/autoSubmit/.test(src)) E('编排层缺少 autoSubmit 语义（归零自动交卷必须显式记录）');
  else O('autoSubmit 语义存在');
  if (!/\[MODE=/.test(src)) W('编排层未输出 [MODE=...] 标记，模型可能忽略分档结果');
}

/* 汇总 */
console.log('\n=== 通过 ===');
oks.forEach((m) => console.log('  ✓ ' + m));
if (warns.length) { console.log('\n=== 警告 ==='); warns.forEach((m) => console.log('  ! ' + m)); }
if (errs.length) { console.log('\n=== 错误 ==='); errs.forEach((m) => console.log('  ✗ ' + m)); }
console.log(`\n${errs.length ? '✗ 不可发布' : '✓ 可以发布'}（错误 ${errs.length}，警告 ${warns.length}）`);
process.exit(errs.length ? 1 : 0);
