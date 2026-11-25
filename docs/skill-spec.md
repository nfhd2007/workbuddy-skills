# SKILL.md 编写规范

本仓库收录的技能遵循 WorkBuddy / Agent Skills 约定：**一个目录 = 一个技能**，入口文件固定为 `SKILL.md`。

## 目录结构

```
skills/<category>/<name>/
├── SKILL.md          # 必需
├── references/       # 可选：按需加载的长文档
├── scripts/          # 可选：可执行脚本
├── assets/           # 可选：模板、图标等静态资源
├── LICENSE           # 可选：技能自身许可证
└── README.md         # 可选：面向人类的补充说明
```

原则：把「什么时候用」写在 SKILL.md，把「怎么用」的细节拆到 `references/`，避免入口文件过长；脚本只通过相对路径引用同目录资源。

## frontmatter 字段

**最小必需**（本仓库校验强制）：

| 字段 | 规则 |
| --- | --- |
| `name` | `^[a-z0-9]+(-[a-z0-9]+)*$`，≤40 字符，必须等于目录名 |
| `description` | 一句话说清「做什么 + 何时触发 + 触发词」 |

**建议补充**（提升触发质量与可读性）：

| 字段 | 说明 |
| --- | --- |
| `version` | 语义化版本，如 `"1.0.0"`，可带 `-local` 等后缀 |
| `display_name` / `display_name_en` | 中英文显示名，尽量不含空格 |
| `description_zh` / `description_en` | 中英文详细描述 |
| `author` | 作者或来源署名 |
| `license` | 技能许可证，第三方技能务必填写 |
| `category` | 分类备注（本仓库以目录层级为准） |
| `examples_zh` / `examples_en` | 使用示例列表 |
| `agent_created` | 标记由智能体创建 |

> 上架 WorkBuddy 开放平台另有更严格的字段要求（`agent_created: true`、`display_name` 无空格、九字段齐全等）。本仓库用于本地安装与源码存档，不强求，但按完整字段写更省心。

## 标准模板

见 [templates/SKILL.md](../templates/SKILL.md)。示例：

```yaml
---
name: my-skill
version: "1.0.0"
display_name: 我的技能
display_name_en: My-Skill
author: your-name
license: MIT
description: "做什么、何时触发、触发词。含英文冒号的长文本请加双引号。"
description_zh: "中文详细描述。"
description_en: "English description."
examples_zh:
  - "帮我做某件事"
agent_created: true
---

# 我的技能

## 何时使用
...
```

## 常见坑

1. **首行被转义**：编辑后首行变成 `\---`，技能会静默失效。每次改完确认首行是三个连字符。
2. **`: ` 破坏 YAML**：`description: Covers: A and B` 会被解析成新键。所有含英文冒号 + 空格、`#`、前导空格的长文本一律用双引号包裹；中文全角冒号「：」安全，但统一加引号最稳妥。
3. **CRLF 换行**：Windows 编辑器容易存成 CRLF，官方打包校验要求 LF（本仓库 `.gitattributes` 已统一）。
4. **BOM**：UTF-8 BOM 会让 frontmatter 解析失败。
5. **name 与目录名不同步**：改名时目录名、`name`、打包 zip 名必须一起改。
6. **文档与实物脱节**：SKILL.md 里写了 `scripts/foo.py` 但文件不存在，校验脚本会告警。

## 自检

```bash
python scripts/validate_skills.py          # 规范 + 敏感信息
python scripts/build_index.py --check      # 索引是否最新
```

校验脚本用纯标准库实现，不依赖 PyYAML。它只做「够用」的 frontmatter 解析：支持 `key: value`、引号包裹值、`- item` 列表，不支持嵌套对象、锚点等高级 YAML 特性 —— SKILL.md 也不需要。
