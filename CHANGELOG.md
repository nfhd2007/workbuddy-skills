# Changelog

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
