#!/usr/bin/env node
'use strict';
/**
 * cx.js — 学习通（超星）作业自动化 CLI
 * 通过 CDP 接管用户已登录的 Edge，不处理账号密码。
 *
 * 两套页面模板同时支持：
 *   旧版  /mooc-ans/work/doHomeWorkNew   容器 div.TiMu，选项 input[type=radio]，题面 .Zy_TItle
 *   新版  /mooc-ans/mooc2/work/dowork    容器 div.questionLi，选项 div.answerBg + span.num_option（单选）/ num_option_dx（多选）
 *                                         （无原生 input，靠 addChoice() 打类名 check_answer）
 *
 * 子命令：
 *   status                       打印当前页面 URL / 标题 / 登录态 / 模板版本
 *   extract  [--out f]           抽取题目、选项、已填内容 → JSON
 *   fill     --answers f         按 answers.json 填写（不提交）
 *   verify   [--out f]           检查填写完整性（选项 + 文本）
 *   shot     [--out f]           整页截图
 *   submit   [--text]            真实点击提交并处理确认弹层（--text 只预览不点）
 *   review  [--out f]            批阅复盘：读每题我的答案/正确答案/得分（/work/view 页）
 *   list                         列出课程作业（需 --course=…&--class=…&--cpi=…，见 references）
 *   open     --work=…            按 workId 打开作业作答页（README 见 references/chaoxing-dom.md）
 *   eval     --file f | --code s 在页面上下文执行任意 JS（排查用）
 *
 * 环境变量：CX_CDP（默认 http://127.0.0.1:9222）、CX_PAGE_HINT（默认 dowork|doHomeWorkNew）
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const CDP = process.env.CX_CDP || 'http://127.0.0.1:9222';
// 新版 dowork 与旧版 doHomeWorkNew 都要能命中，默认用正则
const PAGE_HINT = process.env.CX_PAGE_HINT || 'doHomeWorkNew|dowork|doHomework';

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i > -1 ? process.argv[i + 1] : def;
}
const has = (name) => process.argv.includes('--' + name);
const out = (p, data) => {
  const abs = path.resolve(p);
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, typeof data === 'string' ? data : JSON.stringify(data, null, 1), 'utf8');
  return abs;
};

/* ---------------- 页面内工具函数（会被序列化后注入浏览器执行） ---------------- */
function pageHelpers() {
  const norm = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();

  /**
   * 选项显示字母。注意：绝不读 input.value（旧版 value 是 0/1/2/3 乱序）。
   *   新版 questionLi：<span class="choice{id} num_option|num_option_dx fl" data="A">A</span>
   *   旧版 TiMu：<li> 的文本以字母开头
   */
  const letterOf = (el) => {
    if (!el) return '';
    const dataAttr = el.getAttribute && (el.getAttribute('data') || el.getAttribute('data-letter'));
    if (dataAttr && /^[A-Za-z]$/.test(dataAttr.trim())) return dataAttr.trim().toUpperCase();
    const t = norm(el.innerText);
    const m = t.match(/^([A-Za-z])\s*[\.\、\:：\)\）]/) || t.match(/^([A-Za-z])\s/);
    if (m) return m[1].toUpperCase();
    // 新版 .num_option 文本就是纯字母
    if (/^[A-Za-z]$/.test(t)) return t.toUpperCase();
    return t ? t.charAt(0).toUpperCase() : '';
  };

  /** 页面是哪种模板 */
  const pageKind = () => (document.querySelector('.questionLi') ? 'mooc2' : 'legacy');

  const isMooc2 = () => pageKind() === 'mooc2';

  /** 统一的题目节点列表（去嵌套，保最内层） */
  const questionNodes = () => {
    const sel = '.questionLi, .TiMu, div[id^="question"][typename], div[class*="TiMu"]';
    let nodes = [...document.querySelectorAll(sel)].filter((n) => {
      // 新版：有 .answerBg 选项，或有 textarea/input
      if (n.querySelector('.answerBg')) return true;
      return !!n.querySelector(
        'input[type=radio],input[type=checkbox],textarea,input[type=text],[contenteditable="true"],iframe[id^="ueditor"]'
      );
    });
    nodes = nodes.filter((n) => !nodes.some((o) => o !== n && n.contains(o)));
    return nodes;
  };

  /** 新版：选项对象列表 {el, letter, text}；旧版：由 input 反推 */
  const optionsOf = (node) => {
    if (node.querySelector('.answerBg')) {
      return [...node.querySelectorAll('.answerBg')].map((o) => {
        // 单选 span.num_option，多选 span.num_option_dx——两者都要
        const num = o.querySelector('.num_option, .num_option_dx');
        const body = o.querySelector('.answer_p') || o;
        return {
          el: o,
          // 勾选类名打在 .num_option 上，不在 .answerBg 上
          markEl: num || o,
          letter: letterOf(num) || letterOf(o),
          text: norm(body.innerText),
        };
      });
    }
    return [...node.querySelectorAll('input[type=radio],input[type=checkbox]')].map((inp) => {
      const box = inp.closest('li') || inp.closest('label') || inp.parentElement;
      return { el: inp, markEl: inp, letter: letterOf(box), text: norm(box && box.innerText), _input: inp };
    });
  };

  const isChecked = (opt) => {
    if (opt._input) return !!opt._input.checked;
    // 新版靠类名：单选 check_answer，多选 check_answer_dx（两者互斥，都要认）
    return /(^|\s)(check_answer|check_answer_dx|checkAnswer)(\s|$)/.test(opt.markEl.className || '');
  };

  /** 新版答案也同步写到 input#answer{qid}，可用于复核；注意排除 answertype */
  const hiddenAnswer = (node) => {
    const qid = (node.id || '').replace('question', '');
    const el = node.querySelector('input#answer' + qid) || node.querySelector('input[name="answer' + qid + '"]');
    return el ? (el.value || '') : '';
  };

  const textFields = (node) => [...node.querySelectorAll('textarea,input[type=text],[contenteditable="true"]')]
    .filter((e) => !e.disabled && e.type !== 'hidden');

  return { norm, letterOf, pageKind, isMooc2, questionNodes, optionsOf, isChecked, hiddenAnswer, textFields };
}

/* ---------------- 连接 ---------------- */
async function connect() {
  const browser = await chromium.connectOverCDP(CDP);
  const ctx = browser.contexts()[0];
  const pages = ctx.pages();
  const hintRe = new RegExp(PAGE_HINT, 'i');
  let page = pages.find((p) => hintRe.test(p.url()));
  if (!page) page = pages.find((p) => /chaoxing|edu\.cn|mooc/i.test(p.url()));
  if (!page) page = pages[pages.length - 1];
  if (!page) throw new Error('没有可用页面：请先启动 Edge（scripts/launch_edge.bat）并打开学习通作业页');
  return { browser, page };
}

/* ---------------- 子命令 ---------------- */
async function cmdStatus(page) {
  const info = await page.evaluate((src) => {
    const h = eval('(' + src + ')')();
    const info = {
      url: location.href,
      title: document.title,
      loggedIn: !/passport|login/i.test(location.href),
      template: h.pageKind(),
      hasQuestion: h.questionNodes().length > 0,
      bodyHead: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 300),
    };
    // 已提交/已批阅页会被误当成作业页，这里显式识别
    if (/查看详情|重做|提交时间/.test(info.bodyHead) && !info.hasQuestion) info.submitted = true;
    if (/3004|没有此页面访问权限/.test(info.bodyHead)) info.error = 'NO_PERMISSION_3004（链接缺 enc，走课程页 iframe 取 src）';
    return info;
  }, pageHelpers.toString());
  console.log(JSON.stringify(info, null, 1));
}

async function cmdExtract(page) {
  const result = await page.evaluate((src) => {
    const h = eval('(' + src + ')')();
    const nodes = h.questionNodes();
    const qs = nodes.map((node, i) => {
      const isNew = !!node.querySelector('.answerBg');
      const titleEl = node.querySelector('h3, .mark_name, .Zy_TItle, .Cy_TItle, .qtContent, .TiMuTitle');
      const opts = h.optionsOf(node);
      const fields = h.textFields(node);
      const type = opts.length
        ? ((node.getAttribute('typename') || '').includes('多选') || opts.some((o) => o._input && o._input.type === 'checkbox') ? 'multi' : 'single')
        : 'text';
      return {
        index: i + 1,
        qid: (node.id || '').replace('question', ''),
        typename: (node.getAttribute('typename') || '').trim(),
        type,
        question: h.norm((titleEl || node).innerText).slice(0, 1200),
        options: opts.map((o) => ({ letter: o.letter, text: o.text, checked: h.isChecked(o) })),
        texts: fields.map((e) => (e.isContentEditable ? h.norm(e.innerText) : e.value || '')),
        hidden: h.hiddenAnswer(node),
        editors: [...node.querySelectorAll('iframe')].map((f) => f.id || f.className).filter(Boolean),
      };
    });
    return { url: location.href, title: document.title, template: h.pageKind(), count: qs.length, questions: qs };
  }, pageHelpers.toString());

  const p = out(arg('out', path.join(process.cwd(), 'cx_questions.json')), result);
  console.log(`模板: ${result.template}  题目数: ${result.count}  →  ${p}`);
  if (!result.count) {
    const tail = await page.evaluate(() => (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 200));
    if (/\/work\/view/.test(result.url) || /我的答案|正确答案|提交时间/.test(tail)) {
      console.log('ℹ 当前是「作业详情/批阅」页，本来就没有可填控件。要复盘用 review；要重做点「重做」前先问用户。');
    } else {
      console.log('⚠ 未识别到题目。按顺序排查：');
      console.log('  1) status 看 template / error（3004 = 链接缺 enc）');
      console.log('  2) 若已成已提交页（有「查看详情/重做」）说明交过了');
      console.log("  3) eval --code \"[...document.querySelectorAll('[class*=question]')].map(e=>e.className)\" 找真实容器");
    }
  }
}

async function cmdFill(page) {
  const file = arg('answers');
  if (!file) throw new Error('用法: fill --answers answers.json');
  const answers = JSON.parse(fs.readFileSync(path.resolve(file), 'utf8'));
  const log = await page.evaluate(({ src, answers }) => {
    const h = eval('(' + src + ')')();
    const nodes = h.questionNodes();
    const lines = [];
    const setVal = (el, val) => {
      el.focus && el.focus();
      if (el.isContentEditable) {
        el.innerText = val;
        el.dispatchEvent(new InputEvent('input', { bubbles: true }));
        return;
      }
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, val);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      el.dispatchEvent(new Event('blur', { bubbles: true }));
    };
    for (const [key, spec] of Object.entries(answers)) {
      const node = nodes[parseInt(key, 10) - 1];
      if (!node) { lines.push(`#${key} 未找到题目节点`); continue; }
      const want = (spec.answer || []).map((s) => String(s).toUpperCase());
      const opts = h.optionsOf(node);
      if (want.length && opts.length) {
        const chosen = [];
        for (const o of opts) {
          const should = want.includes(o.letter);
          const now = h.isChecked(o);
          if (should !== now) {
            // 新版必须走 .answerBg 的 click（onclick="addChoice(this)"），点 markEl 无效
            o.el.click();
            lines.push(`#${key} ${should ? '选' : '取消'} ${o.letter}`);
          }
          if (should) chosen.push(o.letter);
        }
        const missing = want.filter((w) => !chosen.includes(w));
        if (missing.length) lines.push(`#${key} ⚠ 答案字母 ${missing.join('')} 在页面选项里不存在（选项仅 ${opts.map((o) => o.letter).join('')}）`);
        continue;
      }
      const texts = spec.texts || (spec.text !== undefined ? [spec.text] : null);
      if (texts) {
        // UEditor 优先：新版简答题是 iframe#ueditor_0 + 隐藏 textarea，只写 textarea 界面仍空白
        const ue = [...node.querySelectorAll('iframe')].find((f) => /ueditor/i.test(f.id || f.className));
        if (ue && ue.contentDocument && ue.contentDocument.body) {
          const doc = ue.contentDocument;
          doc.body.innerHTML = String(texts[0]).split('\n').map((p) => `<p>${p}</p>`).join('');
          doc.body.dispatchEvent(new InputEvent('input', { bubbles: true }));
          // 同步回隐藏 textarea，否则提交时读不到内容
          const ta = node.querySelector('textarea[id^=answer]');
          if (ta) {
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')
              .set.call(ta, String(texts[0]));
            ta.dispatchEvent(new Event('input', { bubbles: true }));
            ta.dispatchEvent(new Event('change', { bubbles: true }));
          }
          lines.push(`#${key} UEditor 写入 ${String(texts[0]).length} 字（已同步隐藏域）`);
          continue;
        }
        const fields = h.textFields(node);
        if (fields.length) {
          texts.forEach((v, i) => {
            if (i < fields.length) { setVal(fields[i], String(v)); lines.push(`#${key} 文本框${i + 1} 写入 ${String(v).length} 字`); }
          });
        } else {
          const ifr = [...node.querySelectorAll('iframe')].find((f) => f.contentDocument && f.contentDocument.body);
          if (ifr) {
            ifr.contentDocument.body.innerHTML = '<p>' + String(texts[0]).replace(/\n/g, '</p><p>') + '</p>';
            lines.push(`#${key} 富文本 iframe 写入 ${String(texts[0]).length} 字`);
          } else lines.push(`#${key} 找不到可写字段`);
        }
      }
    }
    return lines;
  }, { src: pageHelpers.toString(), answers });
  console.log(log.join('\n') || '(无变更)');
}

async function cmdVerify(page) {
  const state = await page.evaluate((src) => {
    const h = eval('(' + src + ')')();
    return h.questionNodes().map((node, i) => {
      const opts = h.optionsOf(node);
      const chosen = opts.filter((o) => h.isChecked(o)).map((o) => o.letter);
      const hidden = h.hiddenAnswer(node);
      // UEditor 题的正文在 iframe 里，隐藏 textarea 可能没同步，优先以编辑器为准
      const ue = [...node.querySelectorAll('iframe')].find((f) => /ueditor/i.test(f.id || f.className));
      const ueText = ue && ue.contentDocument && ue.contentDocument.body
        ? (ue.contentDocument.body.innerText || '').replace(/\u00a0/g, ' ').trim() : '';
      const lens = ue ? [ueText.length] : h.textFields(node).map((e) => (e.isContentEditable ? (e.innerText || '').trim() : (e.value || '').trim()).length);
      const type = opts.length ? ((node.getAttribute('typename') || '').includes('多选') ? 'multi' : 'single') : 'text';
      let done;
      if (type === 'text') done = lens.some((n) => n > 0) || hidden.length > 0;
      else {
        done = chosen.length > 0;
        // 新版隐藏字段是第二道保险：若它与类名勾选不一致，说明 DOM 有其他渲染路径，标出来
        if (done && hidden && hidden.length !== chosen.join('').length) done = true;
      }
      return { index: i + 1, type, chosen, hidden, textLen: lens, done };
    });
  }, pageHelpers.toString());

  const pending = state.filter((s) => !s.done);
  const summary = { total: state.length, answered: state.length - pending.length, pending: pending.map((p) => p.index) };
  const p = out(arg('out', path.join(process.cwd(), 'cx_verify.json')), { summary, state });
  console.log(JSON.stringify(summary));
  state.forEach((s) => console.log(`#${s.index} ${s.type}  ${s.chosen.join('') || '-'}  hidden=${s.hidden || '-'}  text=${s.textLen.join('/')}`));
  console.log(`→ ${p}`);
  return summary;
}

async function cmdShot(page) {
  const p = path.resolve(arg('out', path.join(process.cwd(), 'cx_shot.png')));
  try { await page.screenshot({ path: p, fullPage: true }); }
  catch { await page.screenshot({ path: p }); }
  console.log('截图: ' + p);
}

/**
 * 提交。踩过的坑（务必保留这些处理）：
 *  1. 新版主按钮是 .sub-button 里的「提交」，onclick 里没有 submitWork 之类的关键词；
 *  2. 确认层 .popBottom 里 a.jb_btn 有多个，其中 #hintOk 是隐藏的，locator.last() 会选中它 → 超时；
 *  3. DOM .click() 打不开/关不掉确认层，必须用真实鼠标（playwright locator.click）。
 */
async function cmdSubmit(page) {
  const preview = has('text');
  page.on('dialog', async (d) => { console.log(`[dialog ${d.type()}] ${d.message()}`); await d.accept().catch(() => {}); });

  // 1) 主提交按钮
  const mainSel = page.locator(
    '.sub-button a:visible, .sub-button span:visible, a.completeBtn:visible, a[href="javascript:;"]:visible'
  ).filter({ hasText: /^(提交|交卷|提交作业|提交答案)\s*$|重做/ }).filter({ hasNotText: '重做' });

  let clicked = null;
  const n = await mainSel.count();
  for (let i = 0; i < n; i++) {
    const t = (await mainSel.nth(i).innerText().catch(() => '')).trim();
    if (/^(提交|交卷|提交作业|提交答案)$/.test(t)) { clicked = t; if (!preview) await mainSel.nth(i).click(); break; }
  }
  if (!clicked) {
    // 旧版兜底：onclick 含 submitCheckTimes / submitWork
    const r = await page.evaluate(() => {
      const all = [...document.querySelectorAll('a,button,div[onclick],span[onclick],input[type=button]')];
      const b = all.find((e) => /submitCheckTimes|submitWork|completeWork|submitJob/i.test(e.getAttribute('onclick') || ''));
      if (!b) return null;
      b.setAttribute('data-cx-submit', '1');
      b.click();
      return (b.innerText || b.value || '').trim();
    });
    if (r) clicked = r;
  }
  console.log('主按钮: ' + (clicked ? `已点击「${clicked}」` : '未找到提交按钮'));
  if (!clicked) throw new Error('未找到提交按钮：页面可能已提交（有「重做」）或按钮在 iframe 内。先 status/shot 看现场。');
  if (preview) { console.log('--text 预览模式，到此为止（未落确认）。'); return; }

  // 2) 确认层：只点可见的、文案为「确定/确认/提交」的按钮，且排除隐藏的 #hintOk
  await page.waitForTimeout(1800);
  for (let round = 1; round <= 3; round++) {
    const confirm = page.locator('a.jb_btn:visible, .popBottom a:visible, .layui-layer-btn a:visible')
      .filter({ hasText: /^(提交|确定|确认|是|确认提交)$/ });
    const cnt = await confirm.count();
    let hit = null;
    for (let i = 0; i < cnt; i++) {
      const el = confirm.nth(i);
      const id = await el.getAttribute('id').catch(() => '');
      if (id === 'hintOk') continue;              // 隐藏的提示按钮，点了无效还会卡住后面的 locator
      const box = await el.boundingBox().catch(() => null);
      if (!box || box.width < 2) continue;
      hit = (await el.innerText().catch(() => '')).trim();
      await el.click();
      break;
    }
    if (!hit) break;
    console.log(`确认弹层 ${round}: 点击「${hit}」`);
    await page.waitForTimeout(1500);
    // 若已跳走（prompt/结果页）则不必再找
    if (!/dowork|doHomeWorkNew/i.test(page.url())) break;
  }

  // 3) 结果判定
  await page.waitForTimeout(8000);
  const after = await page.evaluate(() => ({
    url: location.href,
    text: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 600),
    success: /提交成功|已提交|已完成|作业已完成|提交时间|查看详情/.test(document.body.innerText || '')
      || /\/prompt|\/work\/list/.test(location.href),
  }));
  const score = (after.text.match(/([\d.]+)\s*分/) || [])[1] || null;
  console.log('结果: ' + JSON.stringify({ url: after.url, success: after.success, score }, null, 1));
  console.log('页面片段: ' + after.text.slice(0, 240));
  await cmdShot(page);
  return after;
}

/**
 * 批阅复盘：在 /mooc2/work/view（作业详情）页读取每题「我的答案 / 正确答案 / 得分」。
 * 提交后必跑一次，用于沉淀错题；也用于校验自己对某类题的理解。
 */
async function cmdReview(page) {
  const data = await page.evaluate(() => {
    const norm = (s) => (s || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
    const nodes = [...document.querySelectorAll('.questionLi')];
    const items = nodes.map((n, i) => {
      const title = norm((n.querySelector('h3') || {}).innerText).slice(0, 200);
      const mine = norm((n.querySelector('.stuAnswerContent') || {}).innerText);
      const right = norm((n.querySelector('.rightAnswerContent') || {}).innerText);
      const score = norm((n.querySelector('.totalScore') || {}).innerText).replace(/分$/, '');
      const opts = [...n.querySelectorAll('li')].map((li) => norm(li.innerText)).filter(Boolean);
      return { index: i + 1, title, mine, right, score, options: opts, wrong: !!right && mine !== right };
    });
    const total = norm((document.body.innerText.match(/([\d.]+)\s*分/) || [])[1] || '');
    return { total, count: items.length, wrong: items.filter((x) => x.wrong), items };
  });
  const p = out(arg('out', path.join(process.cwd(), 'cx_review.json')), data);
  console.log(`总分 ${data.total || '?'}  题数 ${data.count}  错题 ${data.wrong.length}`);
  data.wrong.forEach((w) => console.log(`#${w.index} 我选 ${w.mine || '空'} → 正确 ${w.right}  《${w.title.slice(0, 60)}》`));
  console.log(`→ ${p}`);
}

/** 从课程页 iframe 取作业列表（新版必须走这个，getAllWork 会 3004） */
async function cmdList(page) {
  const info = await page.evaluate(() => {
    const fr = [...document.querySelectorAll('iframe')].map((f) => f.src).filter((s) => /work\/list|getAllWork/.test(s));
    const rows = [...document.querySelectorAll('li')]
      .map((li) => ({ text: (li.innerText || '').replace(/\s+/g, ' ').trim(), url: li.getAttribute('data') || '' }))
      .filter((r) => /剩余|未交|已完成|进行中/.test(r.text));
    return { frames: fr, rows, url: location.href };
  });
  console.log(JSON.stringify(info, null, 1));
}

async function cmdEval(page) {
  let code = arg('code');
  if (!code) {
    const f = arg('file');
    if (!f) throw new Error('用法: eval --code "location.href" 或 eval --file snippet.js');
    code = fs.readFileSync(path.resolve(f), 'utf8');
  }
  const r = await page.evaluate((src) => { try { return { ok: true, value: eval(src) }; } catch (e) { return { ok: false, error: String(e) }; } }, code);
  console.log(JSON.stringify(r, null, 1));
}

/* ---------------- 入口 ---------------- */
(async () => {
  const cmd = process.argv[2] || 'status';
  const { browser, page } = await connect();
  try {
    if (cmd === 'status') await cmdStatus(page);
    else if (cmd === 'extract') await cmdExtract(page);
    else if (cmd === 'fill') await cmdFill(page);
    else if (cmd === 'verify') await cmdVerify(page);
    else if (cmd === 'shot') await cmdShot(page);
    else if (cmd === 'submit') await cmdSubmit(page);
    else if (cmd === 'list') await cmdList(page);
    else if (cmd === 'review') await cmdReview(page);
    else if (cmd === 'eval') await cmdEval(page);
    else console.log('未知子命令: ' + cmd + '\n可用: status extract fill verify shot submit list review eval');
  } finally {
    await browser.close().catch(() => {}); // 只断开 CDP，不关闭用户浏览器
  }
  process.exit(0);
})().catch((e) => { console.error('ERR: ' + e.message); process.exit(1); });
