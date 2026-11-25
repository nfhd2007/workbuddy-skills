#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 workbuddy-skills 仓库安装单个技能到本地 WorkBuddy 技能目录。

用法:
    python scripts/install_skill.py <技能名> [--ref main] [--dest <目录>] [--force]

可选环境变量 GITHUB_TOKEN / GH_TOKEN：提高 GitHub API 限额。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_REPO = "nfhd2007/workbuddy-skills"


def _request(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "workbuddy-skills-installer"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    return req


def fetch_json(url, token):
    with urllib.request.urlopen(_request(url, token), timeout=30) as r:
        return json.load(r)


def fetch_bytes(url):
    with urllib.request.urlopen(_request(url), timeout=30) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="技能目录名，例如 github")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--dest", default=None, help="目标目录，默认 ~/.workbuddy/skills/<name>")
    ap.add_argument("--force", action="store_true", help="目标非空时仍覆盖同名文件")
    args = ap.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    ref_q = urllib.parse.quote(args.ref, safe="")

    tree_url = "https://api.github.com/repos/{}/git/trees/{}?recursive=1".format(args.repo, ref_q)
    try:
        tree = fetch_json(tree_url, token)
    except urllib.error.HTTPError as e:
        print("读取仓库目录树失败：HTTP {}（检查 --repo / --ref）".format(e.code))
        return 1
    except urllib.error.URLError as e:
        print("网络错误：{}".format(e.reason))
        return 1
    if tree.get("truncated"):
        print("警告：目录树被截断，可能漏文件。")

    entries = [e["path"] for e in tree.get("tree", []) if e.get("type") == "blob"]
    skill_mds = [p for p in entries if p.startswith("skills/") and p.endswith("/SKILL.md")]
    matched = [p for p in skill_mds if p.rsplit("/", 2)[-2] == args.name]
    if not matched:
        names = sorted({p.rsplit("/", 2)[-2] for p in skill_mds})
        print("未找到技能 {!r}。仓库中可用：{}".format(args.name, ", ".join(names) or "（暂无技能）"))
        return 1
    if len(matched) > 1:
        print("技能名重复，请检查：\n  " + "\n  ".join(matched))
        return 1

    base = matched[0][:-len("/SKILL.md")]
    files = [p for p in entries if p.startswith(base + "/")]
    dest = Path(args.dest) if args.dest else Path.home() / ".workbuddy" / "skills" / args.name
    if dest.exists() and any(dest.iterdir()) and not args.force:
        print("目标已存在且非空：{}\n如需覆盖请加 --force（只覆盖同名文件，不删除其他文件）。".format(dest))
        return 1
    dest.mkdir(parents=True, exist_ok=True)

    for p in files:
        url = "https://raw.githubusercontent.com/{}/{}/{}".format(
            args.repo, ref_q, urllib.parse.quote(p, safe="/"))
        try:
            data = fetch_bytes(url)
        except urllib.error.HTTPError as e:
            print("下载失败 {}：HTTP {}".format(p, e.code))
            return 1
        rel = p[len(base) + 1:]
        out = dest.joinpath(*rel.split("/"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)

    print("已安装 {} -> {}（{} 个文件）".format(args.name, dest, len(files)))
    print("在 WorkBuddy 中重新加载技能后即可使用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
