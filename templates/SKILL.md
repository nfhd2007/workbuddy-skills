---
name: skill-name
version: "1.0.0"
display_name: 技能显示名
display_name_en: Skill-Display-Name
author: your-name
license: MIT
category: development
description: "一句话说明这个技能做什么、什么时候该用、有哪些触发词。含英文冒号的长文本请加双引号。"
description_zh: "中文详细描述：能力范围、适用场景、不适用场景。"
description_en: "English description: what it does, when to use it, trigger words."
examples_zh:
  - "帮我做某件事"
  - "用某某技能处理这个文件"
examples_en:
  - "Do something for me"
agent_created: true
---

# 技能显示名

## 何时使用

- 用户说「……」时使用
- 不适用于：……（写清边界，避免误触发）

## 使用步骤

1. 环境检查：……
2. 执行：……
3. 结果复核：……

## 注意事项

- 会读写的文件 / 是否会联网 / 是否需要用户确认
- 破坏性操作必须先征得用户同意

## 资源

- 详细参考：`references/xxx.md`
- 脚本：`scripts/xxx.py`

---

> 模板说明（使用时删除本段）：`name` 必须与目录名一致；首行保持 `---`；全文件使用 LF 换行；把长文档拆到 `references/`，可执行代码放 `scripts/`。
