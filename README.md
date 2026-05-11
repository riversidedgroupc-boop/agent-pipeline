# Agent Pipeline

硬件产品开发多 Agent 协作框架 — 光机电一体化设备设计流水线。

## 架构

```
需求 → 产品经理 → 机械结构 → 光学 → 运动控制 → 算法 → 整机评审
```

## 快速开始

```bash
cd agent-pipeline
uv sync                                      # 安装依赖
pipeline list                                # 查看所有 Agent
pipeline check                               # 校验流水线完整性
pipeline new <project-name>                  # 基于模板创建新项目
pipeline show <agent-id>                     # 查看 Agent 定义
pipeline status                              # 查看项目进度
```

## 目录结构

```
agent-pipeline/
├── agents/                  # Agent 定义（6 个）
│   └── NN-name/
│       ├── agent.md         # 角色/行业/目标/输入输出
│       ├── template.md      # 输出模板
│       └── checklist.md     # 自检清单
├── core/                    # Python 核心模块
│   ├── schema.py            # Pydantic I/O schema
│   ├── template.py          # 模板加载/解析
│   └── checks.py            # 上下游接口校验
├── cli/                     # CLI 工具
├── examples/                # 案例项目
│   └── pic/                 # 金属表面视觉检测
├── pyproject.toml
└── STATUS.md
```

## Agent 列表

| ID | 名称 | 角色 | 状态 |
|----|------|------|------|
| 01 | pm | 产品经理 | 待定义 |
| 02 | mechanical | 资深工业视觉机械结构工程师 | ✅ 已完成 |
| 03 | optics | 光学工程师 | 待定义 |
| 04 | motion | 运动控制工程师 | 待定义 |
| 05 | algorithm | 算法工程师 | 待定义 |
| 06 | review | 整机评审 | 待定义 |
