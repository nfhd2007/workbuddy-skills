#!/usr/bin/env python3
"""掌握度助手 · 运行截图缓存清理（纯标准库、跨平台）。

背景
----
`mcp__browser__tab_screenshot` / `cua_execute` 内嵌 screenshot 返回的是
MCP 图像内容，WorkBuddy 会把它落盘到：

    ~/.workbuddy/blobs/<2 字符前缀>/<sha256>.png

该目录是**全局共享缓存**（其它会话 / 技能的图片也在里面），因此绝不能
整目录删除、按通配符批量删除，也不能按「最近 N 分钟」粗暴清空。

策略
----
    begin   记录本次运行起始时间戳、白名单目录，生成一份运行清单
    add     若截图工具结果里给出了落盘路径，逐条登记（最精确，优先采用）
    list    只读 dry-run，列出待删文件，不删除任何东西
    finish  候选 = 显式登记 ∪ 白名单目录中「起始时间之后新增」的图片；
            逐文件校验后先打印清单，再每 10 个一组 os.remove 并校验；
            成功后默认删除清单文件本身

安全约束（不可放宽）
--------------------
* 不调用 rmtree、不删目录、不用通配符批量删除；只 os.remove 单个文件。
* 白名单目录默认仅 `~/.workbuddy/blobs`；用 realpath + commonpath 校验，
  防路径穿越 / 符号链接越界。
* 默认**不**扫描 `~/.workbuddy/clipboard-images`（里面多为用户自己粘贴的
  图片）；只有 `add --path` 显式登记或 begin 带 `--include-clipboard` 才纳入。
* 只删 IMAGE_EXT 内的普通文件；不删台账 .json、不删清单自身、不碰
  Desktop / Downloads / Documents / Home 根 / 系统目录。
* `--max-delete` 上限（默认 500），超限一律拒绝删除并要求人工确认。
* 任何删除失败立即停止并报告剩余数量，不继续盲删。
* `--keep` 只列不删（复盘用）；`--keep-manifest` 保留清单便于审计。

用法（先跑 --help 查参数，不要凭记忆猜）
----------------------------------------
    python cleanup_screenshots.py begin  [--file <清单>] [--run-id <id>] \
        [--blobs-dir <路径>] [--include-clipboard] [--json]
    python cleanup_screenshots.py add    --file <清单> --path <截图路径> \
        [--path <截图路径> ...] [--json]
    python cleanup_screenshots.py list   --file <清单> [--verbose] [--json]
    python cleanup_screenshots.py finish --file <清单> [--keep] \
        [--keep-manifest] [--max-delete 500] [--json]
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from urllib.parse import unquote

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_MAX_DELETE = 500
BATCH_SIZE = 10
CLOCK_SKEW = 2.0  # 秒：容纳 begin 调用与首张截图之间的时间边界
MANIFEST_DIR = os.path.join(".workbuddy", "mastery")


def now_str():
    return datetime.now().isoformat(timespec="seconds")


def real(p):
    return os.path.realpath(os.path.abspath(p))


def is_under(path, root):
    """path 是否位于 root 之内（含 root 本身）。防跨盘符 / 路径穿越。"""
    try:
        return os.path.commonpath([real(path), real(root)]) == real(root)
    except (ValueError, OSError):
        return False


def default_dirs(include_clipboard=False, blobs_dir=None):
    """动态解析路径，禁止硬编码用户名 / 盘符 / 版本目录名。"""
    home = os.path.expanduser("~")
    base = os.path.join(home, ".workbuddy")
    blobs = blobs_dir or os.path.join(base, "blobs")
    dirs = [real(blobs)]
    if include_clipboard:
        dirs.append(real(os.path.join(base, "clipboard-images")))
    return dirs


def default_manifest(run_id):
    os.makedirs(MANIFEST_DIR, exist_ok=True)
    return os.path.join(MANIFEST_DIR, "screenshots-%s.json" % run_id)


def emit(text, as_json, payload=None):
    if as_json:
        print(json.dumps(payload if payload is not None else {}, ensure_ascii=True))
    else:
        print(text)


def load_manifest(path):
    if not os.path.exists(path):
        raise SystemExit("[跳过] 找不到本次运行清单：%s（无需清理或已清理完毕）" % path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize_path(raw):
    """把工具结果里的路径 / file:// URI 转成绝对路径。"""
    p = raw.strip().strip('"').strip("'")
    if p.lower().startswith("file://"):
        p = unquote(p[7:])
        # Windows: file:///C:/... -> /C:/... -> C:/...
        if os.name == "nt" and len(p) >= 3 and p[0] == "/" and p[2] == ":":
            p = p[1:]
    return real(p)


def validate_candidate(path, manifest_path, dirs):
    """逐文件安全校验。返回 (是否可删, 原因)。"""
    if os.path.islink(path) or not os.path.isfile(path):
        return False, "不是普通文件"
    if os.path.splitext(path)[1].lower() not in IMAGE_EXT:
        return False, "扩展名不在白名单"
    if real(path) == real(manifest_path):
        return False, "清单文件自身"
    if not any(is_under(path, d) for d in dirs):
        return False, "不在白名单目录内"
    # 台账 / 探针等 .workbuddy/mastery 下的文件不属于图片缓存
    if ".workbuddy" in path.replace("\\", "/") and "/mastery/" in path.replace("\\", "/"):
        return False, "位于台账目录，属于保护范围"
    return True, ""


def collect_window(dirs, started_epoch, manifest_path):
    """扫描白名单目录里「起始时间之后新增」的图片。"""
    found = []
    for root in dirs:
        if not os.path.isdir(root):
            continue
        for cur, _subdirs, files in os.walk(root):
            for name in files:
                if os.path.splitext(name)[1].lower() not in IMAGE_EXT:
                    continue
                p = os.path.join(cur, name)
                try:
                    if os.path.islink(p) or not os.path.isfile(p):
                        continue
                    if os.path.getmtime(p) < started_epoch - CLOCK_SKEW:
                        continue
                    ok, _ = validate_candidate(p, manifest_path, dirs)
                    if ok:
                        found.append(real(p))
                except OSError:
                    continue
    return found


def cmd_begin(args):
    run_id = args.run_id or (
        datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    path = args.file or default_manifest(run_id)
    dirs = default_dirs(args.include_clipboard, args.blobs_dir)
    existing = [d for d in dirs if os.path.isdir(d)]
    data = {
        "run_id": run_id,
        "started_at": now_str(),
        "started_epoch": time.time(),
        "cwd": os.getcwd(),
        "whitelist_dirs": dirs,
        "existing_dirs": existing,
        "include_clipboard": bool(args.include_clipboard),
        "explicit": [],
        "finished": False,
        "cleaned": None,
    }
    save_manifest(path, data)
    emit("[ok] 已建立本次运行截图清单：%s\n运行 ID：%s\n白名单目录：%s\n"
         "起始时间：%s（收尾时会清理此后新增的截图）" %
         (path, run_id, "、".join(existing) if existing else "(未发现图片缓存目录)",
          data["started_at"]),
         args.json,
         {"ok": True, "file": path, "run_id": run_id,
          "started_epoch": data["started_epoch"],
          "whitelist_dirs": dirs, "existing_dirs": existing})


def cmd_add(args):
    data = load_manifest(args.file)
    if data.get("finished"):
        raise SystemExit("[跳过] 本次运行已收尾清理，不再登记截图路径")
    dirs = data.get("whitelist_dirs") or default_dirs()
    added, rejected = [], []
    for raw in args.path or []:
        p = normalize_path(raw)
        ok, why = validate_candidate(p, args.file, dirs)
        if not ok:
            rejected.append("%s（%s）" % (p, why))
            continue
        if p not in data["explicit"]:
            data["explicit"].append(p)
            added.append(p)
    data["explicit"] = sorted(set(data["explicit"]))
    save_manifest(args.file, data)
    emit("[ok] 登记截图 %d 个（累计 %d）；拒绝 %d 个%s" %
         (len(added), len(data["explicit"]), len(rejected),
          "：" + "；".join(rejected[:3]) if rejected else ""),
         args.json,
         {"ok": True, "added": added, "total": len(data["explicit"]),
          "rejected": rejected})


def build_candidates(data, manifest_path):
    dirs = data.get("whitelist_dirs") or default_dirs()
    explicit = []
    for p in data.get("explicit", []):
        ok, _ = validate_candidate(p, manifest_path, dirs)
        if ok:
            explicit.append(real(p))
    window = collect_window(
        data.get("existing_dirs") or dirs,
        float(data["started_epoch"]),
        manifest_path)
    return sorted(set(explicit) | set(window)), explicit, window, dirs


def cmd_list(args):
    data = load_manifest(args.file)
    candidates, explicit, window, dirs = build_candidates(data, args.file)
    payload = {
        "ok": True, "run_id": data.get("run_id", ""),
        "finished": data.get("finished", False),
        "explicit": len(explicit), "window": len(window),
        "candidates": len(candidates), "items": candidates,
        "whitelist_dirs": dirs,
    }
    if args.json:
        emit("", True, payload)
        return
    print("运行 ID：%s（起始 %s）" % (data.get("run_id", ""), data.get("started_at", "")))
    print("白名单目录：%s" % "、".join(dirs))
    print("显式登记 %d 个 / 时间窗口新增 %d 个 / 待删合计 %d 个" %
          (len(explicit), len(window), len(candidates)))
    if args.verbose:
        for p in candidates[:200]:
            print("  " + p)
        if len(candidates) > 200:
            print("  ...（其余 %d 个省略）" % (len(candidates) - 200))
    elif candidates:
        for p in candidates[:5]:
            print("  例如：" + p)
    print("（list 为只读 dry-run，未删除任何文件）")


def cmd_finish(args):
    data = load_manifest(args.file)
    if data.get("finished"):
        emit("[跳过] 本次运行已完成截图清理：%s" % json.dumps(
            data.get("cleaned", {}), ensure_ascii=False),
            args.json, {"ok": True, "already_finished": True,
                        "cleaned": data.get("cleaned", {})})
        return

    candidates, explicit, window, dirs = build_candidates(data, args.file)
    candidates = [p for p in candidates
                  if validate_candidate(p, args.file, dirs)[0]]

    payload_base = {
        "ok": True, "run_id": data.get("run_id", ""),
        "explicit": len(explicit), "window": len(window),
        "candidates": len(candidates), "whitelist_dirs": dirs,
    }

    if len(candidates) > args.max_delete:
        emit("[拒绝] 待删 %d 个，超过 --max-delete=%d 上限。为防误删全局缓存，"
             "本次不执行删除；请用 list --verbose 复核，或显式调大上限后重跑 finish。" %
             (len(candidates), args.max_delete),
             args.json, dict(payload_base, ok=False, deleted=0,
                             reason="超过删除上限"))
        return

    if not candidates:
        data["finished"] = True
        data["cleaned"] = {"deleted": 0, "failed": 0, "at": now_str()}
        save_manifest(args.file, data)
        if not args.keep_manifest:
            os.remove(args.file)
        emit("[ok] 本次运行没有产生需要清理的截图缓存（白名单目录无新增图片）。",
             args.json, dict(payload_base, deleted=0, failed=0,
                             manifest_removed=not args.keep_manifest))
        return

    # 先打印待删清单摘要，保证可追溯
    if not args.json:
        print("本次运行截图缓存清理：共 %d 个文件（显式登记 %d / 时间窗口新增 %d）" %
              (len(candidates), len(explicit), len(window)))
        print("白名单目录：%s" % "、".join(dirs))
        print("逐文件删除，每 %d 个一组校验；不用通配符、不删目录。" % BATCH_SIZE)
        for p in candidates[:5]:
            print("  例如：" + p)

    if args.keep:
        emit("[keep] 已按要求只列出、不删除；清单保留在 %s" % args.file,
             args.json, dict(payload_base, deleted=0, kept=True,
                             items=candidates if args.json else None))
        return

    deleted, failed, failures = 0, 0, []
    for i in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[i:i + BATCH_SIZE]
        for p in batch:
            try:
                os.remove(p)
            except OSError as exc:
                failed += 1
                failures.append("%s：%s" % (p, exc))
        # 每组校验：本组文件必须全部消失
        still = [p for p in batch if os.path.exists(p)]
        if still or failed:
            failures.append("第 %d 组校验失败，仍有 %d 个文件存在，立即停止" %
                            (i // BATCH_SIZE + 1, len(still)))
            break
        deleted += len(batch)

    remaining = len(candidates) - deleted
    cleaned = {
        "deleted": deleted, "failed": failed, "remaining": remaining,
        "at": now_str(), "dirs": dirs,
    }
    data["finished"] = True
    data["cleaned"] = cleaned
    save_manifest(args.file, data)
    if not args.keep_manifest and failed == 0 and remaining == 0:
        os.remove(args.file)
        manifest_removed = True
    else:
        manifest_removed = False

    lines = [
        "[ok] 截图缓存清理完成：删除 %d 个，失败 %d 个，剩余 %d 个" %
        (deleted, failed, remaining),
        "清单：%s" % ("已删除" if manifest_removed else "保留在 %s" % args.file),
    ]
    if failures:
        lines.append("失败明细（已停止，未继续盲删）：")
        lines.extend("  " + f for f in failures[:10])
    emit("\n".join(lines), args.json,
         dict(payload_base, deleted=deleted, failed=failed,
              remaining=remaining, failures=failures,
              manifest_removed=manifest_removed))


def build_parser():
    parser = argparse.ArgumentParser(
        description="掌握度助手运行截图缓存清理（白名单 + 逐文件删除）")
    parser.add_argument("--json", action="store_true", help="输出纯 ASCII JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("begin", help="建立本次运行截图清单（阶段 P 调用）")
    p.add_argument("--file", help="清单路径，默认自动生成带 run-id 的文件")
    p.add_argument("--run-id", help="运行标识，默认 时间戳+随机串")
    p.add_argument("--blobs-dir", help="覆盖图片缓存目录（一般不需要）")
    p.add_argument("--include-clipboard", action="store_true",
                   help="把 clipboard-images 也纳入扫描（默认不扫描，避免误删用户粘贴的图）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_begin)

    p = sub.add_parser("add", help="登记截图工具返回的落盘路径（可多次 --path）")
    p.add_argument("--file", required=True)
    p.add_argument("--path", action="append", help="截图落盘路径或 file:// URI")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="只读 dry-run：列出待删截图，不删除")
    p.add_argument("--file", required=True)
    p.add_argument("--verbose", action="store_true", help="打印全部路径（最多 200 个）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("finish", help="收尾：删除本次运行产生的截图缓存")
    p.add_argument("--file", required=True)
    p.add_argument("--keep", action="store_true", help="只列不删（复盘用）")
    p.add_argument("--keep-manifest", action="store_true",
                   help="清理后保留清单文件，便于审计")
    p.add_argument("--max-delete", type=int, default=DEFAULT_MAX_DELETE,
                   help="单次删除上限，默认 %d" % DEFAULT_MAX_DELETE)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_finish)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
