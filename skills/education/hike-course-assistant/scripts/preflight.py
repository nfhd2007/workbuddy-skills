#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""课程助手运行环境自检 / 自动准备 / 路径解析（preflight）。

设计目标：让一台刚安装 WorkBuddy 的电脑也能直接跑起来。
每次触发技能时先运行本脚本：有条件的项直接通过，缺条件的项尽量自动补齐，
补齐不了的项给出「谁来做、怎么做」的明确清单。

自包含：仅用 Python 标准库，无第三方依赖，不联网安装（除非显式 --allow-install），
不写账号 / Cookie / Token / 页面内容，只在运行态目录写路径与环境信息。
`--ascii` 让 stdout 输出纯 ASCII JSON（PowerShell 5.1 / GBK 控制台安全）；
`prepare` 另把完整中文报告落盘为 last_preflight.json 供文件读取工具查看。

命令
----
check     报告本机哪些运行条件已满足、哪些可自动修复、哪些需要 Agent 或用户处理。
prepare   自动执行所有「本地可修复」动作，再复检一次并给出最终状态。
paths     只输出解析后的绝对路径（JSON），供 SKILL.md / browser-tools.md 引用。

用法（工作目录任意，路径用绝对路径）
------------------------------------
python "<SKILL_DIR>/scripts/preflight.py" check --json
python "<SKILL_DIR>/scripts/preflight.py" prepare --json --workspace "<CWD>"
python "<SKILL_DIR>/scripts/preflight.py" prepare --json --workspace "<CWD>" --course "课程名"
python "<SKILL_DIR>/scripts/preflight.py" prepare --json --workspace "<CWD>" --allow-install
python "<SKILL_DIR>/scripts/preflight.py" paths --json --workspace "<CWD>"
python "<SKILL_DIR>/scripts/preflight.py" check --json --ascii --workspace "<CWD>"

退出码：0 = 脚本执行成功（状态一律看 JSON 的 ready / next_action，不代表命令失败）；
        2 = 参数错误。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1
MIN_PYTHON = (3, 8)
SITES = (
    "https://hike-teaching-center.polymas.com",
    "https://wisdom-mooc.zhihuishu.com",
)
RUNTIME_SUBDIR = Path(".workbuddy") / "course-assistant"
ENV_PREFIX = "env-"  # 按技能名分文件，避免两个课程助手共用配置时互相覆盖
LEDGER_NAME = "hike-progress.json"

TOOL_LAYER = {
    "required_tool": "mcp__browser__browsers_list",
    "probe": "在会话中检索并加载该工具的 schema；能加载即代表 Browser Use 插件已连接、方案 A 可用",
    "if_unavailable": "按 references/environment.md『启用浏览器操控能力』启用插件；仍不可用则自动降级方案 B",
    "fallback": "computer-use（Windows 截图 + 坐标）/ desktop-control（agent-desktop 无障碍树）",
    "note": "MCP 工具是否存在，脚本无法检测，必须由 WorkBuddy 在会话内完成这一层探测。",
}

STATUS_MARK = {
    "ok": "[OK]",
    "warn": "[--]",
    "missing": "[缺]",
    "needs_user": "[人]",
    "probe_required": "[探]",
}


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #

def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _mk(cid, level, status, detail, *, auto_fix=None, agent_action=None,
        manual=None, commands=None):
    """构造一条检查结果。"""
    return {
        "id": cid,
        "level": level,           # required / fallback / runtime / optional
        "status": status,         # ok / warn / missing / needs_user / probe_required
        "detail": detail,
        "auto_fix": auto_fix,     # prepare 能自动完成的动作描述（None 表示不需要）
        "agent_action": agent_action,  # 需要 WorkBuddy 在本会话内执行的动作
        "manual": list(manual or []),
        "commands": list(commands or []),
    }


def _which(*names):
    for name in names:
        try:
            found = shutil.which(name)
        except Exception:
            found = None
        if found:
            return found
    return None


def _browser_candidates():
    """返回本机可用浏览器列表（不做联网、不启动进程）。"""
    found = []
    seen = set()

    def add(name, candidate):
        if not candidate:
            return
        try:
            p = Path(candidate)
            if not p.is_file() or str(p) in seen:
                return
            seen.add(str(p))
            found.append({"name": name, "path": str(p)})
        except Exception:
            return

    system = platform.system()
    if system == "Windows":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        add("Microsoft Edge", Path(pf86) / "Microsoft/Edge/Application/msedge.exe")
        add("Microsoft Edge", Path(pf) / "Microsoft/Edge/Application/msedge.exe")
        for base in (pf, pf86, local):
            if base:
                add("Google Chrome", Path(base) / "Google/Chrome/Application/chrome.exe")
                add("QQ 浏览器", Path(base) / "Tencent/QQBrowser/QQBrowser.exe")
        add("Chromium", _which("chromium", "chromium-browser"))
    elif system == "Darwin":
        apps = (
            ("Google Chrome", "Google Chrome.app/Contents/MacOS/Google Chrome"),
            ("Microsoft Edge", "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            ("QQ 浏览器", "QQBrowser.app/Contents/MacOS/QQBrowser"),
        )
        for name, rel in apps:
            add(name, Path("/Applications") / rel)
        add("Chromium", _which("chromium", "chromium-browser"))
    else:
        for name, exe in (("Google Chrome", "google-chrome"),
                          ("Chromium", "chromium"),
                          ("Chromium", "chromium-browser"),
                          ("Microsoft Edge", "microsoft-edge")):
            add(name, _which(exe))
    return found


def _probe_network(timeout):
    """轻量连通性探测；拿到任意 HTTP 响应即视为可达。"""
    last = "未执行"
    for url in SITES:
        try:
            req = urllib.request.Request(
                url, method="HEAD",
                headers={"User-Agent": "Mozilla/5.0 (course-assistant preflight)"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"ok": True, "detail": f"{url} → HTTP {resp.status}", "skipped": False}
        except urllib.error.HTTPError as exc:
            return {"ok": True, "detail": f"{url} → HTTP {exc.code}（站点有响应）", "skipped": False}
        except Exception as exc:  # noqa: BLE001 - 探测失败不阻断自检
            last = f"{url} → {type(exc).__name__}: {exc}"
    return {"ok": False, "detail": last, "skipped": False}


# --------------------------------------------------------------------------- #
# 上下文：动态解析所有绝对路径，绝不写死用户名 / 盘符
# --------------------------------------------------------------------------- #

def build_ctx(args):
    skill_dir = Path(__file__).resolve().parent.parent
    skills_root = skill_dir.parent
    workbuddy_home = skills_root.parent
    workspace = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
    runtime_dir = workspace / RUNTIME_SUBDIR
    skill_name = skill_dir.name
    env_file = runtime_dir / f"{ENV_PREFIX}{skill_name}.json"

    cu = skills_root / "computer-use"
    dc = skills_root / "desktop-control"
    bu = workbuddy_home / "plugins" / "cache" / "workbuddy-browser-use"

    powershell = None
    if platform.system() == "Windows":
        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        candidate = Path(sysroot) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        powershell = str(candidate) if candidate.is_file() else _which("powershell")

    paths = {
        "skill_dir": str(skill_dir),
        "skills_root": str(skills_root),
        "workbuddy_home": str(workbuddy_home),
        "workspace": str(workspace),
        "runtime_dir": str(runtime_dir),
        "env_file": str(env_file),
        "preflight_script": str(skill_dir / "scripts/preflight.py"),
        "ledger_script": str(skill_dir / "scripts/ledger.py"),
        "ledger": str(workspace / LEDGER_NAME),
        "python_exe": sys.executable,
        "python_cmd": _which("python", "python3", "py") or sys.executable,
        "node": _which("node"),
        "npm": _which("npm"),
        "npx": _which("npx"),
        "agent_desktop": _which("agent-desktop"),
        "powershell": powershell,
        "computer_use_skill": str(cu) if (cu / "SKILL.md").is_file() else None,
        "desktop_control_skill": str(dc) if (dc / "SKILL.md").is_file() else None,
        "browser_use_plugin_dir": str(bu) if bu.is_dir() else None,
        "browsers": _browser_candidates(),
    }

    if args.no_network:
        network = {"ok": True, "detail": "已按 --no-network 跳过", "skipped": True}
    else:
        try:
            network = _probe_network(float(args.timeout))
        except Exception as exc:  # noqa: BLE001
            network = {"ok": False, "detail": f"探测异常：{exc}", "skipped": False}

    return {
        "skill_name": skill_name,
        "skill_dir": skill_dir,
        "skills_root": skills_root,
        "workbuddy_home": workbuddy_home,
        "workspace": workspace,
        "runtime_dir": runtime_dir,
        "env_file": env_file,
        "paths": paths,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "python_exe": sys.executable,
        },
        "network": network,
    }


# --------------------------------------------------------------------------- #
# 检查项
# --------------------------------------------------------------------------- #

def build_report(ctx, args):
    p = ctx["paths"]
    checks = []

    # --- 本机层：必需 ---
    ver = (sys.version_info.major, sys.version_info.minor)
    py_ok = ver >= MIN_PYTHON
    checks.append(_mk(
        "python", "required", "ok" if py_ok else "missing",
        f"Python {platform.python_version()}｜{sys.executable}",
        manual=[] if py_ok else [
            "安装 Python 3.8+：https://www.python.org/downloads/",
            "或使用 WorkBuddy 自带 Python（见 references/environment.md『获取 Python』）",
        ]))

    wb = ctx["workbuddy_home"]
    wb_ok = wb.is_dir()
    checks.append(_mk(
        "workbuddy_home", "required", "ok" if wb_ok else "missing",
        f"WorkBuddy 用户目录：{wb}｜技能根目录：{ctx['skills_root']}"
        + ("" if wb_ok else "（未找到）"),
        manual=[] if wb_ok else ["安装并至少启动一次 WorkBuddy，使其创建 ~/.workbuddy 目录"]))

    rd = ctx["runtime_dir"]
    rd_ok = rd.is_dir()
    checks.append(_mk(
        "runtime_dir", "required", "ok" if rd_ok else "missing",
        f"运行态目录：{rd}",
        auto_fix=None if rd_ok else "prepare 自动创建该目录（仅写路径与配置）"))

    ef = ctx["env_file"]
    ef_ok = ef.is_file()
    checks.append(_mk(
        "env_file", "required", "ok" if ef_ok else "missing",
        f"路径配置：{ef}" + ("" if ef_ok else "（尚未生成，桌面技能绝对路径无法解析）"),
        auto_fix=None if ef_ok else
        "prepare 自动生成 env.json：解析技能目录、桌面技能、CLI、浏览器、台账的绝对路径，消除硬编码"))

    # --- 工具层：本地痕迹 + 交给 Agent 探测 ---
    bp = p["browser_use_plugin_dir"]
    bp_ok = bool(bp) and Path(bp).is_dir()
    checks.append(_mk(
        "browser_use_plugin", "required", "ok" if bp_ok else "probe_required",
        (f"Browser Use 插件缓存：{bp}" if bp_ok else
         "本地未见 workbuddy-browser-use 插件缓存；插件也可能由托管方式提供，一律以工具层探测为准"),
        agent_action=None if bp_ok else {
            "kind": "plugin_enable",
            "target": "workbuddy-browser-use",
            "how": "调用 list_installed_plugins 检查插件状态；未启用则引导用户在「设置 > 智能体 > 浏览器操控」启用（内置浏览器无需扩展）",
        },
        manual=[] if bp_ok else [
            "WorkBuddy「设置 > 智能体 > 浏览器操控」：启用浏览器操控，确认 Browser Use 插件已安装且开启",
            "若要复用外部 Chrome / Edge / QQ 浏览器的登录态，点「前往安装」装好对应扩展",
            "仅用 WorkBuddy 内置浏览器（IAB）时不需要任何扩展",
        ]))

    # --- 本机层：可选 / 提示 ---
    browsers = p["browsers"]
    names = "、".join(sorted({b["name"] for b in browsers})) if browsers else ""
    checks.append(_mk(
        "browser_binary", "optional", "ok" if browsers else "warn",
        (f"检测到系统浏览器：{names}" if browsers else
         "未检测到系统浏览器；使用 WorkBuddy 内置浏览器时无需安装，可忽略"),
        manual=[] if browsers else [
            "如需复用外部浏览器登录态，安装 Edge / Chrome / QQ 浏览器之一即可",
            "或直接使用 WorkBuddy 内置浏览器（方案 A 默认）",
        ]))

    net = ctx["network"]
    net_status = "warn" if (net["skipped"] or not net["ok"]) else "ok"
    checks.append(_mk(
        "network", "optional", net_status,
        f"站点连通性：{net['detail']}",
        manual=[] if net["ok"] else [
            "检查网络 / 代理 / 校园网认证；连通性不影响本地自检结果，主流程会在打开页面时再判定",
        ]))

    # --- 方案 B：桌面备用分支（缺了不阻塞方案 A）---
    is_win = platform.system() == "Windows"

    cu = p["computer_use_skill"]
    if not is_win:
        cu_status, cu_detail = "warn", "computer-use 仅支持 Windows；本平台忽略该备用分支"
    elif cu and Path(cu, "scripts/computer-use.ps1").is_file():
        cu_status, cu_detail = "ok", f"computer-use 技能：{cu}"
    elif cu:
        cu_status, cu_detail = "missing", f"技能目录存在但缺少 scripts/computer-use.ps1：{cu}"
    else:
        cu_status, cu_detail = "missing", "未找到 computer-use 技能"
    checks.append(_mk(
        "computer_use_skill", "fallback", cu_status, cu_detail,
        agent_action=None if cu_status in ("ok", "warn") else {
            "kind": "skill_install", "target": "computer-use",
            "how": "用 ToolSearch 加载 search_and_install_skills，搜索并安装 computer-use，安装后重新 check",
        },
        manual=[] if cu_status in ("ok", "warn") else [
            "备用分支：仅当方案 A 不可用、且用户要求操控现有浏览器窗口时才需要",
        ]))

    dc = p["desktop_control_skill"]
    dc_ok = bool(dc) and Path(dc, "SKILL.md").is_file()
    checks.append(_mk(
        "desktop_control_skill", "fallback", "ok" if dc_ok else "missing",
        (f"desktop-control 技能：{dc}" if dc_ok else "未找到 desktop-control 技能"),
        agent_action=None if dc_ok else {
            "kind": "skill_install", "target": "desktop-control",
            "how": "用 ToolSearch 加载 search_and_install_skills，搜索并安装 desktop-control，安装后重新 check",
        }))

    node, npm = p["node"], p["npm"]
    node_ok = bool(node and npm)
    checks.append(_mk(
        "node_runtime", "fallback", "ok" if node_ok else "missing",
        f"node：{node or '未找到'}｜npm：{npm or '未找到'}",
        manual=[] if node_ok else [
            "安装 Node.js 18+：https://nodejs.org/",
            "WorkBuddy 通常自带 Node（见 references/environment.md『获取 Node』）",
        ]))

    ad = p["agent_desktop"]
    checks.append(_mk(
        "agent_desktop_cli", "fallback", "ok" if ad else "missing",
        f"agent-desktop：{ad or '未找到'}",
        commands=[] if ad else ["npm install -g agent-desktop", "agent-desktop status"],
        manual=[] if ad else [
            "仅 desktop-control 分支需要；安装后执行 agent-desktop status 验证",
            "macOS 需按 agent-desktop permissions --guide 授予辅助功能权限",
            "用户同意后可用 prepare --allow-install 由脚本自动安装",
        ]))

    if is_win:
        ps = p["powershell"]
        checks.append(_mk(
            "powershell", "fallback", "ok" if ps else "missing",
            f"Windows PowerShell 5.1：{ps or '未找到'}",
            manual=[] if ps else ["computer-use 依赖 Windows PowerShell 5.1（非 pwsh 7）"]))
    else:
        checks.append(_mk(
            "powershell", "fallback", "warn",
            "非 Windows 平台，跳过 PowerShell 检查"))

    ledger = Path(p["ledger"])
    checks.append(_mk(
        "ledger", "optional", "ok" if ledger.is_file() else "warn",
        f"台账：{ledger}" + ("" if ledger.is_file() else
                            "（尚未建立；prepare --course 可自动初始化，主流程第 2 步也会建立）")))

    # --- 运行时：由主流程处理，不阻塞预检 ---
    checks.append(_mk(
        "login_session", "runtime", "needs_user",
        "登录态无法由脚本检测，也禁止代输凭据；由主流程第 1 步引导用户本人在受控标签登录",
        manual=["用户本人在受控标签登录 AI智慧课程中心 / 智慧树，完成后回复「继续」"]))
    checks.append(_mk(
        "target_course", "runtime", "needs_user",
        "需由用户指定课程名；脚本不猜测课程",
        manual=["用户明确指定要刷哪门课；若表示已全部看完，直接输出台账汇总并停止"]))

    # --- 汇总决策 ---
    auto_fix_ids = [c["id"] for c in checks if c["auto_fix"]]
    blocking = [
        c for c in checks
        if c["level"] == "required"
        and c["status"] in ("missing", "needs_user")
        and not c["auto_fix"]
    ]
    agent_actions = []
    for c in checks:
        if c["agent_action"]:
            action = dict(c["agent_action"])
            action["id"] = c["id"]
            action["status"] = c["status"]
            agent_actions.append(action)
    needs_user = []
    for c in checks:
        if c["status"] == "needs_user" or (
            c["status"] == "missing" and (c["manual"] or c["commands"])
        ):
            needs_user.append({
                "id": c["id"],
                "level": c["level"],
                "blocking": c in blocking,
                "detail": c["detail"],
                "steps": c["manual"],
                "commands": c["commands"],
            })

    ready = not blocking
    if auto_fix_ids:
        next_action = "prepare"
    elif blocking:
        next_action = "wait_user"
    else:
        next_action = "probe_tools_then_run"

    if not ready and blocking:
        summary = f"有 {len(blocking)} 项必需条件缺失，需先补齐：{'、'.join(c['id'] for c in blocking)}"
    elif auto_fix_ids:
        summary = f"本机可自动准备 {len(auto_fix_ids)} 项，运行 prepare 后复检"
    else:
        summary = "本机条件已就绪，下一步探测浏览器工具层后即可开始"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "skill": ctx["skill_name"],
        "platform": ctx["platform"],
        "workspace": str(ctx["workspace"]),
        "runtime_dir": str(ctx["runtime_dir"]),
        "env_file": str(ctx["env_file"]),
        "paths": p,
        "checks": checks,
        "auto_fix": auto_fix_ids,
        "agent_actions": agent_actions,
        "needs_user": needs_user,
        "blocking": [c["id"] for c in blocking],
        "tool_layer": TOOL_LAYER,
        "ready": ready,
        "next_action": next_action,
        "summary": summary,
    }


# --------------------------------------------------------------------------- #
# 自动准备
# --------------------------------------------------------------------------- #

def write_env(ctx):
    env = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "skill": ctx["skill_name"],
        "platform": ctx["platform"],
        "workspace": str(ctx["workspace"]),
        "runtime_dir": str(ctx["runtime_dir"]),
        "env_file": str(ctx["env_file"]),
        "paths": ctx["paths"],
        "tool_layer": TOOL_LAYER,
        "privacy": "本文件只保存路径与环境信息，不含账号、Cookie、Token 或页面内容。",
        "usage": "桌面技能路径一律从本文件 paths 读取，禁止在文档里写死用户名或盘符。",
    }
    ctx["runtime_dir"].mkdir(parents=True, exist_ok=True)
    tmp = ctx["env_file"].with_name(ctx["env_file"].name + ".tmp")
    tmp.write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ctx["env_file"])


def do_prepare(ctx, args):
    actions = []
    p = ctx["paths"]

    # 1. 运行态目录
    try:
        ctx["runtime_dir"].mkdir(parents=True, exist_ok=True)
        actions.append({"id": "runtime_dir", "ok": True,
                        "detail": f"已确保目录存在：{ctx['runtime_dir']}"})
    except Exception as exc:  # noqa: BLE001
        actions.append({"id": "runtime_dir", "ok": False, "detail": str(exc)})

    # 2. env.json（绝对路径解析，解决硬编码用户名问题）
    try:
        write_env(ctx)
        actions.append({"id": "env_file", "ok": True,
                        "detail": f"已生成路径配置：{ctx['env_file']}"})
    except Exception as exc:  # noqa: BLE001
        actions.append({"id": "env_file", "ok": False, "detail": str(exc)})

    # 3. 可选：初始化台账
    if args.course:
        ledger = Path(p["ledger"])
        if not ledger.is_file():
            try:
                result = subprocess.run(
                    [sys.executable, p["ledger_script"], "init",
                     "--course", args.course, "--total", "0", "--file", str(ledger)],
                    capture_output=True, text=True, timeout=30,
                )
                actions.append({"id": "ledger", "ok": result.returncode == 0,
                                "detail": (result.stdout or result.stderr or "").strip()})
            except Exception as exc:  # noqa: BLE001
                actions.append({"id": "ledger", "ok": False, "detail": str(exc)})
        else:
            actions.append({"id": "ledger", "ok": True,
                            "detail": f"台账已存在，保持不变：{ledger}"})

    # 4. 可选：安装 agent-desktop（必须用户显式同意才开启）
    if args.allow_install and not p["agent_desktop"] and p["npm"]:
        try:
            cmd = f'"{p["npm"]}" install -g agent-desktop'
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=300,
            )
            tail = (result.stdout or result.stderr or "").strip()[-800:]
            actions.append({"id": "install_agent_desktop",
                            "ok": result.returncode == 0, "detail": tail})
            p["agent_desktop"] = _which("agent-desktop")
        except Exception as exc:  # noqa: BLE001
            actions.append({"id": "install_agent_desktop", "ok": False, "detail": str(exc)})
    elif args.allow_install and p["agent_desktop"]:
        actions.append({"id": "install_agent_desktop", "ok": True,
                        "detail": "agent-desktop 已存在，无需安装"})

    return actions


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #

def print_human(rep):
    lines = [
        f"课程助手环境自检｜{rep['generated_at']}",
        f"平台：{rep['platform']['system']} {rep['platform']['release']} / Python {rep['platform']['python']}",
        f"结果：{rep['summary']}（ready={rep['ready']}, next_action={rep['next_action']}）",
        "",
        "- 检查项 -",
    ]
    for c in rep["checks"]:
        mark = STATUS_MARK.get(c["status"], "[?]")
        lines.append(f"  {mark} {c['id']:<22} {c['detail']}")
        if c["auto_fix"]:
            lines.append(f"        自动修复：{c['auto_fix']}")
    if rep["agent_actions"]:
        lines += ["", "- 需 WorkBuddy 在本会话内执行 -"]
        for a in rep["agent_actions"]:
            lines.append(f"  · [{a['kind']}] {a['target']}：{a['how']}")
    if rep["needs_user"]:
        lines += ["", "- 需用户配合（无法自动完成） -"]
        for n in rep["needs_user"]:
            lines.append(f"  · {n['id']}（阻塞={n['blocking']}）：{n['detail']}")
            for s in n["steps"]:
                lines.append(f"      - {s}")
            for c in n["commands"]:
                lines.append(f"      $ {c}")
    lines += ["", "- 工具层探测 -", f"  {TOOL_LAYER['probe']}",
              f"  {TOOL_LAYER['note']}"]
    print("\n".join(lines))


def emit(rep, as_json, ascii_only=False):
    if as_json:
        print(json.dumps(rep, ensure_ascii=ascii_only, indent=2))
    else:
        print_human(rep)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", help="工作目录（默认当前目录），运行态目录与台账放在这里")
    common.add_argument("--json", action="store_true", help="输出机器可读 JSON（stdout 只含 JSON）")
    common.add_argument("--no-network", action="store_true", help="跳过站点连通性探测")
    common.add_argument("--timeout", type=float, default=4.0, help="单次连通性探测超时秒数（默认 4）")
    common.add_argument("--ascii", action="store_true", help="JSON 输出纯 ASCII（转义中文），便于 PowerShell 5.1 / GBK 控制台消费")

    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", parents=[common], help="检查运行条件")
    p_prepare = sub.add_parser("prepare", parents=[common], help="自动准备运行条件并复检")
    p_prepare.add_argument("--course", help="顺带为指定课程初始化进度台账（若不存在）")
    p_prepare.add_argument("--allow-install", action="store_true",
                           help="用户已明确同意时，允许执行 npm install -g agent-desktop")
    sub.add_parser("paths", parents=[common], help="只输出解析后的绝对路径（JSON）")
    return parser


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    args = build_parser().parse_args()
    ctx = build_ctx(args)

    if args.command == "paths":
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "generated_at": _now(),
            "skill": ctx["skill_name"],
            "paths": ctx["paths"],
            "env_file": str(ctx["env_file"]),
        }, ensure_ascii=args.ascii, indent=2))
        return 0

    if args.command == "check":
        emit(build_report(ctx, args), args.json, args.ascii)
        return 0

    # prepare
    actions = do_prepare(ctx, args)
    rep = build_report(ctx, args)
    rep["prepared"] = True
    rep["prepare_actions"] = actions
    try:
        ctx["runtime_dir"].mkdir(parents=True, exist_ok=True)
        (ctx["runtime_dir"] / "last_preflight.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - 报告落盘失败不影响主流程
        rep["report_file_error"] = True
    emit(rep, args.json, args.ascii)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
