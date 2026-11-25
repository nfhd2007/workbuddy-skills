#!/usr/bin/env node
'use strict';
/**
 * answercheck.js — 填空题族答案守恒校验（只查形式，不查对错）
 *
 * 三种题型：
 *   banked   选词填空，词库 A–O，答案填字母
 *   matching 段落信息匹配，答案填段落字母
 *   blank    短文/听写填词，答案填一个单词
 *
 * 用法：
 *   node scripts/answercheck.js check.json [--partial] [--json]
 *   node scripts/answercheck.js --help
 *
 * check.json 字段：
 *   type        banked | matching | blank（必填）
 *   bank        词库：{"A":"approximately",...} / ["A"..."O"] / 15（数量）
 *   paragraphs  段落：["A"..."O"] / 15（数量），matching 用
 *   blanks      应填空数（banked / blank）
 *   questions   应答题数（matching）
 *   from / to   题号起止，用于查缺号（可选）
 *   answers     {"1":"C",...} / ["C","N",...] / [{"no":1,"answer":"C"},...]
 *   allowReuse  true 时允许同一字母重复（默认 false）
 *
 * 退出码：0 通过，1 有错误，2 参数/文件错误
 * --partial：答案数不足时降为警告（逐屏作答中途自检用）
 */

const fs = require('fs');

const TYPES = new Set(['banked', 'matching', 'blank']);
const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

function usage() {
  console.log([
    '用法: node scripts/answercheck.js <check.json> [--partial] [--json]',
    '',
    '输入示例（选词填空）:',
    '  { "type": "banked", "bank": {"A":"approximately","B":"case"},',
    '    "blanks": 10, "answers": {"1":"C","2":"N"} }',
    '输入示例（段落匹配）:',
    '  { "type": "matching", "paragraphs": 15, "questions": 10,',
    '    "answers": {"11":"E","17":"L"} }',
    '输入示例（短文填词）:',
    '  { "type": "blank", "blanks": 10, "answers": {"3":"round","4":"run"} }',
    '',
    '只校验形式：数量、字母越界、重复、题号缺号、单词是否为单个词。',
  ].join('\n'));
}

function lettersFromCount(n) {
  if (!Number.isInteger(n) || n < 1 || n > 26) return null;
  return LETTERS.slice(0, n);
}

function normalizeAllowed(raw, kind) {
  // 返回 Map<大写字母, 显示文本>
  const map = new Map();
  if (raw == null) return null;
  if (typeof raw === 'number') {
    const ls = lettersFromCount(raw);
    return ls ? new Map(ls.map((l) => [l, l])) : null;
  }
  if (Array.isArray(raw)) {
    raw.forEach((item, i) => {
      const key = LETTERS[i];
      const val = typeof item === 'string' ? item.trim() : String(item);
      if (key) map.set(key, val);
    });
    return map.size ? map : null;
  }
  if (typeof raw === 'object') {
    Object.keys(raw).forEach((k) => {
      const key = String(k).trim().toUpperCase();
      if (key.length === 1 && LETTERS.includes(key)) map.set(key, String(raw[k]).trim());
    });
    return map.size ? map : null;
  }
  return null;
}

function normalizeAnswers(raw) {
  // 返回 [{ no: string, answer: string }]
  if (raw == null) return [];
  if (Array.isArray(raw)) {
    return raw.map((item, i) => {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        return { no: String(item.no ?? i + 1), answer: String(item.answer ?? '').trim() };
      }
      return { no: String(i + 1), answer: String(item ?? '').trim() };
    });
  }
  if (typeof raw === 'object') {
    return Object.keys(raw).map((k) => ({ no: String(k).trim(), answer: String(raw[k] ?? '').trim() }));
  }
  return [];
}

function cleanLetter(s) {
  // 接受 "C"、"C)"、"C."、" c "；其余原样返回以便报错
  const t = String(s).trim().replace(/^[（(]|[)）.,、;；]$/g, '').trim().toUpperCase();
  return t;
}

function main() {
  const argv = process.argv.slice(2);
  if (!argv.length || argv.includes('--help') || argv.includes('-h')) {
    usage();
    process.exit(argv.length ? 0 : 2);
  }
  const file = argv.find((a) => !a.startsWith('--'));
  const partial = argv.includes('--partial');
  const asJson = argv.includes('--json');
  if (!file) { console.error('✗ 缺少 check.json 路径'); process.exit(2); }
  if (!fs.existsSync(file)) { console.error('✗ 找不到文件: ' + file); process.exit(2); }

  let cfg;
  try { cfg = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (e) { console.error('✗ JSON 解析失败: ' + e.message); process.exit(2); }

  const type = String(cfg.type || '').toLowerCase();
  if (!TYPES.has(type)) { console.error('✗ type 必须是 banked / matching / blank'); process.exit(2); }

  const isWord = type === 'blank';
  const allowed = isWord ? null : normalizeAllowed(
    type === 'banked' ? cfg.bank : cfg.paragraphs, type
  );
  if (!isWord && !allowed) {
    console.error(`✗ ${type === 'banked' ? 'bank' : 'paragraphs'} 缺失或格式不对（对象 / 字母数组 / 1–26 的数量）`);
    process.exit(2);
  }

  const expected = Number(
    type === 'matching' ? (cfg.questions ?? cfg.blanks) : cfg.blanks
  ) || 0;
  const answers = normalizeAnswers(cfg.answers);
  const allowReuse = cfg.allowReuse === true;
  const errs = [];
  const warns = [];
  const rows = [];
  const used = new Map();

  answers.forEach(({ no, answer }) => {
    let val = answer;
    let extra = '';
    let bad = '';

    if (!val) {
      bad = '答案为空';
    } else if (isWord) {
      if (!/^[A-Za-z][A-Za-z'-]*$/.test(val)) bad = '必须是单个单词（不含空格、标点、中文）';
    } else {
      const letter = cleanLetter(val);
      val = letter;
      if (!allowed.has(letter)) bad = `字母 ${letter} 不在${type === 'banked' ? '词库' : '段落'}范围内`;
      else extra = allowed.get(letter);
      if (!bad && used.has(letter) && !allowReuse) bad = `字母 ${letter} 与题号 ${used.get(letter)} 重复`;
      if (used.has(letter)) used.set(letter, used.get(letter) + ',' + no);
      else used.set(letter, no);
    }

    if (bad) errs.push(`题号 ${no}: ${bad}`);
    rows.push({ no, answer: val, extra, status: bad ? '✗ ' + bad : '✓' });
  });

  // 数量
  if (expected > 0) {
    if (answers.length > expected) errs.push(`答案数 ${answers.length} 超过应填数 ${expected}`);
    else if (answers.length < expected) {
      const m = `答案数 ${answers.length} / 应填 ${expected}（还有 ${expected - answers.length} 题未做）`;
      if (partial) warns.push(m); else errs.push(m);
    }
  }

  // 题号缺号（只在给了 from/to 或答案数 == 期望数时检查）
  const from = cfg.from != null ? Number(cfg.from) : null;
  const to = cfg.to != null ? Number(cfg.to) : null;
  if (from != null && to != null && Number.isInteger(from) && Number.isInteger(to) && to >= from) {
    const nums = new Set(answers.map((a) => Number(a.no)).filter(Number.isInteger));
    const missing = [];
    for (let n = from; n <= to; n++) if (!nums.has(n)) missing.push(n);
    if (missing.length) warns.push(`题号缺号: ${missing.join(', ')}`);
    const outOfRange = answers.filter((a) => Number.isInteger(Number(a.no)) && (Number(a.no) < from || Number(a.no) > to));
    if (outOfRange.length) errs.push(`题号超出 ${from}–${to}: ${outOfRange.map((a) => a.no).join(', ')}`);
  }

  // 未使用的词 / 段落
  let unused = [];
  if (!isWord && allowed) {
    unused = [...allowed.entries()]
      .filter(([l]) => !used.has(l))
      .map(([l, w]) => (w && w !== l ? `${l} ${w}` : l));
  }

  const result = {
    type, expected, count: answers.length, allowReuse,
    errors: errs, warnings: warns, rows,
    unused: unused.slice(0, 30),
  };

  if (asJson) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    console.log(`=== 答案守恒校验: ${type} ===`);
    console.log('题号 | 答案 | 对应 | 状态');
    rows.forEach((r) => console.log(
      `${String(r.no).padEnd(4)} | ${String(r.answer).padEnd(4)} | ${String(r.extra).slice(0, 20).padEnd(20)} | ${r.status}`
    ));
    console.log(`\n答案数 ${result.count}${expected ? ' / 应填 ' + expected : ''}`);
    if (!isWord && allowed) console.log(`可用范围 ${[...allowed.keys()].join(' ')}；未使用 ${unused.length} 个`);
    if (unused.length) console.log('未使用: ' + result.unused.join('、') + (unused.length > 30 ? ' …' : ''));
    warns.forEach((w) => console.log('! 警告: ' + w));
    errs.forEach((e) => console.log('✗ 错误: ' + e));
    console.log(errs.length ? '\n✗ 未通过' : '\n✓ 通过（形式校验；正确率仍需双答案交叉）');
  }
  process.exit(errs.length ? 1 : 0);
}

main();
