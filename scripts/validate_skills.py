#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 skills/ 下的技能是否符合本仓库规范（纯 Python 标准库）。

用法: python scripts/validate_skills.py [--root <仓库根目录>]
退出码: 0 = 无 ERROR, 1 = 存在 ERROR
"""
import argparse
import os
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.]+)?$")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             ".archive", ".cx", ".idea", ".vscode", "__MACOSX"}
BAD_FILE_RE = re.compile(
    r"(\.pyc$|\.log$|\.zip$|\.7z$|\.exe$|^cookies?\.json$|^answers\.json$|"
    r"^questions\.json$|^before_submit\.|^Thumbs\.db$|^\.DS_Store$|^\.env(\.|$))",
    re.I)
TEXT_EXT = {".md", ".py", ".js", ".mjs", ".cjs", ".ts", ".json", ".sh", ".ps1",
            ".bat", ".cmd", ".yaml", ".yml", ".txt", ".toml", ".ini", ".cfg",
            ".html", ".css", ".svg", ".xml"}
SECRET_RES = [
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "私钥内容"),
    (re.compile(r"\b(?:sk|ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "疑似 API Token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub PAT"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS Access Key"),
    (re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]"), "硬编码凭据"),
]
HOME_PATH_RE = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/[^/\s]+/|/home/[^/\s]+/)")
REF_RE = re.compile(r"(?:references|scripts|assets)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]+")
MAX_BYTES = 3 * 1024 * 1024


def parse_frontmatter(text):
    """极简 YAML frontmatter 解析，够用于 SKILL.md（不依赖 PyYAML）。"""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, "首行必须是 ---（注意不要写成 \\---）"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, "frontmatter 缺少结束行 ---"
    data, last = {}, None
    for line in lines[1:end]:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            data[key] = "" if val in ("|", ">") else val
            last = key
        elif s.startswith("- ") and last:
            if not isinstance(data.get(last), list):
                data[last] = []
            data[last].append(s[2:].strip().strip("\"'"))
    return data, None


def find_skills(root):
    out = []
    base = root / "skills"
    if not base.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if "SKILL.md" in filenames:
            out.append(Path(dirpath))
    return sorted(out)


def walk_files(folder):
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args()
    root = Path(args.root).resolve()
    errors, warnings = [], []
    skills = find_skills(root)

    for d in skills:
        rel = d.relative_to(root).as_posix()
        raw = (d / "SKILL.md").read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            errors.append(rel + "/SKILL.md: 含 UTF-8 BOM")
        if b"\r\n" in raw:
            errors.append(rel + "/SKILL.md: 使用了 CRLF 换行，请改为 LF")
        fm, err = parse_frontmatter(raw.decode("utf-8-sig", errors="replace"))
        if err:
            errors.append(rel + "/SKILL.md: " + err)
            continue
        name = fm.get("name", "").strip()
        if not name:
            errors.append(rel + "/SKILL.md: 缺少必填字段 name")
        elif not NAME_RE.match(name):
            errors.append(rel + "/SKILL.md: name 必须是小写英文连字符，当前为 " + repr(name))
        elif name != d.name:
            errors.append(rel + "/SKILL.md: name(" + name + ") 与目录名(" + d.name + ") 不一致")
        if not fm.get("description", "").strip():
            errors.append(rel + "/SKILL.md: 缺少必填字段 description")
        ver = fm.get("version", "").strip()
        if ver and not VERSION_RE.match(ver):
            warnings.append(rel + "/SKILL.md: version " + repr(ver) + " 不符合语义化版本")
        for ref in sorted(set(REF_RE.findall(raw.decode("utf-8-sig", errors="replace")))):
            if not (d / ref).is_file():
                warnings.append(rel + "/SKILL.md: 引用的 " + ref + " 不存在")
        for f in walk_files(d):
            r = f.relative_to(root).as_posix()
            if BAD_FILE_RE.search(f.name):
                errors.append(r + ": 禁止提交的文件（运行时数据或打包产物）")
            size = f.stat().st_size
            if size > MAX_BYTES:
                errors.append(r + ": 单文件 " + format(size / 1024 / 1024, ".1f") + "MB 超过 3MB 上限")
            if f.suffix.lower() not in TEXT_EXT:
                continue
            try:
                body = f.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            if HOME_PATH_RE.search(body):
                warnings.append(r + ": 含本机绝对路径，公开仓库建议改为占位符")
            if f.suffix.lower() != ".md":
                for rx, label in SECRET_RES:
                    if rx.search(body):
                        errors.append(r + ": 疑似包含" + label + "，禁止提交")
        print("[OK] " + rel)

    print("")
    print("共 " + str(len(skills)) + " 个技能，" + str(len(errors)) + " 个错误，" + str(len(warnings)) + " 个警告")
    for e in errors:
        print("  ERROR   " + e)
    for w in warnings:
        print("  WARN    " + w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
