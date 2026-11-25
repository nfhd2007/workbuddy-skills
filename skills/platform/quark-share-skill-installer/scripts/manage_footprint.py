#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manage_footprint.py · 查看 / 清理本技能在磁盘上的足迹

本技能所有的写入都限定在 `<config>/runtimes/quark-installer/`（外加它安装技能的
目标目录）。`~/Downloads` 只被只读扫描，从不写入。这个脚本让「它到底写了我哪些
地方、占了多少空间、怎么删干净」变成一条可执行的命令，而不是让人去翻目录。

用法：
    python manage_footprint.py --json            # 只报告，不删除
    python manage_footprint.py --purge --yes     # 删除本技能自有运行时目录
    python manage_footprint.py --purge --yes --keep-python
                                                 # 只删下载缓存，保留便携 Python

安全约束（硬编码，不接受参数放宽）：
  * 只允许删除 `<config>/runtimes/quark-installer` 这一棵树；任何其他路径一律拒绝。
  * 拒绝删除 home、config 根、盘符根，以及符号链接指向外部的目录。
  * 不带 --yes 时只做 dry-run，打印将删除的路径。
  * 永不触碰 ~/Downloads、用户技能目录里的非本技能内容。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

RUNTIME_SUBPATH = ("runtimes", "quark-installer")
# --keep-python 要一并留下的文件：删了解释器还留着来源记录才谈得上可审计。
# 解释器**目录**不写死名字，靠内容识别（见 holds_interpreter）。
KEEP_WITH_PYTHON = {"python-provenance.json"}
# 一个被 --runtime-dir 指向的目录，只要含这些文件就足以证明是本技能写过的树
MARKER_FILES = ("last_preflight.json", "python-provenance.json")
# 判定"这是个解释器目录"的可执行文件名（全部小写比较；另加 python3.x 前缀规则）
INTERP_EXE_NAMES = {"python.exe", "python3.exe", "pythonw.exe", "python", "python3"}
INTERP_EXE_PREFIXES = ("python3.",)


def _setup_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def human_size(n):
    try:
        n = float(n)
    except Exception:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%.1f GB" % n


def dir_usage(p):
    total, files = 0, 0
    try:
        for root, dirs, names in os.walk(str(p)):
            # Never measure through a link: the target is not ours to count.
            dirs[:] = [d for d in dirs if not _is_link(Path(root) / d)]
            for n in names:
                try:
                    total += (Path(root) / n).stat().st_size
                    files += 1
                except OSError:
                    pass
    except Exception:
        pass
    return total, files


def config_dir():
    v = os.environ.get("WORKBUDDY_CONFIG_DIR", "").strip()
    if v:
        try:
            return Path(v).expanduser()
        except Exception:
            pass
    return Path.home() / ".workbuddy"


def runtime_root():
    """Resolve the tree this skill owns.

    QSI_RUNTIME_DIR comes first: preflight/bootstrap can be pointed elsewhere
    with --runtime-dir, and a cleanup script that ignored that override would
    refuse to act on the very directory the skill actually wrote to.
    """
    v = os.environ.get("QSI_RUNTIME_DIR", "").strip()
    if v:
        try:
            return Path(v).expanduser()
        except Exception:
            pass
    return config_dir().joinpath(*RUNTIME_SUBPATH)


def _plausible_owned_root(p):
    """A root reached through an override must still look like ours.

    Without this, `--runtime-dir <anything>` would make the ownership check
    tautological and turn a guard rail into a delete-anything flag.
    """
    try:
        if p.name.lower() == RUNTIME_SUBPATH[-1]:
            return True
        return any((p / m).is_file() for m in MARKER_FILES)
    except Exception:
        return False


def assert_owned(p):
    """Only ever act on <config>/runtimes/quark-installer."""
    try:
        rp = p.expanduser().resolve()
    except Exception as exc:
        raise SystemExit("无法解析路径 %s: %s" % (p, exc))
    expected = runtime_root()
    try:
        expected_r = expected.resolve()
    except Exception:
        expected_r = expected
    default_r = _safe_resolve(config_dir().joinpath(*RUNTIME_SUBPATH))
    if default_r is not None and expected_r != default_r and not _plausible_owned_root(expected_r):
        raise SystemExit(
            "拒绝操作：--runtime-dir / QSI_RUNTIME_DIR 指向的 %s 不像本技能的运行时目录"
            "（应命名为 %s，或其中存在 %s）"
            % (expected_r, RUNTIME_SUBPATH[-1], " / ".join(MARKER_FILES)))
    if rp != expected_r:
        raise SystemExit("拒绝操作：%s 不是本技能自有目录（应为 %s）" % (rp, expected_r))
    # Defence in depth, not the primary gate: by construction rp is two levels
    # below the config root, so this can only fire if RUNTIME_SUBPATH changes.
    # Both sides are guarded — a resolve() failure must not escape as a traceback.
    for label, guard in (("用户主目录", _home()),
                         ("配置根目录", _safe_resolve(config_dir()))):
        if guard is not None and rp == guard:
            raise SystemExit("拒绝操作：目标等同于%s" % label)
    if rp.parent == rp:
        raise SystemExit("拒绝操作：目标是文件系统根")
    if _is_link(p):
        raise SystemExit("拒绝操作：目标是符号链接或 junction，可能指向别处")
    return rp


def _safe_resolve(p):
    """`resolve()` raises on a missing drive, a symlink loop or illegal chars.

    Guard rails must never crash the very command that is supposed to delete
    things, so every resolve here degrades to None instead of propagating.
    """
    try:
        return p.expanduser().resolve()
    except Exception:
        return None


def _home():
    """`Path.home()` itself raises RuntimeError when HOME/USERPROFILE is unset."""
    try:
        return _safe_resolve(Path.home())
    except Exception:
        return None


def _is_link(p):
    """Symlink *or* Windows junction.

    `Path.is_symlink()` returns False for junctions, so a junction inside the
    runtime dir would be walked into (footprint over-counts someone else's
    files) and could be deleted through, taking the target's contents with it.
    """
    try:
        if p.is_symlink():
            return True
        isj = getattr(os.path, "isjunction", None)
        return bool(isj and isj(str(p)))
    except OSError:
        return False


def _looks_like_interpreter(name):
    n = name.lower()
    return n in INTERP_EXE_NAMES or n.startswith(INTERP_EXE_PREFIXES)


def holds_interpreter(p, max_depth=3):
    """True when this tree actually contains an interpreter binary.

    Matching the directory *name* against `python-*` was wrong twice over: it
    deleted `pythons/` (the tree uv populates) even with --keep-python, and it
    would have spared any unrelated `python-old` leftover. Decide by content,
    depth-limited so the walk stays cheap on a 22 MB portable runtime.
    """
    try:
        if not p.is_dir() or _is_link(p):
            return False
        base = len(p.parts)
        for root, dirs, names in os.walk(str(p)):
            if len(Path(root).parts) - base >= max_depth:
                dirs[:] = []
            for n in names:
                if _looks_like_interpreter(n):
                    return True
    except Exception:
        return False
    return False


def kept_entries(items):
    """Entries --keep-python must leave alone: interpreters plus provenance."""
    kept = set()
    for it in items:
        if it["kind"] == "dir" and holds_interpreter(Path(it["path"])):
            kept.add(it["path"])
        elif it["kind"] == "file" and it["name"] in KEEP_WITH_PYTHON:
            kept.add(it["path"])
    return kept


def children_only(items):
    """Every child of the owned root except what --keep-python preserves."""
    kept = kept_entries(items)
    return [Path(it["path"]) for it in items if it["path"] not in kept]


def collect(root):
    items = []
    if not root.is_dir():
        return items
    try:
        children = sorted(root.iterdir(), key=lambda x: x.name.lower())
    except Exception:
        return items
    for c in children:
        try:
            if _is_link(c):
                items.append({"name": c.name, "kind": "symlink", "bytes": 0, "files": 0,
                              "path": str(c)})
                continue
            if c.is_dir():
                b, f = dir_usage(c)
                items.append({"name": c.name, "kind": "dir", "bytes": b, "files": f,
                              "path": str(c)})
            else:
                b = c.stat().st_size
                items.append({"name": c.name, "kind": "file", "bytes": b, "files": 1,
                              "path": str(c)})
        except OSError:
            continue
    return items


def blank_report(root="", home=None):
    """Single source of truth for the report shape.

    Both the success path and the refusal path build on this: a guard-rail
    SystemExit used to produce a half-populated dict and the human printer
    crashed with KeyError, so the refusal message never reached the user.
    """
    return {
        "ok": True,
        "runtime_root": str(root) if root else "",
        "exists": False,
        "bytes": 0,
        "files": 0,
        "items": [],
        "read_only_scanned": str(home / "Downloads") if home else "~/Downloads",
        "writes_outside_this_root": "none by design; ~/Downloads is only read",
        "purged": [],
        "skipped": [],
        "preserved": [],
        "dry_run": True,
        "message": "",
    }


def run(args):
    # Same override the bootstrap scripts accept, applied before anything is
    # measured: measuring one tree and deleting another would be worse than
    # refusing outright.
    explicit = (getattr(args, "runtime_dir", "") or "").strip()
    if explicit:
        os.environ["QSI_RUNTIME_DIR"] = explicit
    root = runtime_root()
    # Validate ownership *before* walking: with --runtime-dir pointing at
    # somewhere huge (home, a drive root) the measure-first order meant the
    # guard only fired after scanning everything under it.
    assert_owned(root)
    home = _home()
    report = blank_report(root, home)
    report["exists"] = root.is_dir()
    total_b, total_f = dir_usage(root)
    report["bytes"], report["files"] = total_b, total_f
    report["items"] = collect(root)
    report["human"] = human_size(total_b)

    if not root.is_dir():
        report["message"] = "本技能尚未写入任何内容（运行时目录不存在）"
        return report

    if not args.purge:
        report["message"] = ("本技能共占用 %s（%d 个文件），全部位于 %s；如需清理：--purge --yes"
                             % (human_size(total_b), total_f, root))
        return report

    rp = assert_owned(root)

    # A Windows process cannot delete the interpreter it is running on, so the
    # directory holding sys.executable is always skipped and reported instead of
    # failing the whole purge.
    try:
        running = Path(sys.executable).resolve()
    except Exception:
        running = None

    def holds_running(p):
        if running is None:
            return False
        try:
            c = p.resolve()
        except Exception:
            return False
        return c == running or c in running.parents

    if args.keep_python:
        targets = children_only(report["items"])
    else:
        targets = [rp]

    # Purging everything while running on this very interpreter would be a
    # no-op (the whole root is protected), so degrade to per-child deletion.
    if targets == [rp] and holds_running(rp):
        targets = children_only(report["items"])

    skipped = [t for t in targets if holds_running(t)]
    targets = [t for t in targets if t not in skipped]
    if targets == [rp]:
        preserved = []
    else:
        gone = {str(t) for t in targets}
        preserved = [it["path"] for it in report["items"] if it["path"] not in gone]
    report["preserved"] = preserved

    if not args.yes:
        report["dry_run"] = True
        report["purged"] = [str(t) for t in targets]
        report["skipped"] = [str(t) for t in skipped]
        msg = ("dry-run：将删除 %d 项（共 %s）" % (len(targets), human_size(total_b)))
        if skipped:
            msg += "，跳过正在使用的解释器目录 %d 项" % len(skipped)
        if preserved:
            msg += "，保留 %d 项（%s）" % (len(preserved),
                                      ", ".join(Path(p).name for p in preserved[:4]))
        report["message"] = msg + "。确认无误后加 --yes 执行。"
        return report

    removed, failed = [], []
    for t in targets:
        try:
            if t == rp:
                assert_owned(t)
            else:
                _assert_inside(t, rp)
        except SystemExit as exc:
            report["ok"] = False
            report["message"] = str(exc)
            return report
        try:
            if t.is_dir() and not _is_link(t):
                shutil.rmtree(str(t))
            elif t.exists():
                t.unlink()
            removed.append(str(t))
        except Exception as exc:
            failed.append("%s: %s" % (type(exc).__name__, exc))

    left_b, left_f = dir_usage(rp if rp.exists() else root)
    report["dry_run"] = False
    report["purged"] = removed
    report["skipped"] = [str(t) for t in skipped]
    report["bytes_after"] = left_b
    if failed:
        report["ok"] = False
        report["message"] = "部分删除失败：%s；已删除 %d 项" % ("; ".join(failed[:3]), len(removed))
        return report

    msg = "已清理 %d 项（释放约 %s），当前剩余 %s" % (
        len(removed), human_size(total_b - left_b), human_size(left_b))
    if skipped:
        msg += ("；因该解释器正在运行而保留 %s，改用其它 Python 再执行一次可彻底清空"
                % ", ".join(Path(s).name for s in skipped))
    elif preserved and left_b:
        why = "（--keep-python）" if args.keep_python else "（解释器目录与来源记录不随缓存清理）"
        msg += "；保留 %s%s" % (", ".join(Path(p).name for p in preserved[:4]), why)
    report["message"] = msg
    return report


def _assert_inside(child, root):
    """A child of the owned root: still must not escape it via symlink/parent."""
    try:
        c = child.expanduser().resolve()
    except Exception as exc:
        raise SystemExit("无法解析路径 %s: %s" % (child, exc))
    if root not in c.parents and c != root:
        raise SystemExit("拒绝操作：%s 不在本技能自有目录内" % c)
    if _is_link(child):
        raise SystemExit("拒绝操作：%s 是符号链接或 junction" % child)
    return c


def print_human(rep):
    print("=" * 72)
    print("夸克分享技能安装器 · 磁盘足迹")
    print("=" * 72)
    if not rep.get("ok") and not rep.get("runtime_root"):
        print("已拒绝 : %s" % (rep.get("error") or rep.get("message") or "未知原因"))
        print("=" * 72)
        return
    print("运行时目录 : %s" % rep["runtime_root"])
    print("占用       : %s（%d 个文件）" % (rep.get("human", human_size(rep["bytes"])), rep["files"]))
    print("只读扫描   : %s（从不写入）" % rep["read_only_scanned"])
    for it in rep["items"]:
        print("   - %-34s %10s  %d 个文件" % (it["name"], human_size(it["bytes"]), it["files"]))
    if rep["message"]:
        print("说明       : %s" % rep["message"])
    if rep.get("skipped"):
        for t in rep["skipped"]:
            print("   已跳过   : %s（正在使用）" % t)
    if rep.get("preserved"):
        for t in rep["preserved"]:
            print("   保留     : %s" % t)
    if rep["dry_run"] is False:
        for t in rep["purged"]:
            print("   已删除   : %s" % t)
    print("=" * 72)


def main(argv=None):
    _setup_console()
    ap = argparse.ArgumentParser(description="查看/清理本技能的磁盘足迹")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--purge", action="store_true", help="删除本技能自有运行时目录")
    ap.add_argument("--keep-python", action="store_true",
                    help="配合 --purge：保留便携 Python，只清下载缓存与报告")
    ap.add_argument("--yes", action="store_true", help="确认真正执行删除（否则 dry-run）")
    ap.add_argument("--runtime-dir",
                    help="Override the owned runtime dir (must match the one preflight/bootstrap used)")
    args = ap.parse_args(argv)

    try:
        rep = run(args)
    except SystemExit as exc:
        rep = blank_report()
        rep.update(ok=False, error=str(exc), message=str(exc))
    except Exception as exc:  # noqa: BLE001
        rep = blank_report()
        rep.update(ok=False, error="%s: %s" % (type(exc).__name__, exc),
                   message=str(exc))

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_human(rep)
    return 0 if rep.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
