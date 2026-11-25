# workbuddy-skills

用于存放 [WorkBuddy](https://www.workbuddy.cn/) 技能（Skills）源文件的个人仓库。

每个技能是一个独立目录，以 `SKILL.md` 为入口（YAML frontmatter + Markdown 使用说明），可附带 `references/`、`scripts/`、`assets/` 等资源。本仓库只保存**可安装到 WorkBuddy 的技能源文件**，不保存运行时数据、凭据或打包产物。

> ⚠️ **本仓库是公开仓库。** 提交前务必阅读 [安全检查清单](docs/security-checklist.md)：禁止提交 Cookie / Token / 密码 / 私钥、账号与答题数据、含本机绝对路径的日志，以及从技能市场下载的第三方或付费技能原件。公开仓库的历史记录无法简单「删掉就算」，误提交需立即撤销凭据并清理历史。

## 仓库结构

```
workbuddy-skills/
├── README.md                 # 本文件
├── INDEX.md                  # 技能索引（自动生成，勿手工编辑）
├── skills.json               # 机器可读索引（自动生成）
├── LICENSE / CHANGELOG.md / CONTRIBUTING.md
├── .gitignore / .gitattributes
├── skills/                   # 技能源文件根目录
│   ├── README.md             # 目录与分类约定
│   └── <category>/<skill>/   # 一个技能一个目录
│       ├── SKILL.md          # 必需：frontmatter + 使用说明
│       ├── references/       # 可选：参考文档
│       ├── scripts/          # 可选：脚本
│       └── assets/           # 可选：静态资源
├── docs/
│   ├── skill-spec.md         # SKILL.md 编写规范
│   └── security-checklist.md # 提交前安全检查清单
├── templates/
│   └── SKILL.md              # 新技能模板
├── scripts/
│   ├── validate_skills.py    # 规范 + 敏感信息校验
│   ├── build_index.py        # 生成 INDEX.md / skills.json
│   └── install_skill.py      # 从本仓库安装单个技能
└── .github/
    ├── workflows/validate.yml
    ├── ISSUE_TEMPLATE/skill-request.md
    └── PULL_REQUEST_TEMPLATE.md
```

## 快速开始

### 安装一个技能

```bash
# 从本仓库拉取指定技能到 ~/.workbuddy/skills/<name>
python scripts/install_skill.py <技能名>

# 指定分支 / 目标目录
python scripts/install_skill.py <技能名> --ref main --dest "D:/my-skills"
```

也可以手动安装：clone 本仓库后，把 `skills/<category>/<name>/` 整个目录复制到技能目录：

| 系统 | 用户级技能目录 |
| --- | --- |
| Windows | `C:\Users\<用户名>\.workbuddy\skills\` |
| macOS / Linux | `~/.workbuddy/skills/` |

项目级技能放在 `<项目>/.workbuddy/skills/`。复制后重启或刷新 WorkBuddy 即可加载。

> 可选：设置环境变量 `GITHUB_TOKEN` 提高 GitHub API 限额（未设置时匿名限额为 60 次/小时，安装单个技能通常够用）。

### 添加一个技能

```bash
mkdir -p skills/<category>/<name>
cp templates/SKILL.md skills/<category>/<name>/SKILL.md
# 编辑 frontmatter 与正文，按需添加 references/ scripts/ assets/
python scripts/validate_skills.py     # 必须通过，0 错误
python scripts/build_index.py         # 更新 INDEX.md / skills.json
```

然后提交 PR。CI 会自动复跑校验，并检查索引是否最新。详见 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [SKILL.md 编写规范](docs/skill-spec.md)。

## 技能索引

见 [INDEX.md](INDEX.md)（自动生成）与 [skills.json](skills.json)（供脚本消费）。

当前收录 5 个技能：教育类 4 个（学习通、智慧树、知到、iTEST 助手）与平台类 1 个（夸克分享技能安装器），完整列表见 [INDEX.md](INDEX.md)。技能版权归各作者，仓库根目录的 MIT 许可仅覆盖基础设施（文档、脚本、模板）。

## 分类约定

| 分类目录 | 用途 |
| --- | --- |
| `automation/` | 桌面、浏览器、GUI 自动化 |
| `education/` | 学习与课程辅助 |
| `development/` | 开发工具、代码与工程 |
| `content/` | 内容创作、文档与媒体 |
| `productivity/` | 效率工具、办公与信息整理 |
| `platform/` | 平台对接、发布与分发 |

分类只是组织手段，不影响技能加载；技能名称以目录名为准。

## 约定速览

- `SKILL.md` 首行必须是 `---`，无 BOM，使用 LF 换行
- `name` 必填，英文小写连字符，**必须与目录名一致**
- `description` 必填，写清「做什么 + 何时触发 + 触发词」
- 含 `: ` 或 `#` 的长文本值必须加双引号
- 单文件不超过 3 MB，不提交 `node_modules/`、`__pycache__/`、`*.zip` 等产物

完整字段说明见 [docs/skill-spec.md](docs/skill-spec.md)。

## 许可与免责

仓库基础文件（README、文档、脚本、模板）采用 [MIT](LICENSE)。各技能目录可自带 `LICENSE` 并保留原作者署名；**请勿将无再分发权限的第三方技能上传到本仓库**。技能由各自作者负责，使用第三方技能前请自行审查其脚本行为。
