# 贡献指南

感谢参与。本仓库只收录**可以安全公开**的 WorkBuddy 技能源文件。

## 提交流程

1. 先开 Issue 或在 PR 中描述技能用途、触发场景、是否依赖外部服务。
2. 在 `skills/<category>/<name>/` 下创建目录，`name` 与目录名一致（小写英文连字符）。
3. 从 `templates/SKILL.md` 复制模板，填写 frontmatter 与正文。
4. 把长篇说明拆到 `references/`，可执行代码放 `scripts/`，静态资源放 `assets/`。
5. 本地自检：`python scripts/validate_skills.py`（必须 0 错误）。
6. 更新索引：`python scripts/build_index.py`，把 `INDEX.md`、`skills.json` 一并提交。
7. 提交 PR，CI 会自动校验。

## 硬性要求

- 必须通过 `scripts/validate_skills.py`，ERROR 为 0；WARNING 请在 PR 中说明。
- 不得提交 Cookie、Token、密码、私钥、账号数据、答题 / 成绩数据、含本机绝对路径的日志。
- 不得提交 `node_modules/`、`__pycache__/`、`*.zip`、截图、超过 3 MB 的文件。
- 只提交你有权公开的技能。从技能市场安装的付费 / 第三方技能、他人作品需获得授权，并在目录内保留 `LICENSE` 与 `author` 署名。
- `SKILL.md` 中引用的 `references/` `scripts/` `assets/` 文件必须真实存在。

## 提交信息

使用 `feat: 新增 xxx 技能` / `fix: 修正 xxx 的 frontmatter` / `docs: 更新索引` 这类前缀，一次提交只做一件事。

## 版本与更新

改动已收录技能时递增 `version`（语义化版本），并在 CHANGELOG.md 记一笔。修复错别字、格式类改动可不升版本。

## 行为准则

保持友善、就事论事。涉及他人隐私或凭据的内容，请不要贴进 Issue / PR，直接联系维护者。
