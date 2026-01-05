# 新频道开发指南

本指南详细说明如何在 VisionAgent 系统中添加新的应用频道（如微信、抖音、微博等）。

## 文档索引

| 文档 | 说明 |
|------|------|
| [01-architecture.md](./01-architecture.md) | 系统架构总览，核心组件和处理流程 |
| [02-workflow-system.md](./02-workflow-system.md) | 工作流系统（核心），简单/复杂任务处理策略 |
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

```
用户任务
    │
    ├─ 简单任务（单一动作）
    │   └─ 规则匹配 → 预设工作流
    │
    └─ 复杂任务（多步骤/含连接词）
        └─ LLM 分析 → 选择/组合工作流
```

### 工作流优先级

1. **预设工作流优先**：可靠性高，执行快
2. **LLM 规划回退**：处理未预设的任务
3. **AI 辅助恢复**：执行中断时的智能恢复

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
