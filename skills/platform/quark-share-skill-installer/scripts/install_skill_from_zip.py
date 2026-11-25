#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_skill_from_zip.py · 审查并安装技能压缩包

压缩包一律视为不可信输入：它通常来自他人分享的夸克网盘链接。包内任何内容
都不会被执行；只以纯文本方式解析 SKILL.md 的 YAML frontmatter，且在写入
第一个字节之前逐条校验所有路径。

v1.3.7 审查加固：用 ZipInfo.orig_filename 检查已被 zipfile 截断的 NUL；
拒绝重复条目名（否则报告展示第一条、落盘写最后一条）；报告中的所有归档
文本经 safe_label 转义控制字符与双向覆写；新增累计压缩比，堵住把炸弹切成
若干 <1 MB 文件绕过单文件比的做法；嵌套技能在报告里显式提示。

标准两阶段用法（阶段 1 强制审查，阶段 2 才安装）：

    python install_skill_from_zip.py skill.zip --scope user --dry-run --json
    python install_skill_from_zip.py skill.zip --scope user --json
    python install_skill_from_zip.py skill.zip --scope user --backup-existing --json

退出码：成功 0，出错 1。使用 --json 时，stdout 只输出一个 JSON 对象，
所有诊断信息走 stderr。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

# Skills-root resolution is shared with preflight.py / quark_share_download.py;
# a second copy here is what let "install to X, preflight reads Y" happen.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _skills_paths import install_skills_root
except ImportError as _exc:  # pragma: no cover - 技能包不完整
    sys.stderr.write(
        "缺少 scripts/_skills_paths.py（技能包不完整）: %s\n"
        "请重新安装/重新分发本技能包，确保 scripts/ 目录完整\n" % _exc)
    raise SystemExit(2)

# ---------------------------------------------------------------------------
# Hard limits (zip-bomb / abuse guards)
# ---------------------------------------------------------------------------
MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024   # 200 MB across the whole archive
MAX_SINGLE_FILE = 100 * 1024 * 1024          # 100 MB per file
MAX_FILES = 2000
MAX_COMPRESSION_RATIO = 200                  # per-file, only for files > 1 MB
MAX_SKILL_MD_BYTES = 512 * 1024
MAX_EXCERPT_CHARS = 1500
# 累计压缩比只在解压量超过 1 MB 后才判定，避免把几 KB 的正常技能包误判成炸弹。
CUMULATIVE_RATIO_MIN_BYTES = 1024 * 1024

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

SUSPICIOUS_EXTS = {
    ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".ps1", ".psm1",
    ".vbs", ".vbe", ".scr", ".msi", ".com", ".jar", ".sh", ".bash",
    ".apk", ".reg", ".hta", ".lnk",
}
NOISE_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
NOISE_MARKERS = ("__macosx/",)

SCRIPT_EXTS = {".py", ".js", ".ts", ".sh", ".ps1", ".bat", ".cmd", ".rb", ".pl"}


def _setup_console():
    """Make UTF-8 output work on Windows consoles without crashing on CJK."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def log(msg: str):
    print(msg, file=sys.stderr, flush=True)


def safe_label(value: str, keep_newlines: bool = False) -> str:
    """Escape control characters coming from an untrusted archive.

    Archive-controlled text (file names, frontmatter values, SKILL.md body) is
    pasted into human-readable reports verbatim. A newline in a file name can
    forge a report line that looks like an audit verdict; RTL override and
    zero-width characters can make a file name look like something else.
    Everything that enters a report goes through here first.

    Newlines are kept only for multi-line text (SKILL.md excerpt), where they
    are the document structure, report output, not attacker-controlled framing.
    """
    named = {"\r": r"\r", "\n": r"\n", "\t": r"\t", "\x00": r"\x00",
             "\x1b": r"\x1b", "\v": r"\v", "\f": r"\f"}
    out = []
    for ch in value:
        cp = ord(ch)
        if ch == "\n" and keep_newlines:
            out.append(ch)
        elif ch in named:
            out.append(named[ch])
        elif cp < 0x20 or cp == 0x7F or 0x80 <= cp <= 0x9F:
            out.append(r"\x%02x" % cp)
        elif (0x202A <= cp <= 0x202E) or (0x2066 <= cp <= 0x2069) or cp in (0x200B, 0x200C, 0x200D, 0xFEFF):
            # Bidirectional override / zero-width / BOM: never show invisibly.
            out.append(r"\u%04x" % cp)
        else:
            out.append(ch)
    return "".join(out)


class InstallError(Exception):
    pass


# ---------------------------------------------------------------------------
# Archive audit
# ---------------------------------------------------------------------------
def normalize(name: str) -> str:
    """Normalize separators; Windows-created zips sometimes contain '\\'."""
    return name.replace("\\", "/")


def is_noise(raw: str) -> bool:
    low = raw.lower()
    if any(marker in low for marker in NOISE_MARKERS):
        return True
    return PurePosixPath(raw).name.lower() in NOISE_NAMES


def audit_archive(zf: zipfile.ZipFile):
    """Return (errors, warnings, entries). entries = [(ZipInfo, normalized_name)].

    Every check runs before a single byte is written. Besides the per-entry
    checks, a cumulative compression ratio closes the "slice the bomb into
    sub-1MB chunks" hole, and the raw archive name is checked for NUL bytes
    because ZipInfo.filename has already been truncated at the first NUL.
    """
    errors, warnings, entries = [], [], []
    total = 0
    total_compressed = 0
    seen_files = set()

    for info in zf.infolist():
        original = normalize(getattr(info, "orig_filename", info.filename))
        raw = normalize(info.filename)
        while raw.startswith("./"):
            raw = raw[2:]
        if not raw:
            continue

        # ZipInfo.__init__ truncates at the first NUL; only orig_filename still
        # holds what the archive declared. Without this, a name like
        # "payload.sh\x00.txt" silently lands as "payload.sh".
        if "\x00" in original:
            errors.append(
                "拒绝含空字符的归档路径（解析层会截断，可造成文件名/扩展名伪装）: %s"
                % safe_label(original))
            continue

        # The report reads the first entry with a given path while extraction
        # writes the last one. Duplicate names therefore break "what you
        # reviewed is what got installed", so refuse the whole archive.
        is_dir_entry = info.is_dir() or raw.endswith("/")
        if not is_dir_entry:
            if raw in seen_files:
                errors.append(
                    "拒绝重复条目名（审查展示与落盘写入可能不是同一份内容）: %s"
                    % safe_label(raw))
                continue
            seen_files.add(raw)

        parts = raw.rstrip("/").split("/")
        unsafe = (
            raw.startswith("/")
            or re.match(r"^[A-Za-z]:", raw) is not None
            or ".." in parts
            or "\x00" in raw
        )
        if unsafe:
            errors.append(
                "拒绝不安全的归档路径（绝对路径 / 盘符 / 含 .. 的段；按失败即关闭原则，"
                "规范化后可能仍在目录内也整体拒绝）: %s" % safe_label(raw))
            continue

        # Unix symlink bit, when the archive carries real Unix mode bits.
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and (mode & 0o170000) == 0o120000:
            errors.append("拒绝符号链接条目: %s" % safe_label(raw))
            continue

        if info.flag_bits & 0x1:
            errors.append("拒绝加密条目（无法读取，也可能是规避检查）: %s" % safe_label(raw))
            continue

        if info.file_size > MAX_SINGLE_FILE:
            errors.append("单文件超过 %d MB，已拒绝: %s"
                          % (MAX_SINGLE_FILE // 1024 // 1024, safe_label(raw)))
            continue

        if info.compress_size > 0 and info.file_size > 1024 * 1024:
            ratio = info.file_size / info.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                errors.append("压缩比异常（疑似 zip 炸弹），已拒绝: %s (%.0f:1)"
                              % (safe_label(raw), ratio))
                continue

        total += info.file_size
        total_compressed += max(info.compress_size, 0)
        if total > MAX_TOTAL_UNCOMPRESSED:
            errors.append("解压后总大小超过 %d MB，已拒绝" % (MAX_TOTAL_UNCOMPRESSED // 1024 // 1024))
            break

        ext = PurePosixPath(raw).suffix.lower()
        if ext in SUSPICIOUS_EXTS and not is_noise(raw):
            warnings.append("包含可执行文件/脚本，安装后请勿自动运行: %s" % safe_label(raw))

        entries.append((info, raw))

    # A sliced bomb keeps every file just under 1 MB, so the per-file ratio
    # never fires. Cumulative expansion is still observable; judge it once over
    # the whole archive, and only when the archive is big enough that small
    # skill packages are not false positives.
    if total > CUMULATIVE_RATIO_MIN_BYTES and total_compressed > 0:
        cumulative = total / total_compressed
        if cumulative > MAX_COMPRESSION_RATIO and not any("总大小超过" in e for e in errors):
            errors.append(
                "累计压缩比异常（疑似切片式 zip 炸弹），已拒绝: %.0f:1 "
                "（解压 %d bytes / 压缩 %d bytes）" % (cumulative, total, total_compressed))

    if len(entries) > MAX_FILES:
        errors.append("文件数超过 %d，已拒绝" % MAX_FILES)

    return errors, warnings, entries


# ---------------------------------------------------------------------------
# Skill discovery inside the archive
# ---------------------------------------------------------------------------
def find_skill_roots(entries):
    roots = []
    for _, raw in entries:
        if is_noise(raw):
            continue
        p = PurePosixPath(raw)
        if p.name.lower() == "skill.md":
            parent = str(p.parent)
            if parent == ".":
                parent = ""
            if parent not in roots:
                roots.append(parent)
    return roots


def read_entry_text(zf, entries, wanted: str) -> str:
    for info, raw in entries:
        if raw == wanted:
            with zf.open(info) as fh:
                data = fh.read(MAX_SKILL_MD_BYTES)
            return data.decode("utf-8", errors="replace")
    return ""


def parse_frontmatter(text: str):
    """Minimal, non-executing YAML frontmatter reader (no PyYAML dependency)."""
    if not text.lstrip("\ufeff").startswith("---"):
        return None, "SKILL.md 缺少 YAML frontmatter（必须以 --- 开头）"
    lines = text.lstrip("\ufeff").splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return None, "SKILL.md 的 frontmatter 未闭合"

    fm, key = {}, None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if val in (">", "|", ">-", "|-", ">+", "|+"):
                val = ""
            elif len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                val = val[1:-1]
            fm[key] = val
        elif key and (line.startswith(" ") or line.startswith("\t")):
            fm[key] = (fm.get(key, "") + " " + line.strip()).strip()
    return fm, None


def slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:64] or "imported-skill"


def decide_name(fm, root: str, zip_path: Path, override):
    if override:
        name = override
        source = "--name"
    elif fm.get("name"):
        name = fm["name"]
        source = "SKILL.md frontmatter"
    elif root:
        name = slugify(PurePosixPath(root).name)
        source = "zip 内目录名"
    else:
        name = slugify(zip_path.stem)
        source = "zip 文件名"
    if not NAME_RE.match(name):
        return None, None, "技能名 %r 不合法（需小写字母/数字/连字符，且与目录名一致）" % name
    return name, source, None


def files_under(entries, root: str):
    out = []
    for info, raw in entries:
        if is_noise(raw):
            continue
        if root:
            if not (raw == root or raw.startswith(root + "/")):
                continue
            rel = raw[len(root):].lstrip("/")
        else:
            rel = raw
        if not rel:
            continue
        out.append((info, rel))
    return out


def build_skill_record(zf, entries, root: str, zip_path: Path, name_override):
    skill_md_path = (root + "/" if root else "") + "SKILL.md"
    text = read_entry_text(zf, entries, skill_md_path)
    if not text:
        # Case-insensitive fallback for SKILL.md spelling.
        for _, raw in entries:
            if PurePosixPath(raw).name.lower() == "skill.md" and (root == "" or raw.startswith(root + "/")):
                text = read_entry_text(zf, entries, raw)
                break
    fm, err = parse_frontmatter(text)
    if err:
        raise InstallError("%s: %s" % (skill_md_path, err))

    name, name_source, err = decide_name(fm, root, zip_path, name_override)
    if err:
        raise InstallError(err)

    warnings = []
    if root and PurePosixPath(root).name != name:
        warnings.append("zip 内目录名 %r 与 frontmatter name %r 不一致，将按 %r 安装" % (
            safe_label(PurePosixPath(root).name), name, name))

    description = fm.get("description", "").strip()
    if not description:
        raise InstallError("%s: frontmatter 缺少非空的 description" % skill_md_path)
    description = safe_label(re.sub(r"\s+", " ", description))

    files = files_under(entries, root)
    total_size = sum(i.file_size for i, _ in files)
    scripts, suspicious = [], []
    for _, rel in files:
        ext = PurePosixPath(rel).suffix.lower()
        if rel.startswith("scripts/") or ext in SCRIPT_EXTS:
            scripts.append(safe_label(rel))
        if ext in SUSPICIOUS_EXTS:
            suspicious.append(safe_label(rel))

    return {
        "name": name,
        "name_source": name_source,
        "description": description,
        "root": root or "(zip 根目录)",
        "agent_created": fm.get("agent_created", ""),
        "file_count": len(files),
        "total_size": total_size,
        "has_scripts": bool(scripts),
        "scripts": scripts[:30],
        "suspicious_files": suspicious[:30],
        # Excerpt is untrusted TEXT, not instructions. Keep its line structure
        # but neutralise invisible/bidirectional/ANSI control characters so it
        # cannot be used to forge report lines or disguise its own content.
        "skill_md_excerpt": safe_label(text[:MAX_EXCERPT_CHARS], keep_newlines=True),
        "warnings": warnings,
        "_files": files,
    }


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
def default_skills_root() -> Path:
    """The same root preflight reports as `dirs.skills` -- by construction.

    The order (QSI_SKILLS_DIR -> the root this skill was loaded from ->
    <config>/skills) lives in _skills_paths and is called from both places, so
    `--scope user` can no longer install into a root preflight never looked at.
    """
    return install_skills_root(Path(__file__).resolve().parent.parent)


def resolve_skills_dir(args) -> Path:
    if args.target_dir:
        return Path(args.target_dir).expanduser().resolve()
    if args.scope == "project":
        return (Path.cwd() / ".workbuddy" / "skills").resolve()
    return default_skills_root().resolve()


def safe_join(target: Path, rel: str) -> Path:
    dest = (target / rel).resolve()
    root = target.resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        raise InstallError("拒绝写出目标目录之外的路径: %s" % rel)
    return dest


def install_one(zf, record, skills_dir: Path, backup_existing: bool, dry_run: bool):
    target = skills_dir / record["name"]
    conflict = target.exists()
    record["conflict"] = conflict
    record["install_path"] = str(target)

    # A dry-run must always produce a report, even when the target already
    # exists: the conflict itself is information the user needs to review.
    if dry_run:
        record["installed"] = False
        return record

    if conflict and not backup_existing:
        raise InstallError(
            "目标已存在: %s\n默认不覆盖。请先将审查报告交给用户确认，确认后加 --backup-existing "
            "（会把旧目录移动到 .backups/ 再安装）。" % target
        )

    if conflict and backup_existing:
        backup_root = skills_dir / ".backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = backup_root / ("%s-%s" % (record["name"], stamp))
        shutil.move(str(target), str(dest))
        record["backup"] = str(dest)
        log("已备份旧技能: %s -> %s" % (target, dest))

    target.mkdir(parents=True, exist_ok=True)
    for info, rel in record["_files"]:
        dest = safe_join(target, rel)
        if info.is_dir() or rel.endswith("/"):
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out, 256 * 1024)

    if not (target / "SKILL.md").exists():
        raise InstallError("安装后未找到 SKILL.md，可能压缩包结构异常: %s" % target)
    record["installed"] = True
    log("已安装技能: %s (%d 个文件)" % (target, record["file_count"]))
    return record


def public_record(record):
    return {k: v for k, v in record.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_human(result):
    print("=" * 72)
    print("WorkBuddy 技能包审查报告")
    print("=" * 72)
    print("压缩包 : %s" % result["zip"])
    print("压缩包大小: %s bytes" % result["zip_size"])
    print("安装位置: %s  (scope=%s)" % (result["skills_dir"], result["scope"]))
    print("模式   : %s" % ("仅审查 (dry-run)" if result["dry_run"] else "执行安装"))
    print()
    if result["audit"]["errors"]:
        print("[阻断项]")
        for e in result["audit"]["errors"]:
            print("  - %s" % e)
    if result["audit"]["warnings"]:
        print("[提醒]")
        for w in result["audit"]["warnings"]:
            print("  - %s" % w)
    if not result["audit"]["errors"] and not result["audit"]["warnings"]:
        print("安全检查: 通过（路径/空字符/重复条目/符号链接/加密/体积与压缩比均正常）")
    print()
    for s in result["skills"]:
        print("-" * 72)
        print("技能名     : %s   (来源: %s)" % (s["name"], s["name_source"]))
        print("描述       : %s" % s["description"][:160])
        print("zip 内根   : %s" % safe_label(s["root"]))
        print("文件数/大小: %d / %s bytes" % (s["file_count"], s["total_size"]))
        print("含脚本     : %s" % ("是 -> %s" % ", ".join(s["scripts"][:8]) if s["has_scripts"] else "否"))
        if s["suspicious_files"]:
            print("可疑文件   : %s" % ", ".join(s["suspicious_files"]))
        print("目标已存在 : %s" % ("是（需 --backup-existing）" if s["conflict"] else "否"))
        for w in s["warnings"]:
            print("提醒       : %s" % w)
        print("SKILL.md 开头:")
        for line in s["skill_md_excerpt"].splitlines()[:12]:
            print("    | %s" % line)
    print("-" * 72)
    if result["dry_run"]:
        print("这是 dry-run，未写入任何文件。将以上内容给用户确认后再执行安装。")
    elif result["partial"]:
        print("部分安装: 已装 %s；失败 %s"
              % (", ".join(result["installed"]), ", ".join(result["failed"])))
        print("已装成的那部分不会自动回滚，重装前请先确认是否要保留。")
    else:
        print("已安装: %s" % ", ".join(result["installed"]) if result["installed"] else "未安装任何技能。")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    _setup_console()
    ap = argparse.ArgumentParser(
        description="Inspect / install a WorkBuddy skill zip (untrusted input).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("zip", help="Path to the skill .zip")
    ap.add_argument("--scope", choices=["user", "project"], default="user",
                    help="user=~/.workbuddy/skills (default), project=./.workbuddy/skills")
    ap.add_argument("--target-dir", help="Explicit skills root directory; overrides --scope")
    ap.add_argument("--name", help="Override the installed skill directory name")
    ap.add_argument("--dry-run", action="store_true", help="Audit only, write nothing")
    ap.add_argument("--backup-existing", action="store_true",
                    help="If the target exists, move it to .backups/ before installing")
    ap.add_argument("--json", action="store_true", help="Emit a single JSON object on stdout")
    args = ap.parse_args()

    result = {
        "ok": False, "zip": "", "zip_size": 0, "scope": args.scope,
        "skills_dir": "", "dry_run": args.dry_run,
        "audit": {"errors": [], "warnings": []},
        "skills": [], "installed": [], "failed": [], "partial": False, "error": "",
    }

    try:
        zip_path = Path(args.zip).expanduser().resolve()
        if not zip_path.is_file():
            raise InstallError("找不到压缩包: %s" % zip_path)
        if not zipfile.is_zipfile(zip_path):
            raise InstallError("不是有效的 zip 文件（可能下载未完成，或分享的是分卷/改后缀文件）: %s" % zip_path)

        result["zip"] = str(zip_path)
        result["zip_size"] = zip_path.stat().st_size
        skills_dir = resolve_skills_dir(args)
        result["skills_dir"] = str(skills_dir)

        with zipfile.ZipFile(zip_path, "r") as zf:
            errors, warnings, entries = audit_archive(zf)
            result["audit"]["errors"] = errors
            result["audit"]["warnings"] = warnings
            if errors:
                raise InstallError("归档安全检查未通过，共 %d 项；未写入任何文件。" % len(errors))

            roots = find_skill_roots(entries)
            if not roots:
                raise InstallError("压缩包内没有找到 SKILL.md，这不是合法的 WorkBuddy 技能包。")

            # A root-level skill takes every archive entry, including the
            # subtree of another skill root. That installs the same files twice.
            # It is not an escape, so report it instead of silently blocking a
            # package the user may legitimately want.
            for parent in roots:
                for child in roots:
                    if parent == child:
                        continue
                    if parent == "" or child.startswith(parent + "/"):
                        result["audit"]["warnings"].append(
                            "[%s] 与 [%s] 存在嵌套关系：子技能的文件会随父技能一并落盘，"
                            "安装后将出现两份副本，请确认这是预期结构"
                            % (safe_label(parent or "(zip 根)"), safe_label(child)))

            records = [build_skill_record(zf, entries, r, zip_path, args.name) for r in roots]
            names = [r["name"] for r in records]
            if len(set(names)) != len(names):
                raise InstallError("压缩包内多个技能解析出同名目录: %s" % names)

            # Aggregate per-skill warnings into the report.
            for r in records:
                for w in r["warnings"]:
                    result["audit"]["warnings"].append("[%s] %s" % (r["name"], w))

            if not args.dry_run and not skills_dir.exists():
                skills_dir.mkdir(parents=True, exist_ok=True)
                log("已创建技能目录: %s" % skills_dir)

            # One bad skill must not abort the rest silently, and a partial run
            # must never be reported as a clean "ok". Skills are independent
            # directories, so installing them independently is honest; leaving
            # the earlier ones behind without saying so is not.
            failed = []
            for r in records:
                try:
                    install_one(zf, r, skills_dir, args.backup_existing, args.dry_run)
                except Exception as exc:  # noqa: BLE001 - per-skill isolation
                    r["installed"] = False
                    r["error"] = "%s: %s" % (type(exc).__name__, exc)
                    failed.append(r["name"])
                    log("安装失败: %s (%s)" % (r["name"], r["error"]))
                result["skills"].append(public_record(r))
                if r.get("installed"):
                    result["installed"].append(r["name"])

            result["failed"] = failed
            if failed:
                result["ok"] = False
                result["partial"] = bool(result["installed"])
                msg = "%d 个技能安装失败: %s" % (len(failed), ", ".join(failed))
                if result["partial"]:
                    msg += ("；已装成的 %s 不会自动回滚——如需重试，请连同它们一起看"
                            % ", ".join(result["installed"]))
                result["error"] = msg
            else:
                result["ok"] = True
                result["message"] = (
                    "审查完成（dry-run，未安装）" if args.dry_run
                    else "已安装 %d 个技能" % len(result["installed"])
                )

    except InstallError as exc:
        result["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - surface everything as structured output
        result["error"] = "%s: %s" % (type(exc).__name__, exc)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["ok"]:
            print("错误: %s" % result["error"], file=sys.stderr)
            if result["audit"]["errors"]:
                for e in result["audit"]["errors"]:
                    print("  - %s" % e, file=sys.stderr)
            # A partial run must still show which skills landed and why the
            # rest failed; otherwise the only visible line is a bare "错误".
            if result["skills"]:
                print_human(result)
        else:
            print_human(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
