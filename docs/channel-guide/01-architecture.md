# 系统架构总览

## 核心处理流程

```
用户输入任务
     │
     ▼
┌────────────────────────────────────┐
│         ModuleRegistry.route()      │  ← 1. 频道识别与路由
│  根据关键词匹配分数选择合适的Handler  │
└────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────┐
│        Handler.set_task_runner()    │  ← 2. 绑定执行器
│  建立Handler与TaskRunner的关联      │
└────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────┐
│     execute_task_with_workflow()    │  ← 3. 工作流优先
│  ├─ is_complex_task()? ─────────┐  │
│  │       │是                   │否 │
│  │       ▼                     ▼   │
│  │  select_workflow_with_llm()  match_workflow()
│  │  (LLM选择预设工作流)         (规则匹配)
│  └──────────────────────────────────┘
└────────────────────────────────────┘
     │ 无匹配或参数不完整
     ▼
┌────────────────────────────────────┐
│         AI Planner 规划             │  ← 4. AI规划（回退方案）
│  使用增强提示词 + 预设工作流参考     │
└────────────────────────────────────┘
     │
     ▼
┌────────────────────────────────────┐
│       WorkflowExecutor 执行         │  ← 5. 执行
│  界面检测 → 导航 → 步骤执行 → 验证   │
└────────────────────────────────────┘
```

## 核心组件职责

| 组件 | 文件 | 职责 |
|------|------|------|
| `ModuleRegistry` | `apps/__init__.py` | 模块发现、注册、任务路由 |
| `TaskClassifier` | `ai/task_classifier.py` | 任务分类（简单/复杂），支持正则/LLM模式 |
| `Handler` | `apps/{channel}/handler.py` | 频道入口，工作流选择与执行 |
| `Workflows` | `apps/{channel}/workflows.py` | 预设工作流定义、任务匹配规则 |
| `WorkflowExecutor` | `apps/{channel}/workflow_executor.py` | 工作流执行、界面检测、导航 |
| `Planner` | `ai/planner.py` | AI任务规划，步骤分解 |
| `TaskRunner` | `core/task_runner.py` | 任务调度，步骤执行与验证 |
| `HybridLocator` | `core/hybrid_locator.py` | 混合定位（OpenCV + AI） |
| `ModuleAssets` | `apps/base.py` | 参考图、提示词资源管理 |

## 目录结构

新频道需要在 `apps/` 下创建以下结构：

```
apps/
└── {channel_name}/                   # 频道目录，如 douyin, weibo
    ├── __init__.py                   # 模块初始化（可为空）
    ├── config.yaml                   # 频道配置（必需）
    ├── handler.py                    # 主处理器（推荐自定义）
    ├── workflows.py                  # 工作流定义（推荐）
    ├── workflow_executor.py          # 工作流执行器（推荐）
    ├── tasks.yaml                    # 简单任务模板（可选）
    ├── images/                       # 参考图目录
    │   ├── aliases.yaml              # 中文别名映射
    │   ├── {channel}_*.png           # 界面元素参考图
    │   ├── {channel}_*_v1.png        # 变体版本（多设备适配）
    │   ├── contacts/                 # 联系人等动态图片
    │   │   └── {contact_name}.png
    │   └── system/                   # 界面状态验证图
    │       └── {channel}_*_page.png
    └── prompts/                      # AI提示词目录
        └── planner.txt               # 规划器提示词
```

## 频道识别与任务路由

### 任务匹配算法

以下是 `apps/base.py` 中 `AppHandler.match_task()` 的实际实现：

```python
# apps/base.py - AppHandler.match_task() 实际代码

def match_task(self, task: str) -> float:
    """
    计算任务与本模块的匹配度

    Args:
        task: 任务描述

    Returns:
        0.0 - 1.0 的匹配得分
    """
    score = 0.0
    task_lower = task.lower()

    # 1. 任务模板匹配 (最高优先级，权重 0.5)
    template_matched = False
    for template in self.tasks:
        for pattern in template.patterns:
            try:
                if re.search(pattern, task, re.IGNORECASE):
                    score += 0.5
                    template_matched = True
                    break
            except re.error:
                continue
        if template_matched:
            break

    # 2. 关键词匹配 (权重 0.4)
    # 使用命中数而非比例，每个命中加 0.1，最多 0.4
    keyword_hits = 0
    for keyword in self.module_info.keywords:
        keyword_lower = keyword.lower()
        # 检查是否为正则表达式模式（包含 . * + ? 等）
        if any(c in keyword for c in '.*+?[]()'):
            try:
                if re.search(keyword_lower, task_lower):
                    keyword_hits += 1
            except re.error:
                pass
        elif keyword_lower in task_lower:
            keyword_hits += 1
            # 完全匹配给更高分
            if keyword_lower == task_lower:
                keyword_hits += 2

    if keyword_hits > 0:
        keyword_score = min(keyword_hits * 0.1, 0.4)
        score += keyword_score

    # 3. 包名匹配 (权重 0.1)
    if self.module_info.package:
        if self.module_info.package.lower() in task_lower:
            score += 0.1

    return min(score, 1.0)
```

### 匹配权重说明

| 匹配类型 | 权重 | 说明 |
|----------|------|------|
| 任务模板 | 0.5 | 最高优先级，精确匹配预定义任务 |
| 关键词 | 0.4 | 每个命中 +0.1，最多 0.4 |
| 包名 | 0.1 | 任务中包含应用包名 |

### config.yaml 配置示例

```yaml
# apps/wechat/config.yaml
name: wechat
display_name: 微信
package: com.tencent.mm
keywords:
  - 微信
  - wechat
  - 聊天
  - 朋友圈
  - 发消息
  - 通讯录
description: 微信即时通讯应用
```
