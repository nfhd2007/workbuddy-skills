#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描 skills/ 生成 INDEX.md 与 skills.json（纯标准库）。

用法: python scripts/build_index.py [--root <仓库根目录>] [--check]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_skills import find_skills, parse_frontmatter  # noqa: E402

REPO = "nfhd2007/workbuddy-skills"


def one_line(s, limit=88):
    s = re.sub(r"\s+", " ", (s or "").strip()).replace("|", "\\|")
    return s if len(s) <= limit else s[:limit - 1] + "…"


def collect(root):
    items = []
    skills_dir = root / "skills"
    for d in find_skills(root):
        text = (d / "SKILL.md").read_text(encoding="utf-8-sig", errors="replace")
        fm, _ = parse_frontmatter(text)
        fm = fm or {}
        rel = d.relative_to(root).as_posix()
        parts = d.relative_to(skills_dir).parts
        category = parts[0] if len(parts) > 1 else "uncategorized"
        items.append({
            "name": fm.get("name") or d.name,
            "display_name": fm.get("display_name", ""),
            "description": one_line(fm.get("description") or fm.get("description_zh") or ""),
            "version": fm.get("version", ""),
            "category": category,
            "author": fm.get("author", ""),
            "path": rel,
        })
    return sorted(items, key=lambda x: x["name"])


def render_md(items):
    lines = [
        "# 技能索引",
        "",
        "> 本文件由 `python scripts/build_index.py` 自动生成，请勿手工编辑。",
        "> 数据源：`skills/*/SKILL.md` 的 frontmatter。",
        "",
        "共 **" + str(len(items)) + "** 个技能。",
        "",
        "| 技能 | 说明 | 版本 | 分类 | 作者 | 目录 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if items:
        for it in items:
            label = "[" + it["name"] + "](" + it["path"] + "/SKILL.md)"
            lines.append("| " + label + " | " + (it["description"] or "—") + " | "
                         + (it["version"] or "—") + " | " + it["category"] + " | "
                         + (it["author"] or "—") + " | `" + it["path"] + "` |")
    else:
        lines.append("| _（暂无技能，欢迎提交第一个）_ | — | — | — | — | — |")
    return "\n".join(lines) + "\n"


def render_json(items):
    return json.dumps({
        "repo": REPO,
        "generated_by": "scripts/build_index.py",
        "count": len(items),
        "skills": items,
    }, ensure_ascii=False, indent=2) + "\n"


def write_lf(path, content):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--check", action="store_true", help="只校验索引是否最新，不写文件")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    items = collect(root)
    outputs = {"INDEX.md": render_md(items), "skills.json": render_json(items)}
    changed = []
    for name, content in outputs.items():
        p = root / name
        if not p.is_file() or p.read_text(encoding="utf-8") != content:
            changed.append(name)
            if not args.check:
                write_lf(p, content)
    if args.check:
        if changed:
            print("索引不是最新，请运行 python scripts/build_index.py 后提交：" + ", ".join(changed))
            return 1
        print("索引已是最新。")
        return 0
    print("已生成 INDEX.md 与 skills.json，共 " + str(len(items)) + " 个技能。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
