#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quark_share_download.py · 从夸克分享链接直链下载技能压缩包

通过网页接口（无需图形界面、无需浏览器自动化）把他人分享的夸克网盘链接里的
.zip 下载到本机，得到的路径可直接交给 install_skill_from_zip.py 审查安装。

链路：
  1. POST /share/sharepage/token     -> stoken              [已由 quark-drive 实测]
  2. GET  /share/sharepage/detail    -> 文件清单             [已由 quark-drive 实测]
  3. POST drive-h /share/sharepage/save -> task_id           [转存；quark-drive 实测]
  4. GET  /task?task_id=             -> 落盘 fid             [quark-drive 实测]
  5. POST /file/download             -> download_url         [路由已探测存在]
  6. GET  download_url               -> 本地 .zip

重要（2026-11-22 修正）：此前这里写的是 `POST /share/sharepage/download`，标注为
"未验证"。实测表明它不是"未验证"而是**不存在**：
  - `POST /share/sharepage/download` 返回 Spring 的 `{"status":404,"error":"Not Found",
    "message":"No message available","path":"/1/clouddrive/share/sharepage/download"}`，
    与故意写错的路由（`.../definitely-not-a-route`）响应**逐字段一致**，GET 也一样；
  - `POST /file/download` 返回业务包 `{"status":401,"code":31001,"message":"require
    login [share missing]"}`，GET 返回 `405 Method Not Allowed`——说明该路由真实存在、
    且只接受 POST。
所以直链只能走"先转存到自己网盘，再从自己的网盘取直链"这条链。转存会**写用户账号**
（网盘根目录出现一份副本、消耗每日转存次数），因此默认关闭，必须显式
`--allow-save-to-drive`，并在下载后把这份副本移入回收站（`--keep-saved` 可保留）。

步 3-6 的路由与形状已逐项探测，但**整链尚未用真实分享链接 + 有效 Cookie 端到端验证**；
JSON 输出里 `verified_steps` / `unverified_steps` / `route_probe` 会如实标注。

Cookie 取值优先级：--cookie-file > $QUARK_COOKIE > ./cookie.txt > 各 skills 根下的
quark-drive/scripts/cookie.txt（skills 根由 _skills_paths 解析，与 preflight.py 同一份
实现：本技能所在根 → QSI_SKILLS_DIR → <config>/skills → ~/.workbuddy/skills）。
Cookie 值绝不打印、不写日志、不进 JSON 输出。

用法：
    python quark_share_download.py "<share-url>" --passcode ab12 --out-dir ./dl --json
    python quark_share_download.py "<share-url>" --list-only --json
    python quark_share_download.py "<share-url>" --keyword skill --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

# Cookie 所在的 skills 根解析必须与 preflight.py 完全同源，否则会出现
# "预检说已登录、这里却 401"（或反过来，于是 route 被判成 api）。规则只写在
# _skills_paths 里，本文件不再保留第二份。
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _skills_paths import cookie_candidates, local_skills_root, skills_roots
except ImportError as _exc:  # pragma: no cover - 技能包不完整
    sys.stderr.write(
        "缺少 scripts/_skills_paths.py（技能包不完整）: %s\n"
        "请重新安装/重新分发本技能包，确保 scripts/ 目录完整\n" % _exc)
    raise SystemExit(2)

API_BASE = "https://drive-pc.quark.cn/1/clouddrive"
# 转存接口在另一个域名（drive-h），见 quark-drive 的抓包记录
SAVE_BASE = "https://drive-h.quark.cn/1/clouddrive"
COMMON_QUERY = "pr=ucpro&fr=pc&uc_param_str="
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MAX_DOWNLOAD = 200 * 1024 * 1024
MAX_ITEMS = 500
MAX_DEPTH = 3
PAGE_SIZE = 50
SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _setup_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def log(msg):
    print(msg, file=sys.stderr, flush=True)


class DownloadError(Exception):
    pass


# ---------------------------------------------------------------------------
# HTTP primitives (kept isolated so the chain can be mock-tested)
# ---------------------------------------------------------------------------
def _headers(cookie, extra=None):
    h = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json",
        "origin": "https://pan.quark.cn",
        "referer": "https://pan.quark.cn/",
        "user-agent": UA,
        "cookie": cookie,
    }
    if extra:
        h.update(extra)
    return h


def _json_request(url, body=None, cookie="", timeout=30, extra_headers=None):
    """GET when body is None, POST otherwise. Returns parsed JSON dict."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers=_headers(cookie, extra_headers),
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            return {"_http_error": e.code, "message": "HTTP %s" % e.code}
    except Exception as e:
        return {"_transport_error": "%s: %s" % (type(e).__name__, e)}
    try:
        return json.loads(raw)
    except Exception:
        return {"message": "非 JSON 响应: %s" % raw[:200]}


def _stream_download(url, dest, cookie, timeout=120, max_size=MAX_DOWNLOAD):
    """Stream a URL to dest with a size cap. Returns bytes written."""
    # Download CDN is stricter about headers than the JSON API: keep it simple,
    # and always send Referer (see quark-drive README pitfall #8).
    req = urllib.request.Request(url, headers={
        "accept": "*/*",
        "referer": "https://pan.quark.cn/",
        "user-agent": UA,
        "cookie": cookie,
    })
    total = 0
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as out:
        declared = r.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_size:
            raise DownloadError("文件超过大小上限 %d MB，已放弃" % (max_size // 1024 // 1024))
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_size:
                raise DownloadError("下载超过大小上限 %d MB，已放弃" % (max_size // 1024 // 1024))
            out.write(chunk)
    return total


# ---------------------------------------------------------------------------
# Input parsing / credentials
# ---------------------------------------------------------------------------
def parse_share(text):
    """Return (pwd_id, passcode_from_url). Accept full URLs, fragments, or raw ids."""
    s = text.strip()
    m = re.search(r"pan\.quark\.cn/s/([A-Za-z0-9]+)", s)
    if m:
        pwd_id = m.group(1)
    elif re.fullmatch(r"[A-Za-z0-9]{8,40}", s):
        pwd_id = s
    else:
        raise DownloadError("无法从输入中识别出夸克分享 pwd_id: %s" % s[:80])
    pm = re.search(r"[?&]pwd=([^&#\s]+)", s)
    passcode = urllib.parse.unquote(pm.group(1)) if pm else ""
    return pwd_id, passcode


def _skills_roots():
    """Candidate skills roots -- delegates to the shared resolver.

    Kept as a thin wrapper so the lookups below read the same way as before;
    the order (this skill's own root → QSI_SKILLS_DIR → <config>/skills →
    ~/.workbuddy/skills) lives in _skills_paths only.
    """
    here = Path(__file__).resolve()
    return skills_roots(extra=[local_skills_root(here.parent.parent)])


def load_cookie(args):
    """Return (cookie, source_label). Never return the value to output."""
    if args.cookie_file:
        p = Path(args.cookie_file).expanduser()
        if not p.is_file():
            raise DownloadError("指定的 Cookie 文件不存在: %s" % p)
        v = p.read_text(encoding="utf-8").strip()
        if not v:
            raise DownloadError("Cookie 文件为空: %s" % p)
        return v, "--cookie-file"

    env = os.environ.get("QUARK_COOKIE", "").strip()
    if env:
        return env, "QUARK_COOKIE"

    roots = _skills_roots()
    for p in cookie_candidates(Path(__file__).resolve().parent, roots):
        if p.is_file():
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v, "cookie.txt (%s)" % p.parent.name
    raise DownloadError(
        "未找到夸克登录 Cookie（已查找: %s）。任选其一：设置环境变量 QUARK_COOKIE；"
        "用 --cookie-file 指向 cookie.txt；或运行 quark-drive 技能的 get_cookie.py 抓取。"
        "Cookie 属于账号凭据，不要粘贴到对话里。"
        % ", ".join(str(p) for p in cookie_candidates(Path(__file__).resolve().parent, roots))
    )


# ---------------------------------------------------------------------------
# API chain
# ---------------------------------------------------------------------------
def get_stoken(pwd_id, passcode, cookie, timeout):
    url = "%s/share/sharepage/token?%s" % (API_BASE, COMMON_QUERY)
    r = _json_request(url, {"pwd_id": pwd_id, "passcode": passcode}, cookie, timeout)
    if r.get("code") != 0:
        raise DownloadError(
            "取 stoken 失败 code=%s msg=%s。检查：提取码是否正确、链接是否失效、Cookie 是否过期。"
            % (r.get("code"), r.get("message"))
        )
    return (r.get("data") or {}).get("stoken")


def list_dir(pwd_id, stoken, pdir_fid, cookie, timeout):
    """One directory level, all pages."""
    items, page = [], 1
    while page <= 20:
        q = ("%s&pwd_id=%s&pdir_fid=%s&stoken=%s&_page=%d&_page_size=%d"
             "&_sort=file_type:asc,updated_at:desc"
             % (COMMON_QUERY, pwd_id, pdir_fid, urllib.parse.quote(stoken or ""),
                page, PAGE_SIZE))
        r = _json_request("%s/share/sharepage/detail?%s" % (API_BASE, q), None, cookie, timeout)
        if r.get("code") != 0:
            raise DownloadError("列分享内容失败 code=%s msg=%s" % (r.get("code"), r.get("message")))
        data = r.get("data") or {}
        batch = data.get("list") or []
        items.extend(batch)
        meta = data.get("_metadata") or {}
        total = meta.get("total")
        if len(batch) < PAGE_SIZE or (isinstance(total, int) and len(items) >= total):
            break
        page += 1
    return items


def collect_files(pwd_id, stoken, cookie, timeout, max_depth=MAX_DEPTH):
    """Walk the share tree (bounded depth/items) and flatten to records."""
    out = []

    def walk(fid, depth, prefix):
        if depth > max_depth or len(out) >= MAX_ITEMS:
            return
        for it in list_dir(pwd_id, stoken, fid, cookie, timeout):
            if len(out) >= MAX_ITEMS:
                break
            name = it.get("file_name") or ""
            rec = {
                "fid": it.get("fid") or "",
                "name": name,
                "path": prefix + name,
                "dir": bool(it.get("dir")),
                "size": it.get("size"),
                "share_fid_token": it.get("share_fid_token") or "",
            }
            out.append(rec)
            if rec["dir"] and rec["fid"]:
                walk(rec["fid"], depth + 1, prefix + name + "/")
            time.sleep(0.05)  # be polite to the API

    walk("0", 1, "")
    return out


def pick_zip(files, keyword="", fid=""):
    if fid:
        hits = [f for f in files if f["fid"] == fid and not f["dir"]]
        if not hits:
            raise DownloadError("指定的 --fid 在分享内容中未找到: %s" % fid)
    else:
        hits = [f for f in files if not f["dir"] and f["name"].lower().endswith(".zip")]
        if keyword:
            hits = [f for f in hits if keyword.lower() in f["name"].lower()]
    if not hits:
        raise DownloadError("分享内容里没有找到 .zip 文件。用 --list-only 查看全部条目。")
    if len(hits) > 1:
        lines = ["  - %s (fid=%s, %s bytes)" % (f["path"], f["fid"], f["size"]) for f in hits[:20]]
        raise DownloadError("分享里有多个 .zip，请用 --keyword 或 --fid 明确指定:\n" + "\n".join(lines))
    return hits[0]


DEAD_ENDPOINT_MSG = (
    "分享文件的直链接口不存在：POST /share/sharepage/download 返回路由级 404"
    "（响应与故意写错的路由逐字段一致），重试多少次都不会成功。两条可行路径：\n"
    "  1) 加 --allow-save-to-drive：把 zip 转存到你自己的网盘 → 从自己的网盘取直链 → "
    "下载后把该副本移入回收站。需要登录 Cookie，会消耗每日转存次数，"
    "且整链尚未用真实链接端到端验证。\n"
    "  2) 改走 GUI / 手动下载（SKILL.md 阶段 1B / 1C），不做任何接口调用。"
)


def _poll_task(task_id, cookie, timeout, tries=20, interval=1.5):
    """轮询异步任务。status: 2=成功，3=终态失败，其他=进行中。"""
    for i in range(tries):
        q = urllib.parse.urlencode({
            "task_id": task_id, "retry_index": i,
            "pr": "ucpro", "fr": "pc", "uc_param_str": "",
        })
        r = _json_request("%s/task?%s" % (API_BASE, q), None, cookie, timeout)
        data = r.get("data") or {}
        st = data.get("status")
        if st == 2:
            return data
        if st == 3 or (isinstance(st, int) and st < 0):
            raise DownloadError("异步任务失败 code=%s msg=%s"
                                % (r.get("code"), r.get("message")))
        if r.get("code") not in (0, None):
            raise DownloadError("轮询任务失败 code=%s msg=%s"
                                % (r.get("code"), r.get("message")))
        time.sleep(interval)
    raise DownloadError("异步任务超时（轮询 %d 次仍未完成）" % tries)


def _saved_fid(task_data, item, cookie, timeout):
    """转存成功后定位那份副本的 fid。优先用任务结果，兜底查网盘根目录。"""
    sa = task_data.get("save_as") or {}
    for key in ("save_as_top_fids", "top_fids"):
        v = sa.get(key)
        if isinstance(v, list) and v:
            return v[0], "task.save_as.%s" % key
    for key in ("fids", "save_as_top_fids"):
        v = task_data.get(key)
        if isinstance(v, list) and v:
            return v[0], "task.%s" % key
    q = urllib.parse.urlencode({
        "_page": 1, "_size": 50, "_fetch_total": 1, "pdir_fid": "0",
        "_sort": "file_type:asc,updated_at:desc",
        "pr": "ucpro", "fr": "pc", "uc_param_str": "",
    })
    r = _json_request("%s/file/sort?%s" % (API_BASE, q), None, cookie, timeout)
    for it in ((r.get("data") or {}).get("list") or []):
        if it.get("file_name") == item["name"]:
            return it.get("fid"), "file/sort"
    raise DownloadError(
        "转存成功但定位不到副本 fid（任务结果无 save_as 字段，网盘根目录也没有同名文件）。"
        "请到网盘根目录确认，或改用 GUI 下载路径。")


def save_to_drive(pwd_id, stoken, item, cookie, timeout):
    """把分享里的目标文件转存到我的网盘根目录，返回 (fid, 来源标签)。

    这是对用户账号的写操作，调用方必须先拿到 --allow-save-to-drive。
    """
    body = {
        "pwd_id": pwd_id,
        "stoken": stoken,
        "pdir_fid": item["fid"],
        "to_pdir_fid": "0",
        "pdir_save_all": False,
        "scene": "link",
    }
    r = _json_request("%s/share/sharepage/save?%s" % (SAVE_BASE, COMMON_QUERY),
                      body, cookie, timeout)
    if r.get("code") != 0:
        raise DownloadError("转存失败 code=%s msg=%s"
                            % (r.get("code"), r.get("message")))
    task_id = (r.get("data") or {}).get("task_id")
    if not task_id:
        raise DownloadError("转存未返回 task_id")
    data = _poll_task(task_id, cookie, timeout)
    return _saved_fid(data, item, cookie, timeout)


def get_download_url(fids, cookie, timeout):
    """从自己的网盘取直链。POST /file/download 路由已探测存在（GET→405）。"""
    body = {"fids": fids if isinstance(fids, list) else [fids]}
    r = _json_request("%s/file/download?%s" % (API_BASE, COMMON_QUERY),
                      body, cookie, timeout)
    if r.get("code") != 0:
        raise DownloadError(
            "取下载直链失败 code=%s msg=%s（/file/download 路由存在，"
            "通常意味着 Cookie 失效或该文件不允许下载）"
            % (r.get("code"), r.get("message")))
    data = r.get("data")
    entry = {}
    if isinstance(data, list) and data:
        entry = data[0] if isinstance(data[0], dict) else {}
    elif isinstance(data, dict):
        entry = data
    u = entry.get("download_url")
    if not u:
        raise DownloadError("接口未返回 download_url。响应字段: %s" % list(entry.keys()))
    return u


def trash_saved(fid, cookie, timeout):
    """把刚转存的那份副本移入回收站。只动本次自己创建的 fid。"""
    body = {"action": 2, "filelist": [fid], "to_trash": True}
    r = _json_request("%s/file/delete?%s" % (API_BASE, COMMON_QUERY),
                      body, cookie, timeout)
    if r.get("code") != 0:
        return False, "code=%s msg=%s" % (r.get("code"), r.get("message"))
    tid = (r.get("data") or {}).get("task_id")
    if tid:
        try:
            _poll_task(tid, cookie, timeout)
        except DownloadError as exc:
            return False, str(exc)
    return True, ""


def save_zip(download_url, out_dir, name, cookie, timeout, max_size):
    safe = SAFE_NAME_RE.sub("_", name).strip() or "shared-skill.zip"
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / safe
    if final.exists():
        stem, ext = final.stem, final.suffix
        n = 1
        while final.exists():
            final = out_dir / ("%s (%d)%s" % (stem, n, ext))
            n += 1
    part = out_dir / (final.name + ".part")
    try:
        size = _stream_download(download_url, part, cookie, timeout, max_size)
        if not zipfile.is_zipfile(part):
            raise DownloadError(
                "下载到的文件不是有效 zip（可能是 HTML 错误页或 auth expired）。"
                "检查 Cookie 是否刷新、Referer 是否带上，或改用 GUI 下载路径。"
            )
        part.replace(final)
        return final, size
    finally:
        if part.exists():
            try:
                part.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run(args):
    result = {
        "ok": False, "zip": "", "size": 0, "pwd_id": "",
        "passcode_used": False, "cookie_source": "",
        "share_items": [], "selected": None, "download_host": "",
        "verified_steps": ["token", "detail"],
        "unverified_steps": [],
        "route_probe": {
            "sharepage/download": "404 route-not-found（与故意写错的路由响应逐字段一致）→ 不存在",
            "file/download": "GET 405 / POST 401 → 路由存在且仅接受 POST",
            "probed_at": "2026-11-22",
        },
        "transfer": {},
        "warning": "", "error": "",
    }
    try:
        pwd_id, url_passcode = parse_share(args.share)
        passcode = args.passcode or url_passcode
        cookie, source = load_cookie(args)
        result["pwd_id"] = pwd_id
        result["passcode_used"] = bool(passcode)
        result["cookie_source"] = source

        stoken = get_stoken(pwd_id, passcode, cookie, args.timeout)
        if not stoken:
            raise DownloadError("接口未返回 stoken")

        files = collect_files(pwd_id, stoken, cookie, args.timeout, args.max_depth)
        result["share_items"] = [
            {k: f[k] for k in ("path", "fid", "dir", "size")} for f in files
        ]
        if args.list_only:
            result["ok"] = True
            result["warning"] = "仅列出分享内容，未下载（--list-only）"
            return result

        item = pick_zip(files, args.keyword, args.fid)
        result["selected"] = {k: item[k] for k in ("path", "fid", "size")}

        if not args.allow_save_to_drive:
            raise DownloadError(DEAD_ENDPOINT_MSG)

        # Writes into the user's own drive: only after explicit consent.
        fid, fid_source = save_to_drive(pwd_id, stoken, item, cookie, args.timeout)
        result["transfer"] = {"saved_fid": fid, "fid_source": fid_source,
                              "trashed": False, "note": ""}
        result["unverified_steps"] = ["sharepage/save→task→file/download（端到端）"]

        download_url = get_download_url(fid, cookie, args.timeout)
        result["download_host"] = urllib.parse.urlparse(download_url).netloc
        # Never expose the signed URL: it embeds temporary credentials.

        final, size = save_zip(download_url, args.out_dir, item["name"],
                               cookie, args.timeout, args.max_size)
        result["zip"] = str(final)
        result["size"] = size
        result["ok"] = True

        if args.keep_saved:
            result["transfer"]["note"] = "已按 --keep-saved 保留网盘里的副本"
        else:
            ok, why = trash_saved(fid, cookie, args.timeout)
            result["transfer"]["trashed"] = ok
            result["transfer"]["note"] = ("副本已移入回收站" if ok
                                         else "副本移入回收站失败（%s），请手动删除" % why)
        result["warning"] = (
            "token/detail 为已验证接口；转存→取直链这条链的路由已探测但未端到端验证，"
            "换一台机器/换一个分享仍可能失败。%s" % result["transfer"]["note"]
        )
    except DownloadError as exc:
        result["error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
    return result


def print_human(result):
    print("=" * 72)
    print("夸克分享直链下载")
    print("=" * 72)
    print("分享 pwd_id : %s" % result["pwd_id"])
    print("使用提取码  : %s" % ("是" if result["passcode_used"] else "否"))
    print("Cookie 来源 : %s" % result["cookie_source"])
    print("分享内条目  : %d" % len(result["share_items"]))
    if result["share_items"]:
        for it in result["share_items"][:20]:
            tag = "目录" if it["dir"] else "文件"
            print("   [%s] %s  %s" % (tag, it["path"], it["size"]))
    if result["selected"]:
        print("目标 zip    : %s (fid=%s)" % (result["selected"]["path"], result["selected"]["fid"]))
    if result["zip"]:
        print("已下载      : %s (%s bytes)" % (result["zip"], result["size"]))
    tr = result.get("transfer") or {}
    if tr.get("saved_fid"):
        print("网盘副本    : fid=%s（%s）；%s"
              % (tr["saved_fid"], tr.get("fid_source", "?"), tr.get("note", "")))
    if result["unverified_steps"]:
        print("未端到端验证: %s" % ", ".join(result["unverified_steps"]))
    if result["warning"]:
        print("提醒        : %s" % result["warning"])
    if result["error"]:
        print("错误        : %s" % result["error"])
    print("=" * 72)


def default_out_dir():
    """Save inside the skill's own runtime dir, not ~/Downloads.

    The preflight phase exports QSI_DOWNLOAD_DIR; when the script is run by
    hand, fall back to <config>/runtimes/quark-installer/downloads so this
    skill never drops files into a user-visible folder uninvited.
    """
    v = os.environ.get("QSI_DOWNLOAD_DIR", "").strip()
    if v:
        try:
            return Path(v).expanduser()
        except Exception:
            pass
    cfg = os.environ.get("WORKBUDDY_CONFIG_DIR", "").strip()
    base = Path(cfg).expanduser() if cfg else Path.home() / ".workbuddy"
    return base / "runtimes" / "quark-installer" / "downloads"


def main(argv=None):
    _setup_console()
    ap = argparse.ArgumentParser(description="Download a .zip from a Quark share link")
    ap.add_argument("share", help="Share URL or raw pwd_id")
    ap.add_argument("--passcode", "-p", help="提取码；省略时取链接里的 ?pwd=")
    ap.add_argument("--cookie-file", help="Path to a file containing the Cookie header")
    ap.add_argument("--out-dir", default=str(default_out_dir()),
                    help="Where to save the .zip (default: <config>/runtimes/quark-installer/downloads)")
    ap.add_argument("--list-only", action="store_true", help="Only list share contents, do not download")
    ap.add_argument("--keyword", help="Only pick a .zip whose name contains this")
    ap.add_argument("--fid", help="Pick a specific file by fid (skips .zip filtering)")
    ap.add_argument("--max-depth", type=int, default=MAX_DEPTH, help="Max directory recursion depth")
    ap.add_argument("--max-size", type=int, default=MAX_DOWNLOAD, help="Max download size in bytes")
    ap.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds")
    ap.add_argument("--json", action="store_true", help="Emit a single JSON object on stdout")
    ap.add_argument("--allow-save-to-drive", action="store_true",
                    help="允许把分享里的 zip 转存到你自己的网盘再取直链下载"
                         "（会对你的账号写入，需先取得同意；默认关闭）")
    ap.add_argument("--keep-saved", action="store_true",
                    help="配合 --allow-save-to-drive：下载后保留网盘里的那份副本"
                         "（默认会把它移入回收站）")
    args = ap.parse_args(argv)

    result = run(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)
        if not result["ok"]:
            print("错误: %s" % result["error"], file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
