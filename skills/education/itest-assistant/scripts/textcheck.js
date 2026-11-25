#!/usr/bin/env node
'use strict';
/**
 * textcheck.js — 中文文本「AI 味 / 机器生成特征」量化自检
 *
 * 动机：AIGC 检测器与查重系统抓的是**可计算的统计特征**，不是「感觉」。人工判断"像不像人写"
 * 经常失灵（改写完自我感觉良好，检测器照样 90%）。这个脚本把几个高相关特征做成硬指标，
 * 让改写有闭环：写 → 测 → 按报告改 → 再测。
 *
 * 用法：
 *   node textcheck.js <file.txt>            单篇检测
 *   node textcheck.js <file.txt> --json     输出 JSON
 *   node textcheck.js --dir <dir>           批量检测目录下所有 .txt
 *
 * 退出码：0 = 通过；1 = 未通过（有 HIGH 项）
 */

const fs = require('fs');
const path = require('path');

/* ---------------- 词表 ---------------- */
// AI 高频套话（中文 AIGC 检测里最稳定的信号之一：这些短语在人类学生答案里出现率极低）
const CLICHES = [
  '首先', '其次', '再次', '最后', '综上所述', '总而言之', '总的来说', '由此可见',
  '值得注意的是', '不难发现', '不难看出', '众所周知', '显而易见', '显而易见地',
  '在当今社会', '随着社会的发展', '随着科技的进步', '在现代社会', '越来越多的',
  '具有重要意义', '起到了至关重要的作用', '至关重要', '极大地', '深刻地', '有效地',
  '进一步加强', '不断提升', '充分发挥', '全面推进', '深入探讨', '全面分析',
  '不仅', '而且', '从而', '进而', '因此', '然而', '此外', '与此同时',
  '一方面', '另一方面', '需要指出的是', '事实上', '实际上', '总的来说',
  '本文', '综上所述', '由此', '可以得出', '换言之', '换句话说',
];
// 对偶/平行结构标记
const PARALLEL = ['既', '又', '不仅', '而且', '一方面', '另一方面', '既要', '又要'];

/* ---------------- 切句 ---------------- */
// 中文切句：按 。！？； 和换行切，保留标点
function splitSentences(text) {
  const parts = text
    .replace(/\r/g, '')
    .split(/(?<=[。！？；!?;])/g)
    .flatMap((p) => p.split(/\n+/))
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  return parts;
}
// 句子「有效长度」只数汉字与英文单词，标点不算——否则 15 字的短句会被标点撑成 20+ 字
function effLen(s) {
  const han = (s.match(/[\u4e00-\u9fa5]/g) || []).length;
  const en = (s.match(/[A-Za-z]+/g) || []).length;
  return han + en;
}

function splitParagraphs(text) {
  return text.split(/\n\s*\n+/).map((p) => p.trim()).filter(Boolean);
}

/* ---------------- 指标 ---------------- */
function stats(arr) {
  const n = arr.length;
  if (!n) return { n: 0, mean: 0, std: 0, cv: 0, min: 0, max: 0 };
  const mean = arr.reduce((a, b) => a + b, 0) / n;
  const std = Math.sqrt(arr.reduce((a, b) => a + (b - mean) ** 2, 0) / n);
  return { n, mean: +mean.toFixed(2), std: +std.toFixed(2), cv: +(std / (mean || 1)).toFixed(3), min: Math.min(...arr), max: Math.max(...arr) };
}

// 相邻句首 2 字重复率：AI 爱用「…的…，…的…」同构开头
function repeatedOpenings(sentences) {
  if (sentences.length < 3) return { rate: 0, samples: [] };
  const heads = sentences.map((s) => s.slice(0, 2));
  const counter = {};
  heads.forEach((h) => (counter[h] = (counter[h] || 0) + 1));
  const dup = Object.entries(counter).filter(([, c]) => c > 1);
  const dupCount = dup.reduce((a, [, c]) => a + c - 1, 0);
  return { rate: +(dupCount / sentences.length).toFixed(3), samples: dup.map(([h, c]) => `${h}×${c}`) };
}

// 四字格堆积：AI 偏爱"成语腔"。只统计词表内的四字固定搭配，避免把任意四连汉字都算进来
const FOUR_CHAR = [
  '具有重要意义', '至关重要的作用', '不可或缺', '举足轻重', '显而易见', '众所周知',
  '日益增长', '不断发展', '综上所述', '相辅相成', '密不可分', '息息相关', '与时俱进',
  '精益求精', '相辅相成', '卓有成效', '事半功倍', '一劳永逸', '面面俱到', '有条不紊',
  '行之有效', '切实可行', '因地制宜', '统筹兼顾', '全面深入', '系统全面', '深入浅出',
];
function fourCharDensity(text) {
  let hits = 0;
  const found = [];
  for (const w of FOUR_CHAR) {
    const n = text.split(w).length - 1;
    if (n > 0) { hits += n; found.push(w + '×' + n); }
  }
  const per100 = +((hits / (text.length / 100)) || 0).toFixed(2);
  return { count: hits, per100, found };
}

// 段落均匀度：AI 常把每段写成差不多的长度
function paragraphEvenness(paras) {
  const lens = paras.map((p) => p.length);
  const s = stats(lens);
  return { ...s, lens };
}

// 口语/主观标记：人类写作的标志，越多越安全
const HUMAN_MARKERS = ['其实', '说白了', '老实说', '我', '这里', '这玩意', '别', '挺', '倒是', '偏偏', '说白了', '不容易', '坑', '白搭', '多半', '基本', '差不多', '真要说'];
function humanScore(text) {
  let hit = 0;
  const found = [];
  for (const m of HUMAN_MARKERS) {
    const c = (text.split(m).length - 1);
    if (c > 0) { hit += c; found.push(`${m}×${c}`); }
  }
  return { hits: hit, found, per100: +((hit / (text.length / 100)) || 0).toFixed(2) };
}

/* ---------------- 主检测 ---------------- */
function check(text, label = '') {
  const clean = text.trim();
  const sents = splitSentences(clean);
  const paras = splitParagraphs(clean);
  const sentLens = sents.map(effLen);
  const sStat = stats(sentLens);
  const pStat = paragraphEvenness(paras);

  // 套话命中
  const clicheHits = [];
  for (const c of CLICHES) {
    const n = clean.split(c).length - 1;
    if (n > 0) clicheHits.push({ word: c, n });
  }
  const clicheTotal = clicheHits.reduce((a, b) => a + b.n, 0);
  const clichePer100 = +((clicheTotal / (clean.length / 100)) || 0).toFixed(2);

  const open = repeatedOpenings(sents);
  const four = fourCharDensity(clean);
  const human = humanScore(clean);

  // 短句占比（<12 字）：人写东西会突然来一句短的
  const shortRatio = +(sents.filter((s) => effLen(s) < 12).length / (sents.length || 1)).toFixed(2);
  // 长句占比（>50 字）
  const longRatio = +(sents.filter((s) => effLen(s) > 50).length / (sents.length || 1)).toFixed(2);

  /* ---------- 评分（100 分制，越高越像人写） ---------- */
  let score = 100;
  const issues = [];

  // 1) 句长变异系数：人类 0.4~0.8，AI 常 <0.3
  if (sStat.cv < 0.25) { score -= 30; issues.push({ level: 'HIGH', k: '句长过于均匀', v: `CV=${sStat.cv}（<0.25）`, fix: '故意插入 1–3 句 8 字以内的短句，或把一个长句拆成两句' }); }
  else if (sStat.cv < 0.35) { score -= 15; issues.push({ level: 'MID', k: '句长偏均匀', v: `CV=${sStat.cv}`, fix: '再制造 1–2 处长短反差' }); }

  // 2) 套话密度：>1.5 次/百字 明显机器味
  if (clichePer100 > 1.5) { score -= 30; issues.push({ level: 'HIGH', k: '套话密度过高', v: `${clichePer100}/百字`, fix: '删掉「因此/然而/此外/不仅」等连接词，改用语义自然承接' }); }
  else if (clichePer100 > 0.8) { score -= 15; issues.push({ level: 'MID', k: '套话偏多', v: `${clichePer100}/百字`, fix: '至少再删一半连接词' }); }

  // 3) 句首重复
  if (open.rate > 0.25) { score -= 20; issues.push({ level: 'HIGH', k: '句首重复', v: `${open.rate} ${open.samples.join(' ')}`, fix: '换掉重复开头，或把同构句合并' }); }

  // 4) 四字格堆积：>0.8 次/百字 说明成语腔重
  if (four.per100 > 0.8) { score -= 15; issues.push({ level: 'MID', k: '四字格堆积', v: `${four.per100}/百字 ${four.found.join(' ')}`, fix: '把「具有重要意义」这类四字格换成具体说法' }); }

  // 5) 段落均匀度
  if (pStat.n >= 3 && pStat.cv < 0.25) { score -= 15; issues.push({ level: 'MID', k: '段落长度过于整齐', v: `CV=${pStat.cv}`, fix: '让某一段明显短（一两句）或明显长' }); }

  // 6) 人类标记太少
  if (human.per100 < 0.3) { score -= 15; issues.push({ level: 'MID', k: '缺少口语/主观痕迹', v: `${human.per100}/百字`, fix: '加入「其实」「这里容易踩坑」「别…」这类判断' }); }
  else if (human.per100 < 0.6) { score -= 5; }

  // 7) 没有短句（AI 特征：句子都很"完整"）
  if (shortRatio === 0 && sents.length > 5) { score -= 10; issues.push({ level: 'MID', k: '无短句', v: '短句占比 0', fix: '插入一句 5–10 字的话，哪怕只是个判断' }); }

  score = Math.max(0, Math.min(100, score));
  const pass = score >= 75 && !issues.some((i) => i.level === 'HIGH');

  return {
    label, chars: clean.length, sentences: sents.length, paragraphs: paras.length,
    score, pass,
    detail: { sentenceLen: sStat, paragraphLen: pStat, cliche: { hits: clicheHits, per100: clichePer100 }, repeatedOpenings: open, fourChar: four, human, shortRatio, longRatio },
    issues,
  };
}

/* ---------------- 输出 ---------------- */
function report(r, json) {
  if (json) return JSON.stringify(r, null, 1);
  const L = [];
  L.push(`=== ${r.label || '文本'} ===`);
  L.push(`字数 ${r.chars}  句数 ${r.sentences}  段数 ${r.paragraphs}`);
  L.push(`\n【人写度】${r.score}/100  ${r.pass ? '✅ 通过' : '❌ 未通过'}`);
  const d = r.detail;
  L.push(`  句长：均值 ${d.sentenceLen.mean} 字，标准差 ${d.sentenceLen.std}，CV ${d.sentenceLen.cv}（目标 0.40–0.80）`);
  L.push(`  句长分布：最短 ${d.sentenceLen.min} / 最长 ${d.sentenceLen.max}；短句(<12字) ${(d.shortRatio * 100).toFixed(0)}%，长句(>50字) ${(d.longRatio * 100).toFixed(0)}%`);
  L.push(`  段落：${d.paragraphLen.lens.join(' / ')} 字，CV ${d.paragraphLen.cv}`);
  L.push(`  套话：${d.cliche.per100}/百字 ${d.cliche.hits.map((h) => h.word + '×' + h.n).join(' ') || '（无）'}`);
  L.push(`  句首重复：${d.repeatedOpenings.rate} ${d.repeatedOpenings.samples.join(' ') || ''}`);
  L.push(`  四字格：${d.fourChar.per100}/百字 ${d.fourChar.found.join(' ') || '（无）'}`);
  L.push(`  口语痕迹：${d.human.per100}/百字 ${d.human.found.join(' ') || '（无）'}`);
  if (r.issues.length) {
    L.push('\n【待改】');
    r.issues.forEach((i) => L.push(`  [${i.level}] ${i.k}：${i.v}\n        → ${i.fix}`));
  } else L.push('\n【待改】无');
  return L.join('\n');
}

/* ---------------- CLI ---------------- */
(function main() {
  const args = process.argv.slice(2);
  const json = args.includes('--json');
  const dirIdx = args.indexOf('--dir');
  const files = [];
  if (dirIdx > -1) {
    const d = args[dirIdx + 1];
    fs.readdirSync(d).filter((f) => f.endsWith('.txt')).forEach((f) => files.push(path.join(d, f)));
  } else {
    const f = args.find((a) => !a.startsWith('--'));
    if (f) files.push(f);
  }
  if (!files.length) {
    console.log('用法: node textcheck.js <file.txt> [--json] | node textcheck.js --dir <dir>');
    process.exit(2);
  }
  const results = files.map((f) => check(fs.readFileSync(f, 'utf8'), path.basename(f)));
  if (json) console.log(JSON.stringify(results.length === 1 ? results[0] : results, null, 1));
  else results.forEach((r) => console.log(report(r) + '\n'));
  process.exit(results.every((r) => r.pass) ? 0 : 1);
})();
