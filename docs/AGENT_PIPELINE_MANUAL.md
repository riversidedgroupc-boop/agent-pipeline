# Agent Pipeline 项目说明书

> 适用项目：`agent-pipeline`  
> 说明对象：硬件产品开发多 Agent 协作框架  
> 典型场景：金属管棒线材、金属表面缺陷、高速工业视觉、光机电一体化非标设备方案设计

## 1. 项目概述

`agent-pipeline` 是一个面向工业视觉检测设备开发的多 Agent 流水线框架。它把一个复杂的光机电一体化设备设计过程拆成 6 个专业阶段，每个阶段由一个独立 Agent 负责产出一份结构化 Markdown 方案文档。

整体目标不是让一个模型一次性写完所有内容，而是让每个 Agent 只处理自己专业范围内的问题，并把上游输出作为下游输入，形成可追踪、可复核、可逐段重跑的工程文档流水线。

核心流水线如下：

```text
客户/市场/产线需求
  -> 01-pm 产品经理
  -> 02-mechanical 机械结构
  -> 03-optics 光学
  -> 04-motion 运动控制
  -> 05-algorithm 算法
  -> 06-review 整机评审
```

每个 Agent 都包含 3 个文件：

| 文件 | 作用 |
| --- | --- |
| `agent.md` | 定义 Agent 的角色、行业背景、设计目标、输入输出、设计原则、上下游接口 |
| `template.md` | 定义该 Agent 输出文档的章节结构 |
| `checklist.md` | 定义该 Agent 自检清单，用于评审输出质量 |

## 2. 适用范围

本项目适合用于以下类型的前期方案设计和跨专业协作：

- 工业视觉检测设备方案设计
- 金属管、棒、线材表面缺陷检测
- 多相机、多光源、多角度照明检测系统
- 在线高速检测设备
- 机械、光学、电气、运动控制、算法协同设计
- FAT/SAT 验收前的方案评审与风险梳理

它不直接替代 CAD 建模、PLC 编程、算法训练或真实工程计算软件，而是用于生成结构化的设计方案、接口约束、选型建议、风险评审和测试计划。

## 3. 技术组成

项目是一个 Python CLI 工具，主要组成如下：

| 模块 | 说明 |
| --- | --- |
| `cli/` | 命令行入口，提供 `pipeline list/check/new/show/status/run/config-show` 等命令 |
| `core/config.py` | 加载 `pipeline.yaml` 配置，读取 API key 环境变量 |
| `core/template.py` | 读取 Agent 文件，解析 Markdown YAML frontmatter |
| `core/context.py` | 组装 system prompt 和 user prompt |
| `core/runner.py` | 调用 LLM API，目前支持 Anthropic provider |
| `core/engine.py` | 串行调度 Agent，读取上游文档，写入当前 Agent 输出 |
| `core/checks.py` | 校验 Agent 链路、上下游引用、必需文件 |
| `agents/` | 6 个 Agent 的定义、模板和自检清单 |
| `examples/` | 默认项目输出目录 |
| `tests/` | 单元测试 |

当前 LLM provider 支持情况：

| Provider | 状态 |
| --- | --- |
| `anthropic` | 已支持 |
| `openai` | 未实现，配置后会明确报错 |
| `deepseek` | 未实现，配置后会明确报错 |

## 4. 配置说明

配置文件位于项目根目录：

```text
pipeline.yaml
```

当前配置示例：

```yaml
model:
  provider: anthropic
  model: claude-sonnet-4-6
  max_tokens: 8192
  temperature: 0.3

retry: 2
output_dir: examples
verbose: false
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `model.provider` | LLM 服务商，目前只支持 `anthropic` |
| `model.model` | 调用的 Anthropic Messages API 模型名 |
| `model.max_tokens` | 单次生成最大 token 数 |
| `model.temperature` | 生成随机性，方案类文档建议保持较低 |
| `retry` | LLM 调用失败后的重试次数 |
| `output_dir` | 项目输出目录，默认 `examples` |
| `verbose` | 是否输出更详细的运行日志 |

API key 不写入配置文件，而是通过环境变量读取：

```text
ANTHROPIC_API_KEY=sk-ant-...
```

可以参考 `.env.example`。

## 5. 命令行使用说明

所有命令默认在项目根目录执行：

```powershell
cd D:\work\agent-pipeline
```

### 5.1 查看 Agent 列表

```powershell
pipeline list
```

作用：

- 列出所有 Agent
- 显示每个 Agent 的 ID、标题、上游、下游
- 用于确认当前流水线结构

### 5.2 校验流水线完整性

```powershell
pipeline check
```

校验内容：

- 是否存在 `agents/` 目录
- 每个 Agent 是否存在 `agent.md`
- 每个 Agent 是否存在 `template.md`
- 每个 Agent 是否存在 `checklist.md`
- Agent ID 是否重复
- 上游引用是否存在
- 下游引用是否存在
- 上下游关系是否互相声明
- 首个 Agent 是否无上游
- 末尾 Agent 是否无下游
- 中间 Agent 是否同时具备上游和下游

### 5.3 创建新项目

```powershell
pipeline new <project-name>
```

示例：

```powershell
pipeline new metal-surface-demo
```

作用：

- 在 `output_dir` 下创建一个项目目录
- 默认路径为 `examples/<project-name>/`
- 为每个 Agent 创建一份初始输出文档
- 初始文档来自对应 Agent 的 `template.md`

生成文件示例：

```text
examples/metal-surface-demo/
  01-pm-方案.md
  02-mechanical-方案.md
  03-optics-方案.md
  04-motion-方案.md
  05-algorithm-方案.md
  06-review-方案.md
```

### 5.4 查看某个 Agent 定义

```powershell
pipeline show <agent-id>
```

示例：

```powershell
pipeline show 03-optics
```

作用：

- 打印该 Agent 的标题和正文定义
- 用于查看角色定位、输入输出、设计原则和上下游接口

### 5.5 查看项目状态

```powershell
pipeline status
```

作用：

- 打印根目录下的 `STATUS.md`
- 用于快速查看当前 Agent 完成情况和阶段说明

### 5.6 查看当前配置

```powershell
pipeline config-show
```

作用：

- 打印当前 provider、model、max_tokens、temperature、retry、output_dir、verbose
- 用于确认运行参数

### 5.7 运行完整流水线

```powershell
pipeline run <project-name>
```

示例：

```powershell
pipeline run metal-surface-demo
```

执行逻辑：

1. 按 Agent ID 顺序读取 `agents/` 下的 Agent。
2. 对每个 Agent 加载 `agent.md` 作为 system prompt。
3. 加载 `template.md` 作为输出结构要求。
4. 从项目目录读取该 Agent 声明的上游输出文档。
5. 组装 prompt 后调用 LLM。
6. 将输出写入 `<agent-id>-方案.md`。
7. 当前 Agent 成功后继续下一个 Agent。
8. 任一 Agent 失败后停止流水线。

### 5.8 运行单个 Agent

```powershell
pipeline run <project-name> --agent <agent-id>
```

示例：

```powershell
pipeline run metal-surface-demo --agent 04-motion
```

适用场景：

- 只想重跑某一个 Agent
- 上游文档已经人工修改完成
- 某个阶段输出不满意，需要单独刷新
- 多人协作时不同人负责不同阶段

注意：

- 单 Agent 运行仍会读取它声明的上游文档。
- 如果上游文档缺失，当前实现不会强制报错，而是以已有信息组装 prompt。
- 为保证输出质量，建议先确认上游文档已经存在且内容完整。

### 5.9 从某个 Agent 继续运行

```powershell
pipeline run <project-name> --from <agent-id>
```

示例：

```powershell
pipeline run metal-surface-demo --from 03-optics
```

适用场景：

- 01-02 已经完成，只想从 03 继续
- 中途失败后，从失败点恢复
- 修改了某个中间文档，希望重新生成它和下游结果

如果传入不存在的 Agent ID，CLI 会给出简洁错误提示。

## 6. 文档流转机制

每个 Agent 的输出是一个 Markdown 文件，默认文件名为：

```text
<agent-id>-方案.md
```

例如：

```text
01-pm-方案.md
02-mechanical-方案.md
03-optics-方案.md
04-motion-方案.md
05-algorithm-方案.md
06-review-方案.md
```

上游读取规则：

- Agent 的上游由 `agent.md` frontmatter 中的 `upstream` 字段定义。
- `core/context.py` 会读取项目目录下对应的上游输出文件。
- 读取到的上游文档会放入 user prompt 的“上游输入文档”部分。
- 当前 Agent 的模板会放入 user prompt 的“输出模板”部分。
- 模板中的 HTML 注释会被剥离，避免模型照抄注释。

prompt 组成方式：

| Prompt 部分 | 来源 | 作用 |
| --- | --- | --- |
| system prompt | 当前 Agent 的 `agent.md` 正文 | 定义角色、目标、原则和专业边界 |
| user prompt 上游输入 | 项目目录里的上游方案文件 | 提供当前阶段设计依据 |
| user prompt 输出模板 | 当前 Agent 的 `template.md` | 约束输出章节结构 |
| user prompt 指令 | `core/context.py` 内置指令 | 要求输出纯 Markdown，按模板填充，量化参数，不保留占位符 |

## 7. Agent 总览

| 阶段 | Agent ID | 名称 | 上游 | 下游 | 核心任务 |
| --- | --- | --- | --- | --- | --- |
| 01 | `01-pm` | 产品经理 Agent | 无 | `02-mechanical` | 把客户、市场、产线约束转成产品规格书 |
| 02 | `02-mechanical` | 机械结构 Agent | `01-pm` | `03-optics` | 设计整机结构、相机/光源安装、传动、防振、维护和 BOM |
| 03 | `03-optics` | 光学 Agent | `02-mechanical` | `04-motion` | 设计光源、镜头、相机、偏振、滤光、防护和装调 |
| 04 | `04-motion` | 运动控制 Agent | `03-optics` | `05-algorithm` | 设计采集时序、触发同步、编码器、电气接口和异常处理 |
| 05 | `05-algorithm` | 算法 Agent | `04-motion` | `06-review` | 设计预处理、融合、缺陷检测、分类分级、部署和验证策略 |
| 06 | `06-review` | 整机评审 Agent | `05-algorithm` | 无 | 审查接口一致性、需求追踪、风险、测试计划和最终结论 |

## 8. Agent 详细说明

### 8.1 `01-pm` 产品经理 Agent

#### 角色定位

产品经理 Agent 是整个流水线的起点。它负责把外部输入转化为工程团队可以直接使用的产品规格书。它不做具体机械、光学或算法设计，而是定义问题边界、验收目标和工程约束。

#### 典型输入

- 客户原始需求
- 销售或售前收集的痛点
- 竞品参数和市场定位
- 产线布局、节拍、空间、电气和通信条件
- 行业标准、安全要求、验收要求
- 样件类型和缺陷样本信息

#### 核心能力

- 将模糊需求转成工程指标
- 定义检测对象的材质、尺寸、表面状态和检测方式
- 定义缺陷类型、最小检出尺寸、检测率、误判率
- 定义在线或离线检测模式
- 定义产线接口、上下料方式、分选方式
- 定义 FAT/SAT 验收标准
- 明确成本、节拍、安装空间和维护约束

#### 输出文档

产品经理 Agent 输出 `01-pm-方案.md`，主要包括：

1. 产品规格书
2. 缺陷分类表
3. 产线接口需求
4. 验收标准

#### 输出价值

这份文档是后续所有 Agent 的设计基准。机械 Agent 从中提取尺寸、节拍和安装约束；光学 Agent 从中提取缺陷尺寸和表面特性；算法 Agent 从中提取检测率、误判率和缺陷分类规则；评审 Agent 用它作为需求追踪源头。

#### 质量关注点

- 所有关键指标必须量化。
- 不能只写“效果好”“速度快”等模糊表达。
- 每个验收指标应有可测试方法。
- 暂时无法确定的参数应标注“待验证”或“待上游确认”。

### 8.2 `02-mechanical` 机械结构 Agent

#### 角色定位

机械结构 Agent 负责把产品规格转化为可制造、可装调、可维护的整机机械方案。它连接产品需求和光学系统，是设备物理实现的核心阶段。

#### 上游输入

来自 `01-pm` 的产品规格书和缺陷分类要求，重点关注：

- 产品尺寸范围
- 产线速度
- 检测节拍
- 安装空间
- 检测方式
- 缺陷类型与最小尺寸
- 分选和上下料方式

#### 核心能力

- 整机结构方案设计
- 相机安装方案设计
- 光源安装方案设计
- 传动机构设计
- 张紧机构设计
- 调焦机构设计
- 防振结构设计
- 气路结构设计
- 维护方案设计
- BOM 初步建议
- 3D 结构描述
- CAD 建模指导

#### 输出文档

机械结构 Agent 输出 `02-mechanical-方案.md`，主要包括：

1. 设备结构方案
2. 相机安装方案
3. 光源安装方案
4. 传动机构
5. 张紧机构
6. 调焦机构
7. 防振结构
8. 气路结构
9. 维护方案
10. BOM 建议
11. 3D 结构描述
12. CAD 建模指导

#### 关键设计指标

机械阶段通常需要关注：

- 检测区域内产品位置重复性
- 相机与光源相对位置漂移
- 检测站固有频率
- 换型调整时间
- 日常维护时间
- 调焦、平移、角度调节自由度
- 防护等级和安全防护
- 线缆走线和运动部件安全

#### 对下游的价值

机械 Agent 为光学 Agent 提供：

- 相机安装位置
- 光源安装空间
- 产品和相机的几何关系
- 工作距离约束
- 结构刚度和振动环境
- 调焦和装调自由度

这些信息直接决定光学系统能否实现稳定成像。

### 8.3 `03-optics` 光学 Agent

#### 角色定位

光学 Agent 负责构建成像能力的物理基础。它根据检测对象、缺陷类型、机械安装空间和产线节拍，设计光源、镜头、相机、偏振、滤光、防护和装调方案。

#### 上游输入

主要来自 `02-mechanical`，同时依赖 `01-pm` 中的缺陷目标：

- 产品材质和表面状态
- 缺陷最小尺寸
- 相机安装空间
- 光源安装空间
- 工作距离
- 视野范围
- 相机数量和角度
- 光源布置角度

#### 核心能力

- 光源类型选择
- 光源波长和角度设计
- 多角度照明覆盖设计
- 镜头焦距、光圈、畸变和接口选型
- 相机分辨率、帧率、像元尺寸和接口选型
- 偏振消反射方案设计
- 滤光方案设计
- 镜头防护和光源散热设计
- 白板、标定板、偏振正交等装调流程设计

#### 输出文档

光学 Agent 输出 `03-optics-方案.md`，主要包括：

1. 光源设计方案
2. 镜头选型方案
3. 相机选型方案
4. 偏振与滤光方案
5. 防护与散热方案
6. 安装调试方案

#### 关键设计指标

光学阶段通常需要关注：

- 单像素分辨率是否满足最小缺陷尺寸
- 多角度照明是否覆盖全周缺陷
- 任意方向划痕是否至少在多个角度可见
- 偏振消光比
- 视场照度均匀性
- 光源寿命和光衰
- 镜头防尘等级
- 光源散热温度
- 畸变对测量和算法的影响

#### 对下游的价值

光学 Agent 为运动控制 Agent 提供：

- 相机触发方式
- 曝光时间
- 帧率要求
- 光源频闪时序
- 采集循环参数

它也为算法 Agent 提供：

- 分辨率
- 像元尺寸
- 畸变参数
- 多角度图像特性
- 偏振和反光残留情况

### 8.4 `04-motion` 运动控制 Agent

#### 角色定位

运动控制 Agent 负责把机械运动、相机采集和光源频闪组织成可靠的时序系统。它保证多相机、多光源、多角度采集在空间上对齐、时间上同步，并能和产线 PLC/MES 稳定交互。

#### 上游输入

主要来自 `03-optics`，并依赖部分机械方案：

- 相机触发模式
- 曝光时间
- 光源频闪参数
- 相机帧率
- 传动机构设计
- 编码器安装方式
- 分选机构动作时间
- 产线速度和节拍

#### 核心能力

- 采集时序设计
- 运动控制架构设计
- 触发同步设计
- 编码器集成方案设计
- 异常处理策略设计
- 电气接口定义
- PLC、运动控制器、总线和 I/O 架构建议
- 与产线 PLC 和 MES 的握手逻辑设计

#### 输出文档

运动控制 Agent 输出 `04-motion-方案.md`，主要包括：

1. 采集时序方案
2. 运动控制架构
3. 触发同步方案
4. 编码器集成方案
5. 异常处理策略
6. 电气接口定义

#### 关键设计指标

运动控制阶段通常需要关注：

- 单次采集循环时间
- 触发位置精度
- 光源点亮和相机曝光窗口重合度
- 编码器脉冲到线分辨率的换算
- 产线 PLC 响应时间
- 掉帧、光源未亮、编码器丢信号等异常检测
- 急停、安全继电器和硬件联锁
- 强弱电隔离和接地

#### 对下游的价值

运动控制 Agent 为算法 Agent 提供：

- 图像采集顺序
- 每张图像对应的角度或工位
- 编码器分辨率
- 空间标定依据
- 触发延迟和曝光时间
- 可能存在的掉帧、错位或时序抖动约束

这些信息会影响算法融合、图像配准、缺陷定位和最终分选时机。

### 8.5 `05-algorithm` 算法 Agent

#### 角色定位

算法 Agent 负责把上游形成的图像采集能力转化为缺陷检测、分类、分级和部署方案。它既覆盖传统 OpenCV 管线，也覆盖 YOLO、UNet、异常检测、模型部署和推理优化。

#### 上游输入

主要来自 `04-motion`，同时需要理解前面阶段的设计结果：

- 缺陷分类表
- 相机分辨率和像元尺寸
- 镜头畸变参数
- 多角度采集顺序
- 曝光和触发时序
- 编码器分辨率
- 偏振和反光处理效果
- 产线节拍和推理时间上限

#### 核心能力

- 图像预处理方案设计
- 多角度图像融合方案设计
- 缺陷检测策略设计
- 缺陷分类和分级逻辑设计
- 传统 OpenCV baseline 设计
- 深度学习模型选型
- 异常检测冷启动策略
- YOLO/UNet/OBB/分割等路线选择
- 模型部署和推理优化
- 验证集、测试集、指标和迭代策略设计

#### 输出文档

算法 Agent 输出 `05-algorithm-方案.md`，主要包括：

1. 图像预处理方案
2. 融合算法方案
3. 缺陷检测方案
4. 缺陷分类分级方案
5. 模型部署方案
6. 验证与迭代策略

#### 算法能力范围

传统视觉能力：

- 滤波降噪
- 直方图均衡和匹配
- 形态学处理
- 阈值分割
- Canny/Sobel/Laplacian/Scharr 边缘检测
- Hough 直线/圆检测
- DoG/LoG 斑点检测
- LBP/GLCM/Gabor 纹理分析
- 轮廓分析和几何测量
- 相机标定和畸变校正
- 模板匹配和亚像素定位

深度学习能力：

- YOLO 系列目标检测
- 语义分割和实例分割
- UNet/UNet++/DeepLabV3+/SegFormer 等分割模型
- EfficientAD/PatchCore/PaDiM 等异常检测
- YOLO-OBB 或旋转框检测
- 少样本和零样本辅助策略

部署能力：

- ONNX Runtime
- TensorRT
- OpenVINO
- FP16/INT8 量化
- 模型剪枝和蒸馏
- Jetson、x86 工控机、GPU 服务器等平台选择
- 采集、处理、分选流水线并行

#### 关键设计指标

算法阶段通常需要关注：

- 缺陷检出率
- 误判率
- Recall、Precision、F1
- 单件处理时间
- 融合和检测总耗时
- 小缺陷和低对比缺陷的检测能力
- 未见缺陷的泛化能力
- NG 判定可解释性
- 原图、融合图、热力图和判定记录的可追溯性

#### 对下游的价值

算法 Agent 为整机评审 Agent 提供：

- 检测能力边界
- 指标达成路径
- 部署资源需求
- 推理时延
- 数据集和验证策略
- 风险和降级方案

### 8.6 `06-review` 整机评审 Agent

#### 角色定位

整机评审 Agent 是流水线的最后一环。它不负责重新设计某个子系统，而是从系统集成角度审查 01-05 阶段之间的接口一致性、需求覆盖、风险、测试计划和是否可进入下一阶段。

#### 上游输入

整机评审 Agent 应汇总前面所有阶段的输出：

- `01-pm` 产品规格书
- `02-mechanical` 机械结构方案
- `03-optics` 光学方案
- `04-motion` 运动控制方案
- `05-algorithm` 算法方案

当前流水线配置中，`06-review` 的直接上游是 `05-algorithm`。如果需要完整整机评审，建议在 `05-algorithm` 输出中保留前序关键约束，或者扩展 `06-review` 的 `upstream` 列表，让它直接读取 01-05 全部文档。

#### 核心能力

- 接口一致性审查
- 规格追踪矩阵设计
- 跨子系统风险识别
- FMEA 风险评估
- FAT/SAT 集成测试计划设计
- 安全、电气、光源、合规性审查
- 评审结论输出

#### 输出文档

整机评审 Agent 输出 `06-review-方案.md`，主要包括：

1. 接口一致性审查报告
2. 规格追踪矩阵
3. 风险评估报告
4. 集成测试计划
5. 合规审查报告
6. 评审结论

#### 关键审查点

整机评审阶段通常关注：

- PM 需求是否被后续 Agent 完整覆盖
- 后续方案是否降低了原始指标
- 机械安装空间是否满足光学设计
- 光学曝光和运动时序是否匹配
- 编码器分辨率是否支撑算法定位精度
- 算法处理时间是否满足节拍
- 分选动作时间是否满足产线速度
- 光源散热是否影响结构热稳定
- 电气接口、信号电平、通信协议是否一致
- FAT/SAT 测试项是否覆盖关键风险

#### 评审结论类型

评审 Agent 最终应给出明确结论：

| 结论 | 含义 |
| --- | --- |
| 通过 | 当前方案可进入下一阶段 |
| 有条件通过 | 可以推进，但必须关闭指定问题 |
| 不通过 | 存在关键缺陷，需要返回前序阶段重做 |

## 9. 推荐工作流程

### 9.1 初始项目流程

```text
1. pipeline check
2. pipeline new <project-name>
3. 人工补充 01-pm 的真实客户需求和产品约束
4. pipeline run <project-name> --agent 01-pm
5. 人工评审并修订 01-pm-方案.md
6. pipeline run <project-name> --from 02-mechanical
7. 逐阶段评审每个 Agent 输出
8. 最终检查 06-review-方案.md
```

### 9.2 推荐的人机协作方式

不要把流水线当成一次性全自动生成工具。更稳妥的做法是：

1. 先让 `01-pm` 生成产品规格初稿。
2. 人工补全缺失的客户、样件、产线和验收信息。
3. 再运行 `02-mechanical`。
4. 人工检查机械方案是否符合现场约束。
5. 再运行 `03-optics`。
6. 按阶段向下推进。
7. 最后由 `06-review` 做跨系统评审。

这样能避免早期需求不清导致后面所有 Agent 产生连锁偏差。

### 9.3 修改上游后的重跑策略

如果修改了某个阶段的输出，需要从它的下游重新运行。

示例：

```text
修改 02-mechanical-方案.md
  -> 重新运行 03-optics
  -> 重新运行 04-motion
  -> 重新运行 05-algorithm
  -> 重新运行 06-review
```

命令：

```powershell
pipeline run <project-name> --from 03-optics
```

## 10. 质量控制清单

### 10.1 运行前检查

- `pipeline check` 无报错
- `pipeline config-show` 中 provider 和 model 正确
- 环境变量 `ANTHROPIC_API_KEY` 已配置
- 项目目录存在
- 上游文档存在且内容不是空模板
- `pipeline.yaml` 中 `output_dir` 与实际输出目录一致

### 10.2 每阶段输出检查

每个 Agent 输出后都建议人工检查：

- 是否按模板章节完整输出
- 是否保留了模板占位符
- 是否出现明显幻觉参数
- 是否引用了上游关键约束
- 是否给出量化指标
- 是否说明了无法确定的信息
- 是否给出可测试、可验证的结论

### 10.3 最终评审检查

最终交付前建议重点检查：

- 所有 PM 需求是否被追踪
- 检测率、误判率、节拍是否前后一致
- 机械、光学、运动、算法是否存在接口冲突
- FAT/SAT 是否覆盖关键风险
- 每个风险是否有责任阶段和缓解措施
- 评审结论是否明确

## 11. 扩展新 Agent 的方法

如果要新增一个 Agent，例如 `07-cost` 成本评估 Agent，建议按以下步骤：

1. 在 `agents/` 下新增目录：

```text
agents/07-cost/
```

2. 创建 3 个文件：

```text
agent.md
template.md
checklist.md
```

3. 在 `agent.md` frontmatter 中定义：

```yaml
---
id: "07-cost"
name: "cost"
title: "成本评估Agent"
role: "设备成本评估工程师"
upstream: ["06-review"]
downstream: []
outputs:
  - "成本估算报告"
---
```

4. 修改上一个 Agent 的 `downstream`，保持上下游互认。

5. 执行：

```powershell
pipeline check
```

6. 通过后即可参与流水线。

注意：当前流水线顺序由 Agent ID 排序决定，所以目录和 `id` 应使用 `NN-name` 格式。

## 12. 常见问题

### 12.1 `pipeline run` 报 provider 不支持

原因：

- `pipeline.yaml` 中配置了非 `anthropic` provider。

解决：

- 改回：

```yaml
model:
  provider: anthropic
```

或在 `core/runner.py` 中实现新的 provider client。

### 12.2 运行某个 Agent 时提示 Agent not found

原因：

- 传入的 Agent ID 不存在。
- Agent ID 必须是完整 ID，例如 `03-optics`，不能只写 `optics`。

正确示例：

```powershell
pipeline run demo --agent 03-optics
```

### 12.3 下游生成质量差

常见原因：

- 上游文档仍是空模板。
- 上游文档缺少关键量化参数。
- 上游文档出现冲突指标。
- 只运行了中间 Agent，但前序文档并不完整。

解决建议：

- 先人工修订上游文档。
- 从受影响的下游 Agent 重新运行。
- 使用 `06-review` 检查接口一致性。

### 12.4 `uv run` 无法执行

如果出现类似 `Failed to initialize cache` 的错误，通常是本地 `uv` 缓存目录异常。可先修复本机 uv cache，或临时使用已有 Python 环境运行测试和 CLI。

这属于本机环境问题，不是 Agent 流水线逻辑问题。

## 13. 当前限制

当前项目仍有一些边界需要注意：

- 只实现了 Anthropic provider。
- `06-review` 默认只直接读取 `05-algorithm` 输出，若要完整读取 01-05，需要调整 `upstream`。
- 单 Agent 运行时，如果上游文档缺失，当前不会强制失败。
- Agent 输出质量依赖上游文档质量。
- 框架生成的是方案文档，不直接生成 CAD、PLC 程序或训练好的模型。
- 真实工程项目仍需要工程师复核、计算、仿真、打样和现场验证。

## 14. 建议后续增强

建议后续可以增强以下能力：

1. 让 `06-review` 直接读取 01-05 全部输出。
2. 在 `run_single` 前检查必需上游文件是否存在。
3. 增加 `pipeline graph` 输出 Mermaid 或文本链路图。
4. 增加 `pipeline validate-project <project>` 检查项目文档完整性。
5. 增加 OpenAI 和 DeepSeek provider adapter。
6. 增加每个 Agent 输出后的 checklist 自动评估。
7. 增加 `--dry-run`，只展示将读取和写入哪些文件。
8. 增加 `--no-overwrite`，避免覆盖人工修订文档。
9. 增加项目级状态文件，记录每个 Agent 最近运行时间、token、耗时和是否成功。

## 15. 一句话总结

`agent-pipeline` 的核心价值，是把工业视觉检测设备的复杂方案设计拆成“产品规格、机械结构、光学系统、运动控制、算法方案、整机评审”六个可管理、可追踪、可重跑的专业阶段，让 LLM 参与工程文档协作时不再是一团散文，而是一条有接口、有模板、有校验、有评审的设计流水线。
