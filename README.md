# VisionAgent - AI 驱动的手机自动化控制系统

VisionAgent 是一个基于视觉理解的手机自动化控制系统，通过 ADB 连接手机，使用 AI 视觉模型理解屏幕内容并执行任务。

## 特性

- **AI 视觉理解**：使用 Claude/OpenAI 等大模型理解手机屏幕
- **预设工作流**：常见任务使用预设工作流，快速可靠
- **SS 快速模式**：固定格式输入，极速执行（<10ms 解析）
- **智能回退**：预设工作流失败时自动切换 AI 规划
- **多频道支持**：支持微信、抖音等多个应用
- **自动复位**：任务完成后自动返回首页

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/yourname/vision-agent.git
cd vision-agent

# 安装依赖
pip install -r requirements.txt

# 复制配置文件
cp .env.example .env
```

### 2. 配置 .env

```bash
# 设备配置
DEFAULT_DEVICE=emulator-5554

# LLM 配置（选择一个）
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your-api-key

# 或使用 OpenAI
# LLM_PROVIDER=openai
# OPENAI_API_KEY=your-api-key

# 任务分类器模式：regex（默认）或 llm
TASK_CLASSIFIER_MODE=regex
```

### 3. 连接设备

```bash
# 查看已连接设备
python run.py --list

# 连接无线设备
adb connect 192.168.1.100:5555
```

### 4. 运行

```bash
# 交互式模式（推荐）
python run.py -i

# 执行单个任务
python run.py -t "给张三发消息说你好"

# SS 快速模式
python run.py -t "ss:张三:你好"
```

## 使用方式

### 交互式模式

```bash
python run.py -i
```

启动后选择运行模式：

```
请选择模式:
  [1] SS快速模式 - 固定格式，极速执行（推荐）
  [2] LLM智能模式 - 自然语言，AI理解
```

### SS 快速模式格式

```bash
# 发送消息
ss:联系人:消息内容
ss:张三:你好

# 发朋友圈
ss:朋友圈:内容
ss:朋友圈:今天天气真好
```

### 命令行参数

```bash
python run.py [选项]

选项：
  -d, --device DEVICE    指定设备（如 emulator-5554）
  -t, --task TASK        执行单个任务
  -i, --interactive      交互式模式
  --list                 列出已连接设备
  --modules              查看可用模块
  --screenshot FILE      截图保存到文件
```

## 项目结构

```
vision-agent/
├── run.py                    # 主入口
├── config.py                 # 配置文件
├── .env                      # 环境变量（API Key等）
├── requirements.txt          # Python 依赖
│
├── ai/                       # AI 模块
│   ├── vision_agent.py       # 视觉理解代理
│   ├── planner.py            # 任务规划器
│   └── task_classifier.py    # 任务分类器
│
├── core/                     # 核心模块
│   ├── adb_controller.py     # ADB 控制器
│   ├── task_runner.py        # 任务执行器
│   └── hybrid_locator.py     # 混合定位器
│
├── apps/                     # 应用频道
│   ├── base.py               # 基类
│   ├── wechat/               # 微信频道（参考实现）
│   │   ├── handler.py
│   │   ├── workflows.py
│   │   ├── workflow_executor.py
│   │   └── images/
│   └── system/               # 系统频道
│
└── docs/                     # 文档
    └── channel-guide/        # 新频道开发指南
```

## 配置说明

### 工作流执行配置

在 `config.py` 中：

```python
WORKFLOW_MAX_STEP_RETRIES = 3        # 步骤最大重试次数
WORKFLOW_MAX_BACK_PRESSES = 5        # 返回键最多按压次数
WORKFLOW_BACK_PRESS_INTERVAL = 500   # 返回键间隔 (ms)
WORKFLOW_HOME_MAX_ATTEMPTS = 5       # 导航到首页最大尝试次数
WORKFLOW_AI_FALLBACK_ATTEMPTS = 3    # AI 回退尝试次数
```

### LLM 配置

支持多种 LLM 提供商：

```bash
# Claude (Anthropic)
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your-key
CLAUDE_MODEL=claude-sonnet-4-20250514

# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4o

# 自定义 API（OpenAI 兼容）
LLM_PROVIDER=custom
CUSTOM_LLM_API_KEY=your-key
CUSTOM_LLM_BASE_URL=https://api.example.com/v1
CUSTOM_LLM_MODEL=model-name
```

## 任务执行流程

```
用户输入
    │
    ▼
┌─────────────────┐
│  任务分类器      │  SS模式 / 正则 / LLM
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  工作流路由      │  type映射 → 预设工作流
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  预置流程        │  启动应用，确保在首页
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  执行步骤        │  失败自动重试（最多3次）
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  复位清理        │  自动返回首页
└─────────────────┘
```

## 开发新频道

参见 [新频道开发指南](docs/channel-guide/README.md)

```bash
# 快速开始
cp -r docs/channel-guide/templates apps/your_channel
cd apps/your_channel
# 修改模板中的占位符...
```

## 相关文档

| 文档 | 说明 |
|------|------|
| [新频道开发指南](docs/channel-guide/README.md) | 添加新应用频道的完整指南 |
| [SS 快速模式](docs/SS_QUICK_MODE.md) | SS 模式使用说明 |
| [调试模式](docs/DEBUG_MODE.md) | 无设备时的调试方法 |
| [交互模式](docs/INTERACTIVE_MODE.md) | 交互式模式说明 |

## 许可证

MIT License
