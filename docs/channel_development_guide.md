# 新频道开发指南

本文档详细说明如何在 VisionAgent 系统中添加新的应用频道（如微信、抖音、微博等）。

## 目录

1. [概述](#概述)
2. [目录结构](#目录结构)
3. [核心文件详解](#核心文件详解)
4. [开发步骤](#开发步骤)
5. [参考图管理](#参考图管理)
6. [工作流系统](#工作流系统)
7. [最佳实践](#最佳实践)

---

## 概述

### 系统架构

```
用户指令 → 任务分发器 → 频道Handler → AI规划器/工作流执行器 → 设备操作
```

### 核心组件

| 组件 | 职责 |
|------|------|
| `Handler` | 频道入口，处理任务分发和规划 |
| `Workflows` | 预定义工作流，处理常见任务 |
| `WorkflowExecutor` | 执行工作流，处理屏幕检测和导航 |
| `ModuleAssets` | 资源管理（图片、提示词、别名） |
| `config.yaml` | 频道元数据和关键词配置 |

---

## 目录结构

新频道需要在 `apps/` 下创建以下结构：

```
apps/
└── {channel_name}/           # 频道目录，如 douyin, weibo
    ├── __init__.py           # 模块初始化
    ├── handler.py            # 主处理器（必需）
    ├── config.yaml           # 频道配置（必需）
    ├── workflows.py          # 工作流定义（可选）
    ├── workflow_executor.py  # 工作流执行器（可选）
    ├── images/               # 参考图目录
    │   ├── aliases.yaml      # 中文别名映射
    │   ├── contacts/         # 联系人头像等动态图片
    │   ├── system/           # 系统级参考图
    │   └── *.png             # 界面元素参考图
    └── prompts/              # AI提示词目录
        └── planner.txt       # 规划器提示词
```

---

## 核心文件详解

### 1. config.yaml - 频道配置

```yaml
# apps/{channel}/config.yaml

name: 微信              # 频道显示名称（中文）
package: com.tencent.mm  # Android包名，用于启动应用
keywords:               # 任务匹配关键词列表
  - 发微信
  - 发消息
  - 朋友圈
  - 加好友
  - 微信支付

# 可选：工作流相关配置
workflow_timeout: 60     # 工作流超时时间（秒）
max_retry: 3            # 最大重试次数
```

**关键词设计原则：**
- 包含用户可能使用的所有相关动词短语
- 覆盖主要功能场景
- 避免与其他频道关键词重叠

### 2. handler.py - 主处理器

#### 最简实现（继承 DefaultHandler）

```python
# apps/{channel}/handler.py

from apps.base import DefaultHandler

class Handler(DefaultHandler):
    """频道处理器 - 最简实现"""
    pass  # 直接使用基类的AI规划功能
```

#### 完整实现（带工作流支持）

```python
# apps/{channel}/handler.py

from typing import Optional
from apps.base import DefaultHandler
from .workflow_executor import WorkflowExecutor
from .workflows import match_workflow, is_complex_task

class Handler(DefaultHandler):
    """频道处理器 - 完整实现"""

    def __init__(self, context):
        super().__init__(context)
        self.workflow_executor = WorkflowExecutor(context, self.assets)

    async def plan(self, task: str) -> str:
        """
        任务规划入口

        处理流程：
        1. 尝试匹配预定义工作流
        2. 匹配成功 → 执行工作流
        3. 匹配失败或复杂任务 → 调用AI规划器
        """
        # 尝试工作流匹配
        workflow = match_workflow(task)

        if workflow and not is_complex_task(task):
            # 执行预定义工作流
            result = await self.execute_task_with_workflow(task, workflow)
            if result:
                return result

        # 回退到AI规划
        return await super().plan(task)

    async def execute_task_with_workflow(
        self,
        task: str,
        workflow
    ) -> Optional[str]:
        """执行工作流任务"""
        success, message = await self.workflow_executor.execute_workflow(
            workflow=workflow,
            task_params=self._extract_params(task)
        )
        return message if success else None

    def _extract_params(self, task: str) -> dict:
        """从任务描述中��取参数"""
        # 实现参数提取逻辑
        return {}

    def get_planner_prompt(self) -> str:
        """获取AI规划器提示词"""
        base_prompt = super().get_planner_prompt()
        # 可以追加频道特定的提示信息
        return base_prompt
```

### 3. workflows.py - 工作流定义

```python
# apps/{channel}/workflows.py

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import re

# 屏幕状态枚举
class ScreenState(Enum):
    """应用界面状态"""
    HOME = "home"           # 主页
    CHAT = "chat"           # 聊天界面
    PROFILE = "profile"     # 个人页面
    SETTINGS = "settings"   # 设置页面
    UNKNOWN = "unknown"     # 未知状态

# 导航步骤
@dataclass
class NavStep:
    """单个导航步骤"""
    action: str             # 动作类型: tap, input, swipe, wait
    target: str             # 目标元素（参考图名或文字）
    value: Optional[str] = None  # 输入值或参数
    description: str = ""   # 步骤描述（用于日志）

# 工作流定义
@dataclass
class Workflow:
    """完整工作流"""
    name: str               # 工作流名称
    description: str        # 工作流描述
    start_screen: ScreenState  # 起始屏幕要求
    steps: List[NavStep]    # 步骤列表
    success_indicator: str = ""  # 成功标识（参考图）
    params: List[str] = field(default_factory=list)  # 需要的参数

# 工作流注册表
WORKFLOWS: Dict[str, Workflow] = {
    "send_message": Workflow(
        name="发送消息",
        description="向联系人发送文字消息",
        start_screen=ScreenState.HOME,
        params=["contact", "message"],
        steps=[
            NavStep("tap", "search_button", description="点击搜索"),
            NavStep("input", "search_input", "{contact}", "输入联系人"),
            NavStep("tap", "contact_item", description="选择联系人"),
            NavStep("input", "chat_input", "{message}", "输入消息"),
            NavStep("tap", "send_button", description="点击发送"),
        ],
        success_indicator="message_sent"
    ),
    # 添加更多工作流...
}

# 简单任务模式匹配
SIMPLE_TASK_PATTERNS = {
    r"发.*消息": "send_message",
    r"发朋友圈": "post_moments",
    r"加.*好友": "add_friend",
}

def match_workflow(task: str) -> Optional[Workflow]:
    """根据任务描述匹配工作流"""
    for pattern, workflow_name in SIMPLE_TASK_PATTERNS.items():
        if re.search(pattern, task):
            return WORKFLOWS.get(workflow_name)
    return None

def is_complex_task(task: str) -> bool:
    """判断是否为复杂任务（需要AI规划）"""
    complex_indicators = [
        "如果", "假如",    # 条件判断
        "然后", "接着",    # 多步骤
        "检查", "确认",    # 验证操作
        "所有", "每个",    # 批量操作
    ]
    return any(ind in task for ind in complex_indicators)
```

### 4. workflow_executor.py - 工作流执行器

```python
# apps/{channel}/workflow_executor.py

import asyncio
from typing import Tuple, Dict, Any, Optional
from .workflows import Workflow, NavStep, ScreenState

class WorkflowExecutor:
    """工作流执行引擎"""

    def __init__(self, context, assets):
        self.context = context
        self.assets = assets
        self.device = context.device
        self.locator = context.locator  # HybridLocator实例

    async def execute_workflow(
        self,
        workflow: Workflow,
        task_params: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        执行工作流

        Returns:
            (success, message) 元组
        """
        try:
            # 1. 确保应用运行
            await self._ensure_app_running()

            # 2. 检测当前屏幕
            current_screen = await self.detect_screen()

            # 3. 导航到起始屏幕（如需要）
            if current_screen != workflow.start_screen:
                await self.navigate_to_screen(workflow.start_screen)

            # 4. 执行工作流步骤
            for step in workflow.steps:
                success = await self._execute_step(step, task_params)
                if not success:
                    return False, f"步骤失败: {step.description}"
                await asyncio.sleep(0.5)  # 步骤间延迟

            # 5. 验证成功
            if workflow.success_indicator:
                if not await self._verify_success(workflow.success_indicator):
                    return False, "未能确认操作成功"

            return True, f"{workflow.name}执行成功"

        except Exception as e:
            return False, f"执行异常: {str(e)}"

    async def _ensure_app_running(self):
        """确保应用正在运行"""
        package = self.assets.module_info.package
        # 检查当前应用
        current = await self.device.get_current_package()
        if current != package:
            await self.device.launch_app(package)
            await asyncio.sleep(2)

    async def detect_screen(self) -> ScreenState:
        """检测当前屏幕状态"""
        screenshot = await self.device.screenshot()

        # 使用参考图匹配检测屏幕
        screen_indicators = {
            ScreenState.HOME: "home_indicator",
            ScreenState.CHAT: "chat_indicator",
            ScreenState.PROFILE: "profile_indicator",
        }

        for state, ref_image in screen_indicators.items():
            ref_path = self.assets.get_image(ref_image)
            if ref_path:
                result = await self.locator.find(screenshot, ref_path)
                if result and result.confidence > 0.7:
                    return state

        return ScreenState.UNKNOWN

    async def navigate_to_screen(self, target: ScreenState):
        """导航到目标屏幕"""
        # 实现导航逻辑，通常先返回主页再导航
        await self.navigate_to_home()
        # 根据target执行相应导航

    async def navigate_to_home(self):
        """返回主页"""
        max_attempts = 5
        for _ in range(max_attempts):
            screen = await self.detect_screen()
            if screen == ScreenState.HOME:
                return
            # 点击返回按钮
            back_ref = self.assets.get_image("back_button")
            if back_ref:
                result = await self.locator.find(
                    await self.device.screenshot(),
                    back_ref
                )
                if result:
                    await self.device.tap(result.x, result.y)
                    await asyncio.sleep(0.5)

    async def _execute_step(
        self,
        step: NavStep,
        params: Dict[str, Any]
    ) -> bool:
        """执行单个步骤"""
        # 替换参数占位符
        target = step.target
        value = step.value
        if value:
            for key, val in params.items():
                value = value.replace(f"{{{key}}}", str(val))

        screenshot = await self.device.screenshot()

        if step.action == "tap":
            return await self._do_tap(screenshot, target)
        elif step.action == "input":
            return await self._do_input(screenshot, target, value)
        elif step.action == "swipe":
            return await self._do_swipe(step.value)
        elif step.action == "wait":
            await asyncio.sleep(float(step.value or 1))
            return True

        return False

    async def _do_tap(self, screenshot, target: str) -> bool:
        """执行点击操作"""
        # 优先使用参考图
        ref_path = self.assets.get_image(target)
        if ref_path:
            result = await self.locator.find(screenshot, ref_path)
            if result and result.confidence > 0.6:
                await self.device.tap(result.x, result.y)
                return True

        # 回退到文字识别
        result = await self.locator.find_by_text(screenshot, target)
        if result:
            await self.device.tap(result.x, result.y)
            return True

        return False

    async def _do_input(self, screenshot, target: str, text: str) -> bool:
        """执行输入操作"""
        # 先点击输入框
        if not await self._do_tap(screenshot, target):
            return False
        await asyncio.sleep(0.3)
        # 输入文字
        await self.device.input_text(text)
        return True

    async def _do_swipe(self, direction: str) -> bool:
        """执行滑动操作"""
        # 实现滑动逻辑
        return True

    async def _verify_success(self, indicator: str) -> bool:
        """验证操作成功"""
        screenshot = await self.device.screenshot()
        ref_path = self.assets.get_image(indicator)
        if ref_path:
            result = await self.locator.find(screenshot, ref_path)
            return result and result.confidence > 0.7
        return True  # 无验证图时默认成功
```

### 5. images/aliases.yaml - 参考图别名

```yaml
# apps/{channel}/images/aliases.yaml

# 格式: 中文别名 -> 英文文件名（不含扩展名）
# 支持子目录，如: 张三 -> contacts/zhangsan

aliases:
  # 主页元素
  首页: home_page
  搜索按钮: search_button
  搜索: search_button        # 支持多个别名指向同一文件

  # 导航
  返回: back_button
  返回按钮: back_button

  # 底部标签
  首页标签: tab_home
  消息标签: tab_messages
  我的标签: tab_profile

  # 聊天界面
  输入框: chat_input
  发送按钮: send_button
  发送: send_button

  # 联系人（子目录）
  张三: contacts/zhangsan
  李四: contacts/lisi
```

### 6. prompts/planner.txt - 规划器提示词

```text
你是一个手机自动化操作专家，负责分析屏幕截图并规划操作步骤。

## 你的任务
分析当前手机屏幕截图，规划完成用户任务所需的操作步骤。

## 可用操作
- tap: 点击屏幕元素
- input: 输入文字
- swipe: 滑动屏幕
- wait: 等待
- back: 返回上一页
- screenshot: 截取屏幕

## 可用参考图
{reference_images}

## 输出格式
返回JSON格式的操作计划：
```json
{
  "analysis": "当前屏幕分析",
  "plan": [
    {"action": "tap", "target": "搜索按钮"},
    {"action": "input", "target": "搜索输入框", "value": "联系人名称"},
    {"action": "tap", "target": "搜索结果"}
  ],
  "expected_result": "预期结果描述"
}
```

## 注意事项
1. 优先使用参考图名称作为target
2. 如果参考图不存在，使用界面上的可见文字
3. 每一步操作后可能需要等待页面加载
4. 遇到弹窗需要先处理弹窗
```

---

## 开发步骤

### 步骤1：创建目录结构

```bash
mkdir -p apps/{channel_name}/{images,prompts}
touch apps/{channel_name}/__init__.py
touch apps/{channel_name}/handler.py
touch apps/{channel_name}/config.yaml
touch apps/{channel_name}/images/aliases.yaml
touch apps/{channel_name}/prompts/planner.txt
```

### 步骤2：配置 config.yaml

1. 设置频道名称和包名
2. 定义关键词列表
3. 配置超时和重试参数

### 步骤3：实现 Handler

**最简实现**：直接继承 `DefaultHandler`，使用AI规划所有任务。

**完整实现**：
1. 定义工作流（workflows.py）
2. 实现工作流执行器（workflow_executor.py）
3. 在Handler中集成工作流

### 步骤4：准备参考图

1. 截取应用界面关键元素
2. 命名规范：`{channel}_{element}[_v{n}].png`
3. 配置 aliases.yaml 中文映射

### 步骤5：编写规划器提示词

1. 描述应用特点和操作方式
2. 列出可用参考图
3. 提供输出格式示例

### 步骤6：注册频道

在 `apps/__init__.py` 中注册：

```python
from .{channel_name}.handler import Handler as {ChannelName}Handler

HANDLERS = {
    "{channel_name}": {ChannelName}Handler,
    # ...
}
```

### 步骤7：测试验证

```bash
python test_planner.py --channel {channel_name} --task "测试任务"
```

---

## 参考图管理

### 命名规范

```
{channel}_{element}[_v{version}].png
```

示例：
- `wechat_home.png` - 微信主页
- `wechat_chat_send.png` - 发送按钮
- `wechat_back_v1.png` - 返回按钮变体1
- `wechat_back_v2.png` - 返回按钮变体2

### 版本变体

同一元素可能有多种外观（如不同主题、状态），使用 `_v{n}` 后缀区分：

```
images/
├── wechat_send.png      # 默认版本
├── wechat_send_v1.png   # 变体1
└── wechat_send_v2.png   # 变体2
```

系统会自动并行匹配所有变体，选择置信度最高的结果。

### 目录组织

```
images/
├── aliases.yaml          # 别名配置
├── {channel}_*.png       # 主界面元素
├── contacts/             # 联系人头像
│   ├── zhangsan.png
│   └── lisi.png
└── system/               # 系统级参考图
    └── notification.png
```

### 别名配置要点

1. **多别名支持**：同一文件可有多个中文别名
2. **子目录支持**：使用 `subdir/filename` 格式
3. **模糊匹配**：系统支持模糊匹配，优先匹配较长的键

---

## 工作流系统

### 何时使用工作流

| 场景 | 推荐方案 |
|------|----------|
| 固定流程任务（如发消息） | 预定义工作流 |
| 简单重复操作 | 简单任务模式匹配 |
| 复杂/动态任务 | AI规划器 |
| 需要条件判断 | AI规划器 |

### 工作流设计原则

1. **原子化步骤**：每个NavStep只做一件事
2. **清晰的参数**：明确定义需要的参数
3. **失败处理**：定义失败后的回退策略
4. **成功验证**：提供成功指示器参考图

### 与AI规划器的配合

```
任务输入
    ↓
工作流匹配 ─────→ 匹配成功 → 执行工作流 → 成功 → 返回结果
    │                              ↓
    │                           失败
    ↓                              ↓
匹配失败 ──────────────────→ AI规划器 → 执行计划 → 返回结果
```

---

## 最佳实践

### 1. 参考图质量

- 截取清晰的界面元素
- 避免包含动态内容（如时间、未读数）
- 保持适当的边距
- 使用代表性的截图

### 2. 工作流健壮性

- 添加适当的等待时间
- 处理可能的弹窗和异常
- 提供失败回退机制
- 验证操作结果

### 3. 提示词优化

- 提供清晰的操作说明
- 列出完整的参考图清单
- 给出典型示例
- 说明特殊情况处理

### 4. 渐进式开发

1. 先用最简Handler验证基本功能
2. 收集常见任务场景
3. 逐步添加工作流
4. 持续优化参考图库

### 5. 调试技巧

- 启用详细日志
- 保存执行过程截图
- 记录匹配置信度
- 分析失败原因

---

## 示例：添加抖音频道

### 1. 目录结构

```
apps/douyin/
├── __init__.py
├── handler.py
├── config.yaml
├── images/
│   ├── aliases.yaml
│   ├── douyin_home.png
│   ├── douyin_search.png
│   └── douyin_publish.png
└── prompts/
    └── planner.txt
```

### 2. config.yaml

```yaml
name: 抖音
package: com.ss.android.ugc.aweme
keywords:
  - 发抖音
  - 刷抖音
  - 抖音搜索
  - 发视频
  - 看直播
```

### 3. handler.py（最简版）

```python
from apps.base import DefaultHandler

class Handler(DefaultHandler):
    """抖音频道处理器"""
    pass
```

### 4. images/aliases.yaml

```yaml
aliases:
  首页: douyin_home
  搜索: douyin_search
  发布: douyin_publish
  我的: douyin_profile
```

---

## 常见问题

### Q: 如何处理需要登录的应用？

A: 在 `_ensure_app_running()` 中检测登录状态，未登录时提示用户或执行登录流程。

### Q: 参考图匹配不准确怎么办？

A:
1. 检查参考图质量
2. 添加多个变体版本
3. 调整匹配置信度阈值
4. 考虑使用文字识别作为补充

### Q: 工作流执行中途失败如何恢复？

A:
1. 返回已知状态（如主页）
2. 重新执行工作流
3. 或回退到AI规划器处理

### Q: 如何支持多语言界面？

A:
1. 为不同语言准备不同的参考图变体
2. 在别名配置中添加多语言映射
3. 或依赖文字识别而非固定文字

---

## 附录：基类API参考

### ModuleAssets

```python
class ModuleAssets:
    module_info: ModuleInfo      # 模块信息

    def get_image(name: str) -> Optional[Path]
        # 获取参考图路径，支持中文别名和模糊匹配

    def get_prompt(name: str) -> str
        # 获取提示词内容

    def list_images() -> List[str]
        # 列出所有可用参考图
```

### DefaultHandler

```python
class DefaultHandler(AppHandler):
    context: Context             # 运行上下文
    assets: ModuleAssets         # 资源管理器

    async def plan(task: str) -> str
        # 规划任务执行

    def get_planner_prompt() -> str
        # 获取AI规划器提示词
```

### HybridLocator

```python
class HybridLocator:
    async def find(screenshot: Image, reference: Path) -> LocateResult
        # 在截图中定位参考图

    async def find_by_text(screenshot: Image, text: str) -> LocateResult
        # 通过文字识别定位元素
```
