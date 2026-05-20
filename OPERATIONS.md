# Agent Pipeline 操作手册

## 项目概述

硬件产品开发多 Agent 协作框架。6 个专业 Agent 按流水线依次产出方案文档，通过飞书群机器人与用户交互。

**核心场景**：在飞书群里 @机器人 启动新项目 → 输入需求 → PM 生成技术方案 → 审阅通过 → 自动运行全部下游 Agent（机械/光学/运动控制/算法/整机评审）。

---

## 环境准备

### 1. 依赖

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器

```bash
cd D:\work\agent-pipeline
uv sync
```

### 2. 配置 API 密钥

复制 `.env.example` 为 `.env`，填入真实密钥：

```env
# LLM API（至少配一个）
DEEPSEEK_API_KEY=sk-xxxxxxxx
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...

# 飞书应用
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
```

### 3. 飞书应用配置

在 [飞书开放平台](https://open.feishu.cn) 创建企业自建应用：

| 配置项 | 值 |
|--------|-----|
| 能力 | 机器人 |
| 权限 | `im:message`、`im:message:read`、`im:chat`、`im:file` |

将应用发布上线，然后添加到目标群聊。

### 4. 检查环境

```bash
uv run pipeline check          # 验证 pipeline 完整性
uv run pipeline config-show    # 查看当前配置
```

---

## 架构

### Agent 流水线

```
01-pm (产品经理)
  ↓
02-mechanical (机械结构)
  ↓
03-optics (光学)
  ↓
04-motion (运动控制)
  ↓
05-algorithm (算法)
  ↓
06-review (整机评审) ← 读取 01-05 全部输出
```

每个 Agent 是**完全独立**的：从磁盘读取上游文档，写入自己的输出文件。

### 文件结构

```
agent-pipeline/
├── agents/                  # Agent 定义（每个一个文件夹）
│   ├── 01-pm/
│   │   ├── agent.md         # 系统提示词（角色、目标、约束）
│   │   └── template.md      # 输出模板
│   ├── 02-mechanical/
│   └── ...
├── core/                    # 引擎、上下文组装、配置
├── cli/                     # CLI 命令（pipeline + feishu）
├── feishu/                  # 飞书机器人（消息、状态、导出）
├── examples/                # 项目输出目录（按项目名分文件夹）
│   └── <项目名>/
│       ├── requirements.md          # 客户需求（内部）
│       ├── 01-pm-方案.md           # Agent 输出（内部中间格式）
│       ├── 01-pm-方案.docx         # Agent 输出（对外 Word 文档）
│       └── ...
├── pipeline.yaml            # 模型配置
├── .env                     # API 密钥（不入库）
└── .geniusforge/            # 运行时状态（自动生成）
    ├── project-states.json  # 项目创建状态机
    └── message-map.json     # 飞书消息→Agent 映射
```

### 数据流

```
用户需求 → requirements.md
                ↓ 注入到所有 Agent 的 prompt
Agent 生成 → {agent_id}-方案.md   （内部，Agent 间通信）
          → {agent_id}-方案.docx （对外，飞书推送）
```

---

## CLI 命令

所有命令在项目根目录 `D:\work\agent-pipeline` 执行。

### pipeline 主命令

| 命令 | 说明 |
|------|------|
| `pipeline list` | 列出所有 Agent 及上下游关系 |
| `pipeline check` | 验证 pipeline 完整性 |
| `pipeline show <agent_id>` | 查看 Agent 定义（如 `pipeline show 03-optics`） |
| `pipeline config-show` | 查看当前模型配置 |
| `pipeline new <项目名>` | 从模板创建项目骨架 |
| `pipeline run <项目名>` | **运行完整流水线**（01 → 06 依次执行） |
| `pipeline run <项目名> --agent 03-optics` | 单独运行某个 Agent |
| `pipeline run <项目名> --from 04-motion` | 从指定 Agent 开始接续运行 |

### pipeline feishu 子命令

| 命令 | 说明 |
|------|------|
| `pipeline feishu chats` | 列出机器人已加入的飞书群 |
| `pipeline feishu listen` | **启动后台监听**（推荐用法，自动发现所有群） |
| `pipeline feishu listen --chat-id <id>` | 只监听指定群 |
| `pipeline feishu push <agent_id> --chat-id <id>` | 手动推送某个 Agent 方案到群 |
| `pipeline feishu push-all --chat-id <id>` | 推送全部方案到群 |
| `pipeline feishu status --chat-id <id>` | 推送项目状态到群 |
| `pipeline feishu feedback --chat-id <id>` | 拉取群内反馈 |
| `pipeline feishu export-all --chat-id <id>` | 导出全部方案为 Word 并上传 |
| `pipeline feishu export-push <agent_id> --chat-id <id>` | 导出单个方案 |

### 运行示例

```bash
# 本地完整流水线
uv run pipeline run pic

# 只重跑光学方案（带反馈）
uv run pipeline run pic --agent 03-optics

# 启动飞书机器人（后台常驻）
uv run pipeline feishu listen
```

---

## 飞书交互流程

### 启动机器人

在终端启动监听（保持窗口不关）：

```bash
cd D:\work\agent-pipeline
uv run pipeline feishu listen
```

输出：
```
Auto-discovered 1 chat(s):
  oc_xxxxxxxx — 某测试群
Listening on 1 chat(s) (poll every 10s). Ctrl+C to stop.
```

### 完整项目流程

#### 第 1 步：新建项目

在群里发：

> 新建项目

机器人回复：
> 🚀 收到！请输入新项目名称（例如：手机屏幕检测）：

回复项目名称，例如：
> 钢棒表面检测

机器人回复：
> ✅ 项目「钢棒表面检测」已创建！
> 请描述客户需求（如：检测分辨率、节拍时间、缺陷类型等）：

#### 第 2 步：输入需求

> 单根钢棒，长 3-6 米，直径 5-20mm，银亮材，40m/min。缺陷主要是划痕、凹坑、黑点，最小缺陷 0.1mm。需要 360° 全覆盖检测。

机器人收到后**自动运行 PM Agent**，生成技术方案 Word 文档并上传到群。

#### 第 3 步：审阅 PM 方案

PM 方案生成后，可以：

- **修改方案**：直接回复修改意见，PM 重新生成
  > 光源方案改成环形 LED，亮度 2000lux 以上
  
- **确认通过**：回复 ✅ 或 "确认通过"，自动触发全部下游 Agent
  > ✅

确认后流程：
```
✅ PM 方案确认通过！
正在运行全部下游 Agent：
机械结构 → 光学 → 运动控制 → 算法 → 整机评审
```

全部完成后上传 6 份 Word 方案文档。

#### 第 4 步：后续操作

项目完成后：

| 群里发 | 作用 |
|--------|------|
| `状态` | 查看流水线状态（Token 消耗、成本） |
| `查看 光学` | 重新发送光学方案 |
| `重跑 03-optics` | 重新生成光学方案 |
| `帮助` | 显示命令列表 |
| `新建项目` | 开始下一个项目 |

### 反馈匹配

回复机器人消息时，系统自动识别是哪条消息（哪个 Agent），不需要手动指定。

独立发送反馈时，需要在文本中包含 Agent 名称：
> 光学 环形LED亮度改成 3000lux
> 03-optics 需要增加偏振方案

---

## 配置

### pipeline.yaml

```yaml
model:
  provider: deepseek        # anthropic / deepseek
  model: deepseek-v4-pro
  max_tokens: 8192
  temperature: 0.3

retry: 2                   # LLM 调用失败重试次数
output_dir: examples       # 项目输出目录
verbose: false
```

### Agent 定制

每个 Agent 在 `agents/<id>/` 下有两个文件：

- **agent.md**：YAML frontmatter + 系统提示词。frontmatter 中配置 `id`、`title`、`upstream`、`downstream`。
- **template.md**：输出模板，Agent 按此结构填充方案。

修改后无需重启，下次调用自动生效。

---

## 常见问题

### Q: @机器人没反应？

1. 确认 `pipeline feishu listen` 在运行
2. 确认机器人在群里（`pipeline feishu chats`）
3. 确认飞书应用权限已配置（`im:message`）

### Q: 项目名出现乱码（如 @_user_1）？

已修复：系统自动过滤 @mention 文本。如仍有问题，重启 listen 即可。

### Q: PM 方案与需求无关？

已修复：`requirements.md` 现在注入到所有 Agent 的 prompt 中。如旧项目有问题，重跑即可。

### Q: Review Agent 检查不全面？

已修复：Review Agent 现在读取全部 01-05 的输出，而非仅 01 和 05。

### Q: 如何重跑某个 Agent？

```bash
# 命令行
uv run pipeline run <项目名> --agent 03-optics

# 飞书群里
重跑 03-optics
```

### Q: 如何清理旧项目状态？

删除状态文件：
```bash
rm D:\work\agent-pipeline\.geniusforge\project-states.json
```

### Q: 多群并发怎么办？

`listen` 默认自动发现所有群并同时监控，每 60 秒刷新群列表。不同群的项目状态互相隔离。

---

## 成本估算

DeepSeek V4 定价：输出 $1.10 / 1M tokens（约 ¥7.97 / 1M tokens）。

6 Agent 完整流水线预估：
- PM 方案：~3000 tokens
- 机械/光学/运动/算法：各 ~2000-4000 tokens
- 整机评审：~5000 tokens
- **合计约 ¥0.15-0.30 / 项目**
