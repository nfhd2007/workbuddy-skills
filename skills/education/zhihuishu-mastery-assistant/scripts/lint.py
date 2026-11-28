#!/usr/bin/env python3
"""发布前自检：检查 SKILL.md 关键口径与资源完整性。

    python scripts/lint.py [--skill-dir <路径>]

退出码 0 才可打包 / 发布。改版时防止把阶段 P、安全边界、提交授权、
免考跳过、断点续跑、Edge 扩展优先、截图收尾自动清理，以及 v1.3.x 新增的
交付优先原则、按提问范围自适应汇报、route=offline / channel=offline 降级路径、
离线演练交付手册这些关键能力弄丢（借鉴 iTEST 助手 lint.js 的思路）。

v1.3.1 起额外校验「文档引用的 .py 脚本必须内置于 scripts/」——与开放平台
「内置文件缺失」检测口径对齐，防止从其它技能复制口径时残留不存在的脚本名。
"""

import argparse
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REQUIRED_REFERENCES = [
    "site-map.md", "tooling.md", "answering.md",
    "environment.md", "walkthrough.md", "offline.md",
]
REQUIRED_SCRIPTS = ["mastery.py", "cleanup_screenshots.py", "lint.py"]

KEYWORDS = [
    ("阶段 P", "环境自检与自动准备"),
    ("安全边界", "安全边界与红线"),
    ("提交", "自测题提交授权"),
    ("免考", "免考格子跳过"),
    ("断点续跑", "台账续跑 / 直达 URL"),
    ("DOM 快照", "DOM 不可用结论"),
    ("掌握度分析", "核心页面"),
    ("热力图", "未满知识点扫描"),
    ("去提升", "进入自测题"),
    ("dry-run", "只演练不提交"),
    ("tabs_claim", "受控标签接管"),
    ("计分", "计分考核红线"),
    # 用户明确要求：默认优先使用 WorkBuddy Edge 扩展程序
    ("浏览器通道选择", "浏览器通道选择章节"),
    ("Edge 扩展", "Edge 扩展优先通道"),
    ("WorkBuddy Edge 扩展程序", "扩展程序官方名称与安装引导"),
    ("user_tabs", "扩展实例识别字段"),
    ("type=extension", "实例类型判定"),
    ("family=edge", "Edge 实例判定"),
    ("browser_info", "实例能力复核"),
    ("不共享登录态", "内置 IAB 降级理由"),
    # 用户明确要求：运行结束后自动删除本次产生的截图缓存
    ("截图缓存与清理策略", "截图缓存与清理策略章节"),
    ("cleanup_screenshots.py", "截图清理脚本"),
    ("begin --file", "实况通道建立截图清单"),
    ("finish --file", "实况通道收尾自动清理"),
    ("截图清理结果", "清理结果汇报项"),
    ("白名单", "清理目录白名单"),
    ("逐文件", "逐文件删除约束"),
    ("不整目录清空", "禁止整目录删除"),
    ("clipboard-images", "用户剪贴板图片保护"),
    ("--keep", "只列不删开关"),
    # v1.3.x：环境缺失不阻断交付，离线演练为一等交付路径
    ("交付优先原则", "环境缺失不阻断交付"),
    ("按提问范围自适应", "汇报不夹带固定模板"),
    ("route=offline", "工具缺失时的合法继续路径"),
    ("channel=offline", "离线通道判定"),
    ("离线演练交付", "逐题答案清单与看答案怎么填的一等路径"),
    ("静态页面信息速查", "离线可答的页面标题与提示异常"),
    ("references/offline.md", "离线演练交付手册"),
]

# 防止后续改版把参考文档里的通道口径删掉
RESOURCE_KEYWORDS = {
    "tooling.md": ["type=extension", "user_tabs", "browser_info", "family",
                   "cleanup_screenshots.py", "blobs", "替代调用链"],
    "environment.md": ["Edge 扩展", "前往安装", "route=degraded", "route=offline",
                       "cleanup_screenshots.py", "begin"],
    "site-map.md": ["Edge 扩展", "browser_id=2"],
    "walkthrough.md": ["Edge 扩展", "browser_info",
                       "cleanup_screenshots.py", "finish", "F. 离线演练清单"],
    "offline.md": ["逐题", "页面标题", "颜色档位", "存疑", "看答案时怎么填"],
}

FORBIDDEN_LEFTovers = ["example.py", "example_asset.txt", "api_reference.md"]

# 用户明确要求：技能名（frontmatter name）使用中文；目录名保持英文技术标识
REQUIRE_CHINESE_NAME = True


def main():
    parser = argparse.ArgumentParser(description="掌握度助手发布前自检")
    parser.add_argument("--skill-dir", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    args = parser.parse_args()
    root = os.path.abspath(args.skill_dir)
    errors, warnings = [], []

    skill_path = os.path.join(root, "SKILL.md")
    if not os.path.exists(skill_path):
        errors.append("缺少 SKILL.md")
        text = ""
    else:
        with open(skill_path, "r", encoding="utf-8") as f:
            text = f.read()

    # frontmatter
    if text.startswith("---"):
        fm = text.split("---", 2)[1]
    else:
        fm = ""
        errors.append("SKILL.md 缺少 YAML frontmatter")
    for field in ("name:", "description:"):
        if field not in fm:
            errors.append("frontmatter 缺少 %s" % field)
    if not re.search(r"agent_created:\s*true", fm):
        errors.append("frontmatter 必须包含 agent_created: true")
    m = re.search(r"^name:\s*(.+)", fm, re.M)
    dirname = os.path.basename(root)
    if m:
        skill_name = m.group(1).strip().strip('"').strip("'")
        if re.match(r"^[a-z0-9-]+$", skill_name):
            # 英文技术名：遵循 skill-creator 规范，必须与目录名一致
            if skill_name != dirname:
                errors.append("name 与目录名不一致：%s != %s" %
                              (skill_name, dirname))
        else:
            # 中文技能名：平台允许（官方「发布为应用」即中文 name + 英文目录 sites）
            # 目录名仍须为 hyphen-case 技术标识，保证路径与引用稳定
            if not re.match(r"^[a-z0-9-]+$", dirname):
                errors.append("中文 name 时目录名仍须为 hyphen-case 技术标识：%s" % dirname)
            if not re.search(r"^display_name_zh:", fm, re.M):
                warnings.append("中文 name 建议同时提供 display_name_zh")
            if not re.search(r"^display_name_en:", fm, re.M):
                warnings.append("中文 name 建议同时提供 display_name_en")

    # 用户明确要求技能名为中文，防止后续改版回退成英文
    if REQUIRE_CHINESE_NAME:
        if not m or not re.search(r"[\u4e00-\u9fff]", m.group(1)):
            errors.append("技能名必须为中文（用户要求），当前 name 未含中文字符")

    # 用户明确要求：默认优先 WorkBuddy Edge 扩展程序，触发描述里也要体现
    m_desc = re.search(r"^description:\s*(.+)", fm, re.M)
    if m_desc and "Edge" not in m_desc.group(1):
        errors.append("frontmatter description 未声明 Edge 扩展优先")

    # 关键口径
    for keyword, label in KEYWORDS:
        if keyword not in text:
            errors.append("SKILL.md 缺少关键口径「%s」（%s）" % (keyword, label))

    if "[TODO" in text or "TODO:" in text:
        errors.append("SKILL.md 仍有 TODO 占位")
    if len(text) < 3000:
        warnings.append("SKILL.md 偏短（%d 字符），确认不是模板残稿" % len(text))

    # 资源
    for name in REQUIRED_REFERENCES:
        if not os.path.exists(os.path.join(root, "references", name)):
            errors.append("缺少 references/%s" % name)
    for name in REQUIRED_SCRIPTS:
        if not os.path.exists(os.path.join(root, "scripts", name)):
            errors.append("缺少 scripts/%s" % name)
    for name in FORBIDDEN_LEFTovers:
        for sub in ("", "scripts", "references", "assets"):
            p = os.path.join(root, sub, name) if sub else os.path.join(root, name)
            if os.path.exists(p):
                warnings.append("示例文件残留：%s" % os.path.relpath(p, root))

    # 参考文档里的 Edge 扩展口径
    for name, words in RESOURCE_KEYWORDS.items():
        p = os.path.join(root, "references", name)
        if not os.path.exists(p):
            continue  # 文件缺失已由上面的检查报错
        with open(p, "r", encoding="utf-8") as f:
            rtext = f.read()
        for w in words:
            if w not in rtext:
                errors.append("references/%s 缺少 Edge 扩展口径「%s」" % (name, w))

    # 脚本可编译
    for name in REQUIRED_SCRIPTS:
        p = os.path.join(root, "scripts", name)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    compile(f.read(), p, "exec")
            except Exception as exc:
                errors.append("scripts/%s 语法错误：%s" % (name, exc))

    # 资源引用一致性
    for name in REQUIRED_REFERENCES + REQUIRED_SCRIPTS:
        if name not in text:
            warnings.append("SKILL.md 未提及 %s" % name)

    # 文档引用的脚本必须内置（对齐开放平台「内置文件缺失」检测口径）。
    # 扫描 SKILL.md 与 references/*.md 里出现的所有以 .py 结尾的文件名 token，
    # 逐个确认 scripts/ 下存在同名文件。从其它技能复制口径时残留的不存在
    # 脚本名会被这一项拦下，而不是等平台审核驳回；本文件不写出具体脚本名，
    # 避免自身成为新的悬空引用来源。
    doc_files = [("SKILL.md", text)]
    ref_dir = os.path.join(root, "references")
    if os.path.isdir(ref_dir):
        for fn in sorted(os.listdir(ref_dir)):
            if fn.endswith(".md"):
                with open(os.path.join(ref_dir, fn), "r", encoding="utf-8") as f:
                    doc_files.append(("references/" + fn, f.read()))
    py_token = re.compile(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_./-]+\.py)\b")
    md_token = re.compile(r"`(references/[A-Za-z0-9_-]+\.md)`")
    cited_py = {}
    for doc_name, dtext in doc_files:
        for mt in py_token.finditer(dtext):
            base = os.path.basename(mt.group(1))
            cited_py.setdefault(base, set()).add(doc_name)
        for mt in md_token.finditer(dtext):
            rel = mt.group(1)
            if not os.path.exists(os.path.join(root, rel.replace("/", os.sep))):
                errors.append("%s 引用了不存在的资源 %s" % (doc_name, rel))
    for base in sorted(cited_py):
        if not os.path.exists(os.path.join(root, "scripts", base)):
            errors.append(
                "文档引用了未内置的脚本 scripts/%s（引用方：%s）——平台会判「内置文件缺失」，"
                "请删除该引用或把脚本放进 scripts/" %
                (base, ", ".join(sorted(cited_py[base]))))

    for w in warnings:
        print("[警告] %s" % w)
    for e in errors:
        print("[错误] %s" % e)
    if errors:
        print("\n自检未通过：%d 项错误、%d 项警告" % (len(errors), len(warnings)))
        return 1
    print("\n自检通过：%d 项关键口径齐全，资源完整（%d 项警告）；"
          "文档引用的 %d 个脚本均已内置于 scripts/" %
          (len(KEYWORDS), len(warnings), len(cited_py)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
