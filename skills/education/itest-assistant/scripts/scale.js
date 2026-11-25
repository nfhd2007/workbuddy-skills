#!/usr/bin/env node
'use strict';
/**
 * scale.js — 跨分辨率坐标粗换算（阶段 P 的 route 层辅助工具）
 *
 * references/itest-ui.md 里的预设坐标是在 2560×1600 物理像素、Edge 最大化、
 * 150% 系统缩放下标定的。换一台电脑分辨率不同，这些坐标不能照抄。
 *
 * 用途：把「文档里的基准坐标」粗略换算到本机分辨率，作为第一次找按钮的起点。
 * 注意：这是等比估算，页面有固定宽度元素时会有偏差，**最终一定以当前截图为准**。
 * 阶段 P 报告 resolution.match=false 时会提示使用本工具；每屏重新截图量坐标仍是首选。
 *
 * 用法：
 *   bash scripts/run.sh scale --auto --coords "1078,135 846,301"
 *   bash scripts/run.sh scale --to 1920x1080 --coords "673,495" --coords "673,740"
 *   bash scripts/run.sh scale --from 2560x1600 --to 1366x768 --coords "1916,690" --json
 *
 * 参数：
 *   --from WxH      基准分辨率，默认 2560x1600
 *   --to   WxH      目标分辨率；与 --auto 二选一
 *   --auto          调用 act.ps1 info 自动读取本机虚拟屏幕尺寸
 *   --coords "x,y x,y ..."   可重复；也接受 --x N --y N 单点
 *   --json          额外输出 JSON
 */
const path = require('path');
const { spawnSync } = require('child_process');

const PS = process.env.ITEST_PS || path.join(
  process.env.SystemRoot || 'C:\\Windows',
  'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'
);
const DEF_FROM = { w: 2560, h: 1600 };

const arg = (n, d) => { const i = process.argv.indexOf('--' + n); return i > -1 ? process.argv[i + 1] : d; };
const has = (n) => process.argv.includes('--' + n);
const allArgs = (n) => {
  const out = [];
  process.argv.forEach((v, i) => { if (v === '--' + n && process.argv[i + 1]) out.push(process.argv[i + 1]); });
  return out;
};
function parseSize(s, label) {
  const m = String(s || '').match(/^(\d+)\s*[xX\u00d7]\s*(\d+)$/);
  if (!m) throw new Error(label + ' 格式应为 WxH，例如 1920x1080（收到：' + s + '）');
  return { w: Number(m[1]), h: Number(m[2]) };
}
function autoSize() {
  const r = spawnSync(PS, [
    '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', path.join(__dirname, 'act.ps1'), '-Op', 'info',
  ], { input: '{}', encoding: 'utf8', timeout: 90000, maxBuffer: 8 * 1024 * 1024, windowsHide: true });
  if (r.error) throw r.error;
  const out = (r.stdout || '').replace(/^\uFEFF/, '').trim();
  const last = out.split(/\r?\n/).filter(Boolean).pop() || '{}';
  const j = JSON.parse(last);
  if (!j.ok || !j.primaryScreen) throw new Error('读取屏幕尺寸失败：' + JSON.stringify(j));
  const s = j.primaryScreen;
  return { w: s.width, h: s.height, origin: { x: s.x, y: s.y } };
}
function parseCoords() {
  const pts = [];
  for (const chunk of allArgs('coords')) {
    for (const pair of String(chunk).split(/[\s;]+/)) {
      const m = pair.match(/^(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$/);
      if (!m) throw new Error('坐标应为 x,y，收到：' + pair);
      pts.push({ x: Number(m[1]), y: Number(m[2]) });
    }
  }
  const x = arg('x'), y = arg('y');
  if (x !== undefined && y !== undefined) pts.push({ x: Number(x), y: Number(y) });
  return pts;
}

function main() {
  const from = parseSize(arg('from', '2560x1600'), '--from');
  let to;
  if (has('auto')) {
    to = autoSize();
  } else if (arg('to')) {
    to = parseSize(arg('to'), '--to');
  } else {
    throw new Error('请指定 --to WxH 或 --auto');
  }
  const pts = parseCoords();
  if (!pts.length) throw new Error('没有坐标：用 --coords "1078,135 846,301" 或 --x N --y N');

  const sx = to.w / from.w;
  const sy = to.h / from.h;
  const rows = pts.map((p) => ({
    from: { x: p.x, y: p.y },
    to: { x: Math.round(p.x * sx), y: Math.round(p.y * sy) },
  }));

  console.log('基准 ' + from.w + '\u00d7' + from.h + '  \u2192  本机 ' + to.w + '\u00d7' + to.h);
  if (to.origin) console.log('虚拟屏幕原点 (' + to.origin.x + ',' + to.origin.y + ')');
  console.log('缩放系数 x=' + sx.toFixed(4) + '  y=' + sy.toFixed(4));
  if (to.origin && (to.origin.x !== 0 || to.origin.y !== 0)) {
    console.log('\u26a0 检测到多显示器 / 虚拟屏幕原点非 0，换算结果可能不准，请以截图为准。');
  }
  console.log('');
  console.log('  基准坐标        换算后');
  rows.forEach((r) => {
    console.log('  (' + r.from.x + ', ' + r.from.y + ')'.padEnd(18) +
      '\u2192 (' + r.to.x + ', ' + r.to.y + ')');
  });
  console.log('');
  console.log('\u26a0 这只是等比粗估，页面有固定宽度元素时会偏。点之前务必先 bash scripts/run.sh shot');
  console.log('  看当前截图重新量一次坐标；截图上量到的坐标可直接用，不需要换算。');
  console.log('  详见 references/environment_setup.md');

  if (has('json')) {
    console.log(JSON.stringify({ from, to, scale: { x: sx, y: sy }, points: rows }, null, 1));
  }
}

try { main(); } catch (e) { console.error('ERR: ' + e.message); process.exit(1); }
