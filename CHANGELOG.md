# Changelog

## 2026-11-28 (v1.3.1)

- 修复 `skills/education/zhihuishu-mastery-assistant` 文件质量检测驳回项：`references/tooling.md` 曾引用不存在的 `preflight.py`（`prepare --json` / `env_file` 口径为跨技能复制残留），已改为对齐本技能真实机制（`scripts/cleanup_screenshots.py` 的运行时动态路径解析），`references/environment.md` 同源残留一并清除。
- `scripts/lint.py` 新增「文档引用的 .py 脚本必须内置于 scripts/」检查，与平台「内置文件缺失」检测口径对齐，并以坏样本回归验证可拦截。
- 版本号 v1.3.0 → v1.3.1；`INDEX.md` / `skills.json` 由 `scripts/build_index.py` 重新生成。

## 2026-11-28

- 新增 `skills/education/zhihuishu-mastery-assistant`（知到/智慧树掌握度助手 v1.3.0）：浏览器工具 / 已登录会话 / 桌面动作层缺失时按只读或离线演练通道继续交付，附 `references/offline.md` 离线演练手册
- 提交前按仓库规范脱敏：实测记录中的真实姓名改为占位描述
- `INDEX.md` 与 `skills.json` 由 `scripts/build_index.py` 重新生成，更新为 5 个技能

## 2026-11-25

- 初始化仓库骨架：README、目录与分类约定、`.gitignore`、`.gitattributes`、MIT 许可
- 新增 `docs/skill-spec.md`（SKILL.md 编写规范）与 `docs/security-checklist.md`（提交前安全检查清单）
- 新增 `templates/SKILL.md` 技能模板
- 新增三个工具脚本：`validate_skills.py`（校验）、`build_index.py`（索引）、`install_skill.py`（安装）
- 新增 GitHub Actions 校验工作流与 Issue / PR 模板
- 生成初始 `INDEX.md` 与 `skills.json`
- 收录 5 个技能：`itest-assistant`、`chaoxing-homework`、`hike-course-assistant`、`zhidao-course-assistant`（`education/`）与 `quark-share-skill-installer`（`platform/`）
- 收录前完成脱敏：移除 `_skillhub_meta.json`、`shots/`、`audio/`、`node_modules/`、`.archive/`、`.cx/` 等安装与运行时数据，本机绝对路径改为泛化描述，补齐缺失的 `author`
- 移除 `skills/education/chaoxing-homework`（学习通作业助手）；`INDEX.md` 与 `skills.json` 同步更新为 4 个技能
