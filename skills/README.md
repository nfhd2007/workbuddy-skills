# skills/

技能源文件根目录。**一个子目录 = 一个技能**，目录名即技能 `name`，入口必须是 `SKILL.md`。

```
skills/
└── <category>/
    └── <skill-name>/
        ├── SKILL.md
        ├── references/
        ├── scripts/
        └── assets/
```

推荐分类（可按需新增，分类不参与技能加载）：

| 目录 | 用途 |
| --- | --- |
| `automation/` | 桌面、浏览器、GUI 自动化 |
| `education/` | 学习与课程辅助 |
| `development/` | 开发工具、代码与工程 |
| `content/` | 内容创作、文档与媒体 |
| `productivity/` | 效率工具、办公与信息整理 |
| `platform/` | 平台对接、发布与分发 |

当前收录 5 个技能：`education/` 下 4 个课程助手，`platform/` 下 1 个技能安装器。完整列表见仓库根目录的 [INDEX.md](../INDEX.md)。

新增技能：从 [templates/SKILL.md](../templates/SKILL.md) 复制模板 → 填写 frontmatter → `python scripts/validate_skills.py` → `python scripts/build_index.py`。详见 [贡献指南](../CONTRIBUTING.md) 与 [编写规范](../docs/skill-spec.md)。

> 提醒：这里是公开仓库，不要放 Cookie、答题数据、本机绝对路径或第三方付费技能。
