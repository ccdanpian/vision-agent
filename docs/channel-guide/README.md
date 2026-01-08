# 新频道开发指南

本指南详细说明如何在 VisionAgent 系统中添加新的应用频道（如微信、抖音、微博等）。

## 启动命令

```bash
# 1. 查看手机信息（默认任务）
python run.py
python run.py -d emulator-5554
python run.py --device 192.168.1.100:5555

# 2. 执行单个任务
python run.py -t "打开微信"
python run.py -t "给张三发消息说你好"
python run.py -t "发朋友圈今天天气真好"

# 3. SS 快速模式（极速执行，推荐）
python run.py -t "ss:张三:你好"           # 发消息
python run.py -t "ss:朋友圈:今天真开心"    # 发朋友圈

# 4. 交互式模式（推荐，支持连续执行）
python run.py -i
python run.py --interactive
python run.py -d emulator-5554 -i

# 5. 其他命令
python run.py --list          # 列出已连接设备
python run.py --modules       # 查看可用模块
python run.py --screenshot output.png  # 截图保存
```

### 交互式模式说明

交互式模式启动后会提示选择运行模式：

```
请选择模式:
  [1] SS快速模式 - 固定格式，极速执行（推荐）
  [2] LLM智能模式 - 自然语言，AI理解
```

- **模式1（SS快速模式）**：使用 `联系人:内容` 或 `朋友圈:内容` 格式
- **模式2（LLM智能模式）**：直接输入自然语言描述

### 环境配置

在 `.env` 文件中配置：

```bash
# 默认设备
DEFAULT_DEVICE=emulator-5554

# 任务分类器模式：regex（默认）或 llm
TASK_CLASSIFIER_MODE=regex

# LLM 配置
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your-api-key
```

## 文档索引

| 文档 | 说明 |
|------|------|
| [01-architecture.md](./01-architecture.md) | 系统架构总览，核心组件和处理流程 |
| [02-workflow-system.md](./02-workflow-system.md) | 工作流系统（核心），任务分类器与工作流处理策略 |
| [03-handler.md](./03-handler.md) | Handler 实现，工作流选择与执行入口 |
| [04-workflow-executor.md](./04-workflow-executor.md) | 工作流执行器，界面检测与导航 |
| [05-reference-images.md](./05-reference-images.md) | 参考图片管理，命名规范与别名系统 |
| [06-development-guide.md](./06-development-guide.md) | 开发步骤详解，最佳实践与常见问题 |

## 代码模板

| 模板 | 说明 |
|------|------|
| [templates/workflows.py](./templates/workflows.py) | 工作流定义模板，包含界面枚举和工作流结构 |
| [templates/handler.py](./templates/handler.py) | Handler 处理器模板 |
| [templates/workflow_executor.py](./templates/workflow_executor.py) | 工作流执行器模板 |
| [templates/config.yaml](./templates/config.yaml) | 频道配置文件模板 |
| [templates/aliases.yaml](./templates/aliases.yaml) | 参考图别名配置模板 |

## 快速开始

```bash
# 1. 复制模板到新频道目录
cp -r docs/channel-guide/templates apps/{channel_name}

# 2. 重命名模板文件
cd apps/{channel_name}
mv templates/workflows.py workflows.py
mv templates/handler.py handler.py
mv templates/workflow_executor.py workflow_executor.py
mv templates/config.yaml config.yaml
mv templates/aliases.yaml images/aliases.yaml
rm -rf templates

# 3. 修改模板中的占位符
# 将 {Channel} 替换为实际频道名（如 Douyin, Weibo）
# 将 {channel} 替换为小写名称（如 douyin, weibo）

# 4. 创建必要的子目录
mkdir -p images/{contacts,system} prompts
touch __init__.py

# 5. 准备参考图和提示词
```

## 核心概念

### 任务分类

系统使用可配置的任务分类器自动判断任务类型：

```
用户任务
    │
    ├─ 简单任务（单一动作）
    │   └─ 规则匹配 → 预设工作流
    │
    └─ 复杂任务（多步骤/含连接词）
        └─ LLM 分析 → 选择/组合工作流
```

**任务分类器支持三种模式**：

1. **SS 快速模式**（自动检测）
   - ⚡ 极速响应（<10ms），零成本
   - ✅ 100%准确率，固定格式
   - 触发：任务以 `ss` 开头
   - 示例：`ss:消息:张三:你好`
   - 详见：[SS 快速模式使用指南](../SS_QUICK_MODE.md)

2. **正则表达式模式**（默认）
   - ✅ 零成本，快速响应
   - ✅ 准确率约90%
   - 配置：`TASK_CLASSIFIER_MODE=regex`

3. **LLM 智能模式**
   - ✅ 准确率约95%
   - ✅ 支持独立模型配置（可用更便宜的模型）
   - ✅ 同时解析任务参数
   - ✅ 识别无效输入（invalid 类型）
   - 配置：`TASK_CLASSIFIER_MODE=llm`
   - 详见：[无效输入处理](../INVALID_INPUT_HANDLING.md)

详见 [02-workflow-system.md](./02-workflow-system.md#任务分类器taskclassifier)

### 工作流路由优先级

```
1. parsed_data.type 存在 → type 映射路由（最高优先级，SS模式/LLM模式）
2. task_type == COMPLEX → LLM 选择工作流
3. 其他 → 规则匹配（兼容旧逻辑）
```

### 任务执行流程

```
预置准备 → 执行任务 → 返回结果 → 复位清理
    │          │          │          │
    │          │          │          └─ 自动返回首页（try-finally）
    │          │          └─ 成功/失败结果
    │          └─ 步骤重试（最多N次）
    └─ 确保应用在前台，导航到首页
```

**关键特性**：
- **预置流程容错**：预置失败不阻断正式任务
- **步骤自动重试**：失败后最多重试3次，每次尝试恢复
- **任务完成后复位**：无论成功失败，都自动返回首页

### 参考图分类

| 类型 | 目录 | 用途 |
|------|------|------|
| 点击操作图 | `images/` | 定位可点击元素 |
| 界面验证图 | `images/system/` | 验证当前页面 |
| 联系人图 | `images/contacts/` | 识别联系人 |

## 新频道目录结构

新频道需要在 `apps/` 下创建以下结构：

```
apps/{channel_name}/
├── __init__.py                   # 模块初始化（可为空）
├── config.yaml                   # 频道配置（必需）
├── handler.py                    # 主处理器（推荐自定义）
├── workflows.py                  # 工作流定义（推荐）
├── workflow_executor.py          # 工作流执行器（推荐）
├── tasks.yaml                    # 简单任务模板（可选）
├── images/                       # 参考图目录
│   ├── aliases.yaml              # 中文别名映射
│   ├── {channel}_*.png           # 点击操作参考图
│   ├── {channel}_*_v1.png        # 变体版本（多设备适配）
│   ├── contacts/                 # 联系人等动态图片
│   │   └── {contact_name}.png
│   └── system/                   # 界面状态验证图
│       └── {channel}_*_page.png
└── prompts/                      # AI提示词目录
    └── planner.txt               # 规划器提示词
```

## 参考实现

微信频道是完整的参考实现，位于 `apps/wechat/` 目录：

```
apps/wechat/
├── config.yaml           # 频道配置
├── handler.py            # 主处理器
├── workflows.py          # 工作流定义
├── workflow_executor.py  # 工作流执行器
├── images/
│   ├── aliases.yaml      # 中文别名
│   ├── wechat_*.png      # 操作元素参考图
│   ├── contacts/         # 联系人参考图
│   └── system/           # 界面验证参考图
└── prompts/
    └── planner.txt       # 规划器提示词
```

## 工作流配置参数

在 `config.py` 中统一配置工作流执行参数：

```python
# config.py - 工作流执行配置
WORKFLOW_MAX_STEP_RETRIES = 3        # 步骤最大重试次数
WORKFLOW_MAX_BACK_PRESSES = 5        # 返回键最多按压次数
WORKFLOW_BACK_PRESS_INTERVAL = 500   # 返回键按压间隔 (ms)
WORKFLOW_HOME_MAX_ATTEMPTS = 5       # 确保在首页/导航到首页的最大尝试次数
WORKFLOW_AI_FALLBACK_ATTEMPTS = 3    # AI回退最大尝试次数
WORKFLOW_RECOVER_NAV_ATTEMPTS = 3    # 恢复时导航到首页的尝试次数
```

详见 [04-workflow-executor.md](./04-workflow-executor.md#配置参数)
