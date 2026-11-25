#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_quark_zip.py · 定位刚下载完成的压缩包

浏览器 / 夸克客户端的下载是异步的：文件已出现但仍在写入（.crdownload /
.part）。本工具会等待文件大小稳定、且确认是有效 zip，才把路径交给
install_skill_from_zip.py 做审查安装。

用法：
    # 点击下载「之前」先记录时间戳，然后：
    python find_quark_zip.py --since 1763706000 --wait 120 --json

    python find_quark_zip.py --dir "C:\\Users\\me\\Downloads" --keyword skill --json
    python find_quark_zip.py --all --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

INCOMPLETE_SUFFIXES = (".crdownload", ".part", ".tmp", ".download", ".!ut")
DEFAULT_DIRS = None  # resolved in main()


def _setup_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def parse_since(value):
    """Accept epoch seconds, ISO datetime, 'today', or 'now-30s' / 'now-30m' / 'now-2h'."""
    if not value:
        return None
    v = value.strip()
    if v.isdigit():
        return datetime.fromtimestamp(int(v))
    if v.lower() == "today":
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if v.lower().startswith("now-"):
        spec = v[4:].strip()
        unit = spec[-1:].lower()
        try:
            amount = int(spec[:-1])
        except ValueError:
            raise ValueError("--since 相对时间格式应为 now-30m / now-2h / now-1d")
        delta = {"s": timedelta(seconds=1), "m": timedelta(minutes=1),
                 "h": timedelta(hours=1), "d": timedelta(days=1)}.get(unit)
        if delta is None:
            raise ValueError("--since 相对时间单位只支持 s/m/h/d")
        return datetime.now() - amount * delta
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        raise ValueError("无法解析 --since: %s（支持 epoch / ISO / today / now-30m）" % v)


def is_stable(path: Path, interval: float, min_size: int) -> bool:
    try:
        s1 = path.stat().st_size
        if s1 < min_size:
            return False
        for suffix in INCOMPLETE_SUFFIXES:
            if Path(str(path) + suffix).exists():
                return False
        time.sleep(interval)
        s2 = path.stat().st_size
        if s1 != s2:
            return False
        return zipfile.is_zipfile(path)
    except OSError:
        return False


def scan(dirs, since, keyword, min_size):
    found = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in d.glob("*.zip"):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_size < min_size:
                continue
            if keyword and keyword.lower() not in p.name.lower():
                continue
            if since:
                mtime = datetime.fromtimestamp(st.st_mtime)
                if mtime < since:
                    continue
            found.append((p, st))
    found.sort(key=lambda item: item[1].st_mtime, reverse=True)
    return found


def main() -> int:
    _setup_console()
    ap = argparse.ArgumentParser(description="Locate a freshly downloaded skill .zip")
    ap.add_argument("--dir", dest="dirs", action="append",
                    help="Download directory (repeatable). Default: ~/Downloads")
    ap.add_argument("--since", help="Only files modified after this time: epoch / ISO / today / now-30m")
    ap.add_argument("--keyword", help="Only files whose name contains this string")
    ap.add_argument("--wait", type=float, default=0,
                    help="Seconds to keep polling for a STABLE zip (0 = single scan)")
    ap.add_argument("--interval", type=float, default=1.0, help="Polling interval in seconds")
    ap.add_argument("--min-size", type=int, default=128, help="Ignore files smaller than this (bytes)")
    ap.add_argument("--all", action="store_true", help="List all candidates instead of just the newest")
    ap.add_argument("--json", action="store_true", help="Emit a single JSON object on stdout")
    args = ap.parse_args()

    result = {"ok": False, "zip": "", "size": 0, "mtime": "",
              "candidates": [], "dirs": [], "error": ""}

    try:
        since = parse_since(args.since)
        dirs = [Path(d).expanduser().resolve() for d in args.dirs] if args.dirs else [Path.home() / "Downloads"]
        result["dirs"] = [str(d) for d in dirs]

        deadline = time.monotonic() + max(0.0, args.wait)
        stable = None
        while True:
            found = scan(dirs, since, args.keyword, args.min_size)
            result["candidates"] = [
                {"path": str(p), "size": st.st_size,
                 "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
                for p, st in found
            ]
            for p, st in found:
                if is_stable(p, args.interval, args.min_size):
                    stable = (p, st)
                    break
            if stable or args.wait <= 0 or time.monotonic() >= deadline:
                break
            time.sleep(args.interval)

        if not stable:
            hint = "未找到已下载完成的 zip。"
            if result["candidates"]:
                hint += " 存在候选文件但仍未完成下载或不是有效 zip: %s" % ", ".join(
                    c["path"] for c in result["candidates"][:5])
            else:
                hint += " 请确认浏览器/夸克客户端的下载目录，或用 --dir 指定。"
            raise RuntimeError(hint)

        p, st = stable
        result.update({
            "ok": True,
            "zip": str(p),
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    except Exception as exc:  # noqa: BLE001
        result["error"] = "%s: %s" % (type(exc).__name__, exc)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["ok"]:
            print("错误: %s" % result["error"], file=sys.stderr)
        elif args.all:
            for c in result["candidates"]:
                print("%s  %s bytes  %s" % (c["mtime"], c["size"], c["path"]))
        else:
            print(result["zip"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
