#!/usr/bin/env python3
"""Progress ledger for hike-course-assistant.

Pure standard library. Stores course progress as UTF-8 JSON on local disk.
Only section titles, indices and statuses are stored -- never credentials,
cookies, tokens or any page content.

Commands:
    init     Create a new ledger (refuses to overwrite without --force)
    record   Upsert one section's status
    summary  Print completed / remaining sections and completion ratio
    reset    Delete the ledger (requires --confirm)

Examples:
    python ledger.py init --course "数据安全培训" --total 12
    python ledger.py record --index 3 --title "第3节 数据分类" --status completed
    python ledger.py summary
    python ledger.py reset --confirm
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_FILE = Path("hike-progress.json")
STATUSES = ("completed", "playing", "pending", "skipped")
SITE = "hike-teaching-center.polymas.com"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load(path: Path) -> dict:
    if not path.exists():
        return {
            "site": SITE,
            "course": "",
            "total": 0,
            "sections": [],
            "created_at": _now(),
            "updated_at": _now(),
        }
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("site", SITE)
    data.setdefault("course", "")
    data.setdefault("total", 0)
    data.setdefault("sections", [])
    data.setdefault("created_at", _now())
    return data


def _save(path: Path, data: dict) -> None:
    data["updated_at"] = _now()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _sort_key(section: dict):
    index = section.get("index")
    return (index is None, index if isinstance(index, int) else 0, section.get("title", ""))


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if path.exists() and not args.force:
        print(f"台账已存在：{path}（如需重建请加 --force）")
        return 1
    data = {
        "site": SITE,
        "course": args.course,
        "total": args.total,
        "sections": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save(path, data)
    print(f"已建立台账：{path}｜课程：{args.course or '(未命名)'}｜总节数：{args.total}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data = _load(path)
    if args.course:
        data["course"] = args.course
    if args.total is not None:
        data["total"] = args.total

    if args.index is None and not args.title:
        print("需要 --index 或 --title 才能定位小节")
        return 2

    section = None
    if args.index is not None:
        section = next(
            (s for s in data["sections"] if s.get("index") == args.index), None
        )
    if section is None and args.title:
        section = next(
            (s for s in data["sections"] if s.get("title") == args.title), None
        )
    if section is None:
        section = {
            "index": args.index,
            "title": args.title or "",
            "status": args.status,
            "updated_at": _now(),
        }
        data["sections"].append(section)
    else:
        section["status"] = args.status
        if args.title:
            section["title"] = args.title
        if args.index is not None:
            section["index"] = args.index
        section["updated_at"] = _now()
    if args.note:
        section["note"] = args.note

    data["sections"].sort(key=_sort_key)
    _save(path, data)
    label = f"#{section['index']}" if section.get("index") is not None else section.get("title") or "(无标题)"
    print(f"已记录 {label} {section.get('title', '')} → {args.status}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"尚无台账：{path}（先运行 init 或 record）")
        return 1
    data = _load(path)
    sections = data["sections"]
    done = [s for s in sections if s.get("status") == "completed"]
    total = data.get("total") or 0
    done_indices = {s.get("index") for s in done}
    remaining = [i for i in range(1, total + 1) if i not in done_indices] if total else []
    pct = (len(done) / total * 100) if total else 0.0

    lines = [
        f"课程：{data.get('course') or '(未命名)'}",
        f"站点：{data.get('site', SITE)}",
        f"进度：已完成 {len(done)} / 总节数 {total or '未知'}（{pct:.1f}%）",
        f"最近更新：{data.get('updated_at', '未知')}",
    ]
    if remaining:
        preview = ", ".join(str(i) for i in remaining[:20])
        more = f" …等共 {len(remaining)} 节" if len(remaining) > 20 else ""
        lines.append(f"剩余未完成序号：{preview}{more}")
    else:
        lines.append("剩余未完成序号：无（或总节数未设置，无法推算）")
    if args.verbose:
        lines.append("小节明细：")
        for s in sections:
            lines.append(
                f"  #{s.get('index', '?')} {s.get('title', '')} — {s.get('status')} "
                f"({s.get('updated_at', '')})"
            )
    print("\n".join(lines))
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not args.confirm:
        print("重置需要显式 --confirm（会删除台账文件）")
        return 2
    if path.exists():
        path.unlink()
        print(f"已删除台账：{path}")
    else:
        print(f"台账不存在：{path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--file", default=str(DEFAULT_FILE), help="台账 JSON 路径（默认 ./hike-progress.json）"
    )

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", parents=[common], help="建立新台账")
    p_init.add_argument("--course", default="", help="课程名称")
    p_init.add_argument("--total", type=int, default=0, help="总节数")
    p_init.add_argument("--force", action="store_true", help="覆盖已存在的台账")
    p_init.set_defaults(func=cmd_init)

    p_record = sub.add_parser("record", parents=[common], help="记录/更新一节状态")
    p_record.add_argument("--index", type=int, help="小节序号")
    p_record.add_argument("--title", help="小节标题")
    p_record.add_argument("--status", choices=STATUSES, required=True, help="状态")
    p_record.add_argument("--course", help="顺带更新课程名称")
    p_record.add_argument("--total", type=int, help="顺带更新总节数")
    p_record.add_argument("--note", help="可选备注")
    p_record.set_defaults(func=cmd_record)

    p_summary = sub.add_parser("summary", parents=[common], help="输出进度汇总")
    p_summary.add_argument("--verbose", action="store_true", help="附带小节明细")
    p_summary.set_defaults(func=cmd_summary)

    p_reset = sub.add_parser("reset", parents=[common], help="删除台账")
    p_reset.add_argument("--confirm", action="store_true", help="确认删除")
    p_reset.set_defaults(func=cmd_reset)

    return parser


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
