#!/usr/bin/env python3
"""掌握度台账：记录课程基线、未满知识点与逐个拉满的结果。

纯 Python 标准库，跨平台。所有输出默认 UTF-8；Windows PowerShell 5.1 下
若中文乱码，加 --json 得到纯 ASCII JSON（非 ASCII 转义）。

用法（先跑 --help 查参数，不要凭记忆猜）：
    python mastery.py init --course "课程名" --url "分析页URL" --file <路径> \
        --channel edge-extension
    python mastery.py channel --file <路径> --channel edge-extension
    python mastery.py add --file <路径> --module 1 --col 3 --title "知识点名" --pct 0
    python mastery.py record --file <路径> --key 1-3 --status done --pct 100 \
        --questions 5 --correct 5 --avg 2.7 --missing 36
    python mastery.py pending --file <路径>
    python mastery.py summary --file <路径>

channel 仅记录浏览器通道标识，便于断点续跑时沿用同一实例：
    edge-extension（默认首选）/ chrome-extension / qq-extension / iab（降级）
"""

import argparse
import json
import os
import sys
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

VALID_STATUS = {"pending", "done", "partial", "skipped_exempt", "unverified"}
STATUS_CN = {
    "pending": "待处理",
    "done": "已拉满",
    "partial": "部分完成",
    "skipped_exempt": "免考跳过",
    "unverified": "待复核",
}
DEFAULT_FILE = os.path.join(".workbuddy", "mastery", "mastery.json")


def now():
    return datetime.now().isoformat(timespec="seconds")


def load(path):
    if not os.path.exists(path):
        raise SystemExit("[错误] 台账不存在：%s（先运行 init）" % path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    data["updated_at"] = now()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def emit(text, as_json, payload=None):
    if as_json:
        print(json.dumps(payload if payload is not None else {}, ensure_ascii=True))
    else:
        print(text)


def key_of(module, col):
    return "%s-%s" % (module, col)


def blank_stats():
    return {"total": None, "avg": None, "weak": None, "missing": None,
            "exempt": None, "ability": None}


def apply_stats(stats, args):
    for name in ("total", "avg", "weak", "missing", "exempt", "ability"):
        value = getattr(args, name, None)
        if value is not None:
            stats[name] = value
    return stats


def cmd_init(args):
    if os.path.exists(args.file) and not args.force:
        raise SystemExit("[错误] 台账已存在：%s（覆盖请加 --force）" % args.file)
    data = {
        "course": args.course,
        "analysis_url": args.url or "",
        "browser_channel": args.channel or "",
        "created_at": now(),
        "updated_at": now(),
        "baseline": apply_stats(blank_stats(), args),
        "current": apply_stats(blank_stats(), args),
        "points": [],
    }
    save(args.file, data)
    emit("[ok] 台账已建立：%s\n课程：%s\n分析页：%s\n浏览器通道：%s" %
         (args.file, args.course, args.url or "(未记录)",
          args.channel or "(未记录)"),
         args.json, {"ok": True, "file": args.file, "course": args.course,
                     "browser_channel": args.channel or ""})


def cmd_channel(args):
    data = load(args.file)
    data["browser_channel"] = args.channel
    save(args.file, data)
    emit("[ok] 浏览器通道已记录：%s" % args.channel,
         args.json, {"ok": True, "browser_channel": args.channel})


def cmd_add(args):
    data = load(args.file)
    key = args.key or key_of(args.module, args.col)
    for p in data["points"]:
        if p["key"] == key:
            emit("[跳过] 知识点已存在：%s %s" % (key, p.get("title", "")),
                 args.json, {"ok": True, "skipped": True, "key": key})
            return
    point = {
        "key": key,
        "module": args.module,
        "col": args.col,
        "title": args.title or "",
        "initial_pct": args.pct,
        "final_pct": None,
        "status": "pending",
        "questions": None,
        "correct": None,
        "note": "",
        "updated_at": now(),
    }
    data["points"].append(point)
    save(args.file, data)
    emit("[ok] 登记待办：%s %s（初始 %s%%）" % (key, point["title"], args.pct),
         args.json, {"ok": True, "key": key})


def find_point(data, args):
    key = args.key or (key_of(args.module, args.col)
                       if args.module is not None and args.col is not None else None)
    if not key:
        raise SystemExit("[错误] 需要 --key，或同时给 --module 与 --col")
    for p in data["points"]:
        if p["key"] == key:
            return p
    raise SystemExit("[错误] 台账里没有该知识点：%s" % key)


def cmd_record(args):
    if args.status not in VALID_STATUS:
        raise SystemExit("[错误] 非法 status：%s（可选 %s）" %
                         (args.status, ", ".join(sorted(VALID_STATUS))))
    data = load(args.file)
    p = find_point(data, args)
    p["status"] = args.status
    if args.pct is not None:
        p["final_pct"] = args.pct
    if args.questions is not None:
        p["questions"] = args.questions
    if args.correct is not None:
        p["correct"] = args.correct
    if args.note:
        p["note"] = args.note
    p["updated_at"] = now()
    apply_stats(data["current"], args)
    save(args.file, data)
    emit("[ok] %s → %s（%s%%）" % (p["key"], STATUS_CN[args.status],
                                  args.pct if args.pct is not None else "-"),
         args.json, {"ok": True, "key": p["key"], "status": args.status})


def cmd_pending(args):
    data = load(args.file)
    items = [p for p in data["points"] if p["status"] == "pending"]
    if args.json:
        emit("", True, {"ok": True, "count": len(items), "items": items})
        return
    if not items:
        print("没有待处理知识点。")
        return
    print("待处理 %d 个：" % len(items))
    for p in items:
        print("  %-8s 模块%-3s 列%-3s %s（初始 %s%%）" %
              (p["key"], p["module"], p["col"], p.get("title", ""), p.get("initial_pct")))


def cmd_summary(args):
    data = load(args.file)
    counts = {s: 0 for s in VALID_STATUS}
    for p in data["points"]:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    baseline, current = data.get("baseline", {}), data.get("current", {})
    channel = data.get("browser_channel") or ""
    payload = {
        "ok": True,
        "course": data.get("course", ""),
        "analysis_url": data.get("analysis_url", ""),
        "browser_channel": channel,
        "baseline": baseline,
        "current": current,
        "counts": counts,
        "total_points": len(data["points"]),
    }
    if args.json:
        emit("", True, payload)
        return
    print("课程：%s" % data.get("course", ""))
    print("分析页：%s" % (data.get("analysis_url") or "(未记录)"))
    print("台账：%s" % args.file)
    print("浏览器通道：%s" % (channel or "(未记录)"))
    print("登记知识点：%d" % len(data["points"]))
    for s in ("done", "partial", "pending", "skipped_exempt", "unverified"):
        print("  %-16s %d" % (STATUS_CN[s], counts.get(s, 0)))
    print("基线：总数 %s / 平均 %s%% / 薄弱 %s / 遗漏 %s / 免考 %s / 能力 %s%%" %
          tuple(baseline.get(k) for k in
                ("total", "avg", "weak", "missing", "exempt", "ability")))
    print("当前：总数 %s / 平均 %s%% / 薄弱 %s / 遗漏 %s / 免考 %s / 能力 %s%%" %
          tuple(current.get(k) for k in
                ("total", "avg", "weak", "missing", "exempt", "ability")))
    if counts.get("partial") or counts.get("unverified"):
        print("需复核：")
        for p in data["points"]:
            if p["status"] in ("partial", "unverified"):
                print("  %-8s %s  %s" % (p["key"], STATUS_CN[p["status"]], p.get("title", "")))


def build_parser():
    parser = argparse.ArgumentParser(
        description="知到/智慧树掌握度台账（纯标准库）")
    parser.add_argument("--json", action="store_true", help="输出纯 ASCII JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    def stats_flags(p):
        p.add_argument("--total", type=int, help="知识点总数")
        p.add_argument("--avg", type=float, help="平均掌握度（%%）")
        p.add_argument("--weak", type=int, help="薄弱点数量")
        p.add_argument("--missing", type=int, help="遗漏点数量")
        p.add_argument("--exempt", type=int, help="免考数量")
        p.add_argument("--ability", type=float, help="能力达成度（%%）")

    p = sub.add_parser("init", help="建立台账并写入基线")
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--course", required=True, help="课程名")
    p.add_argument("--url", default="", help="掌握度分析页 URL（断点续跑用）")
    p.add_argument("--channel", default="",
                   help="浏览器通道：edge-extension / chrome-extension / qq-extension / iab")
    p.add_argument("--force", action="store_true", help="覆盖已有台账")
    p.add_argument("--json", action="store_true")
    stats_flags(p)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("channel", help="记录或更新本次使用的浏览器通道")
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--channel", required=True,
                   help="edge-extension / chrome-extension / qq-extension / iab")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_channel)

    p = sub.add_parser("add", help="登记一个未满知识点")
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--key", help="自定义键，默认 模块-列")
    p.add_argument("--module", type=int, help="知识模块序号")
    p.add_argument("--col", type=int, help="列序号（1-4）")
    p.add_argument("--title", default="", help="知识点标题")
    p.add_argument("--pct", type=float, default=0, help="初始掌握度，默认 0")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("record", help="记录一个知识点的处理结果")
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--key")
    p.add_argument("--module", type=int)
    p.add_argument("--col", type=int)
    p.add_argument("--status", required=True,
                   help="pending / done / partial / skipped_exempt / unverified")
    p.add_argument("--pct", type=float, help="最终掌握度")
    p.add_argument("--questions", type=int, help="总题数")
    p.add_argument("--correct", type=int, help="答对题数")
    p.add_argument("--note", default="", help="备注（存疑题等）")
    p.add_argument("--json", action="store_true")
    stats_flags(p)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("pending", help="列出剩余待办")
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_pending)

    p = sub.add_parser("summary", help="汇总进度")
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_summary)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
