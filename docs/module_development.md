# 模块开发指南

本文档介绍如何为 VisionAgent 开发新的应用模块。

## 目录结构

每个模块位于 `apps/` 目录下，遵循以下结构：

```
apps/
├── __init__.py          # 模块注册表
├── base.py              # 基类定义
└── your_module/         # 你的模块目录
    ├── config.yaml      # 模块配置（必需）
    ├── tasks.yaml       # 预定义任务（可选）
    ├── handler.py       # 自定义处理器（可选）
    ├── images/          # 参考图片目录
    │   ├── icon.png
    │   ├── button.png
    │   └── aliases.yaml # 图片别名配置
    └── prompts/         # 提示词模板目录
        └── planner.txt
```

## 快速开始

### 1. 创建模块目录

```bash
mkdir -p apps/myapp/{images,prompts}
```

### 2. 创建 config.yaml

```yaml
# apps/myapp/config.yaml

name: 我的应用
package: com.example.myapp  # 应用包名
version: "1.0.0"
description: |
  我的应用自动化模块
  支持的功能：...

author: Your Name

# 路由关键词（用于任务路由）
keywords:
  - 我的应用
  - myapp
  - 功能1
  - 功能2
```

### 3. 创建 tasks.yaml（可选）

```yaml
# apps/myapp/tasks.yaml

tasks:
  - name: 打开应用
    description: 启动应用
    patterns:
      - "打开我的应用"
      - "启动myapp"
    steps:
      - action: launch_app
        description: 启动应用
        package_name: "com.example.myapp"

  - name: 执行搜索
    description: 搜索内容
    patterns:
      - "(?:在我的应用)?搜索(?P<query>.+)"
    variables:
      - query
    steps:
      - action: launch_app
        description: 打开应用
        package_name: "com.example.myapp"
      - action: wait
        duration: 1.5
      - action: tap
        description: 点击搜索框
        target_ref: "search_box"
      - action: input_text
        description: "输入搜索内容"
        text: "{query}"
      - action: tap
        description: 点击搜索按钮
        target_ref: "search_button"
```

### 4. 添加参考图片

将 UI 元素的截图放入 `images/` 目录：

```
images/
├── search_box.png      # 搜索框
├── search_button.png   # 搜索按钮
├── home_tab.png        # 首页标签
└── aliases.yaml        # 别名配置
```

`aliases.yaml` 示例：

```yaml
aliases:
  搜索框: search_box
  搜索按钮: search_button
  首页: home_tab
```

## 配置详解

### config.yaml 字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| name | string | 是 | 模块显示名称 |
| package | string | 否 | Android 应用包名 |
| version | string | 否 | 模块版本 |
| description | string | 否 | 模块描述 |
| author | string | 否 | 作者 |
| keywords | list | 是 | 路由关键词列表 |

### tasks.yaml 字段

每个任务包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 任务名称 |
| description | string | 任务描述 |
| patterns | list | 正则匹配模式 |
| variables | list | 从正则中提取的变量 |
| steps | list | 执行步骤列表 |

### 可用的动作类型

| 动作 | 说明 | 参数 |
|------|------|------|
| tap | 点击元素 | target_ref |
| long_press | 长按元素 | target_ref, duration |
| swipe | 滑动屏幕 | direction (up/down/left/right) |
| input_text | 输入文字 | text, target_ref |
| wait | 等待 | duration (秒) |
| launch_app | 启动应用 | package_name, activity |
| call | 拨打电话 | phone_number |
| open_url | 打开网址 | url |
| key_event | 按键事件 | key_code |

### 常用按键码

| 按键 | key_code |
|------|----------|
| Home | 3 |
| Back | 4 |
| 音量+ | 24 |
| 音量- | 25 |
| 电源 | 26 |
| 回车 | 66 |
| 静音 | 164 |
| 最近任务 | 187 |

## 任务路由与处理策略

系统根据任务内容自动决定使用预定义模板还是 AI 规划。

### 任务处理流程

```
用户任务
    │
    ▼
┌─────────────────────────────────────┐
│ 1. 模块路由 (ModuleRegistry.route)  │
│    - 根据关键词匹配找最佳模块        │
│    - 根据任务模板正则匹配            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 2. 模板匹配 (handler.match_template)│
│    - 尝试匹配 tasks.yaml 中的模式   │
│    - 提取变量（如 URL、电话号码）    │
└─────────────────────────────────────┘
    │
    ├── 匹配成功 ──▶ 使用预定义步骤（快速、免费）
    │
    └── 匹配失败 ──▶ 调用 AI 规划（灵活、需 API）
```

### 路由评分算法

```python
score = 0.0

# 1. 任务模板匹配 (权重 0.5) - 最高优先级
if 任务匹配 tasks.yaml 中的 pattern:
    score += 0.5

# 2. 关键词匹配 (权重 0.4)
# 每个命中的关键词 +0.1，最多 0.4
for keyword in module.keywords:
    if keyword in task:
        score += 0.1  # 完全匹配额外 +0.2

# 3. 包名匹配 (权重 0.1)
if package_name in task:
    score += 0.1
```

### 预定义模板 vs AI 规划

**设计原则**：只有最简单的系统级操作使用预定义模板，其他所有任务交给 AI 规划。

#### 简单任务（使用模板，标记 `simple: true`）

| 类型 | 示例 | 原因 |
|------|------|------|
| 启动应用 | 打开微信、打开浏览器 | 单一 ADB 命令 |
| 系统按键 | 返回桌面、锁屏、静音 | 单一按键事件 |
| 音量控制 | 增大音量、减小音量 | 固定按键序列 |
| 拨打电话 | 拨打 12345 | 直接调用系统 Intent |

#### AI 规划任务（不标记 simple）

| 类型 | 示例 | 原因 |
|------|------|------|
| 涉及界面元素 | 点击搜索框、发送消息 | 需要视觉定位 |
| 多步骤操作 | 打开百度然后搜索 | 需要理解任务序列 |
| 内容输入 | 搜索"天气"、发消息"你好" | 需要处理用户输入 |
| 动态交互 | 查看朋友圈、打开设置 | 界面状态不确定 |

#### tasks.yaml 配置示例

```yaml
tasks:
  # ✅ 简单任务 - 直接执行
  - name: 打开微信
    simple: true          # 标记为简单任务
    patterns:
      - "打开微信"
    steps:
      - action: launch_app
        package_name: "com.tencent.mm"

  # ❌ 非简单任务 - 交给 AI
  - name: 发消息给联系人
    # 不标记 simple，由 AI 规划
    patterns:
      - "(?:给)?(?P<contact>.+?)(?:发消息)"
    variables:
      - contact
```

#### 当前简单任务清单

| 模块 | 简单任务 |
|------|---------|
| 系统 | 拨打电话、打开拨号盘、返回桌面、返回上一级、最近任务、下拉/收起通知栏、音量加减、静音、锁屏 |
| 微信 | 打开微信 |
| Chrome | 打开浏览器 |

### 正则模式设计原则

1. **精确匹配**：避免过度贪婪的正则
   ```yaml
   # ❌ 错误：会匹配过多内容
   - "访问(?P<url>.+)"

   # ✅ 正确：只匹配有效 URL 字符
   - "访问(?P<url>[a-zA-Z0-9._~:/?#@!$&'()*+;=-]+)"
   ```

2. **处理中文边界**：URL、数字等参数遇到中文应停止
   ```yaml
   # 匹配电话号码，遇到非数字停止
   - "(?:打电话|拨打).*?(?P<number>\\d{5,})"
   ```

3. **可选前缀**：支持多种表达方式
   ```yaml
   - "(?:打开|访问|进入)(?:网址|网站)?\\s*(?P<url>...)"
   ```

## 执行策略设计

系统采用分层执行策略，根据步骤的复杂度决定执行方式，大幅提高执行效率。

### 执行级别

| 级别 | 名称 | 动作 | 特点 |
|------|------|------|------|
| Level 0 | FIRE_AND_FORGET | `launch_app`, `call`, `open_url`, `press_key`, `go_home`, `wait` | 直接执行，无需截图和验证 |
| Level 1 | QUICK_VERIFY | `swipe` | 快速执行，轻量验证 |
| Level 2 | LOCATE_AND_EXECUTE | `tap`/`input_text` + 参考图 | 需要 OpenCV 定位，轻量验证 |
| Level 3 | FULL_AI | `tap`/`input_text` + 动态描述 | 需要 AI 定位 + AI 验证 |

### 批量执行

连续的 Level 0 步骤会被批量执行：

```
原始步骤：[launch_app] → [wait] → [open_url] → [wait] → [tap dynamic:xxx]

批量分组：
  批次1: [launch_app, wait, open_url, wait]  ← 快速连续执行
  批次2: [tap dynamic:xxx]                    ← 单独执行，需要 AI
```

### 执行流程对比

```
旧流程（每步都慢）：
步骤1: 截图 → AI定位 → 执行 → 截图 → AI验证 → 等待
步骤2: 截图 → AI定位 → 执行 → 截图 → AI验证 → 等待
...
总计：6步任务 = 12+ 次 AI 调用

新流程（智能分层）：
[批次1: Level 0 步骤] → 直接连续执行，无 AI 调用
[批次2: Level 3 步骤] → 截图 → AI定位 → 执行 → AI验证
...
总计：6步任务 = 2-4 次 AI 调用
```

### 代码位置

- `core/execution_strategy.py` - 策略定义和步骤分类
- `core/task_runner.py` - `_execute_step_fast()` 和 `_execute_step_with_strategy()`

## 验证策略设计

不同类型的动作需要不同的验证策略，这是系统设计的核心原则之一。

### 验证策略分类

| 策略 | 适用动作 | 说明 |
|------|---------|------|
| **跳过验证** | `wait`, `press_key`, `go_home` | 这些动作不一定会导致屏幕变化，执行即成功 |
| **宽松验证** | `launch_app`, `open_url`, `call` | 只检查是否有错误弹窗，不要求屏幕必须变化（应用可能已打开） |
| **标准验证** | `tap`, `long_press`, `swipe`, `input_text` | 检查屏幕是否有预期变化 |
| **精确验证** | 带 `verify_ref` 或 `success_condition` 的步骤 | 使用参考图或描述进行精确验证 |

### 各动作的验证逻辑

```
┌─────────────────┬──────────────────────────────────────────────────┐
│ 动作            │ 验证逻辑                                          │
├─────────────────┼──────────────────────────────────────────────────┤
│ wait            │ 跳过验证，等待时间到即成功                         │
│ press_key       │ 跳过验证，按键可能没有可见效果                     │
│ go_home         │ 跳过验证，可能已在桌面                            │
├─────────────────┼──────────────────────────────────────────────────┤
│ launch_app      │ 宽松验证，应用可能已打开，只检查错误               │
│ open_url        │ 宽松验证，页面可能已加载，只检查错误               │
│ call            │ 宽松验证，只检查是否进入通话界面                   │
├─────────────────┼──────────────────────────────────────────────────┤
│ tap             │ 标准验证，期望屏幕有响应变化                       │
│ long_press      │ 标准验证，期望弹出菜单或有反馈                     │
│ swipe           │ 标准验证，期望页面滚动或切换                       │
│ input_text      │ 标准验证，期望输入框显示文字                       │
└─────────────────┴──────────────────────────────────────────────────┘
```

### 自定义验证条件

在 tasks.yaml 中可以为步骤指定精确的验证条件：

```yaml
steps:
  - action: tap
    description: 点击登录按钮
    target_ref: "login_button"
    # 方式1: 使用参考图验证
    verify_ref: "login_success_page"

  - action: input_text
    description: 输入用户名
    text: "{username}"
    # 方式2: 使用描述验证
    success_condition: "输入框中显示了输入的用户名"
```

### 扩展新动作时的验证设计原则

1. **确定动作的可预期性**
   - 动作是否一定会导致屏幕变化？
   - 动作失败时屏幕会如何表现？

2. **选择合适的验证策略**
   - 无可见效果 → 跳过验证
   - 可能无变化但需检查错误 → 宽松验证
   - 期望明确变化 → 标准验证

3. **在 TaskRunner._verify_step() 中注册**
   ```python
   # 跳过验证的动作
   skip_verify_actions = [ActionName.WAIT, ActionName.PRESS_KEY, ...]

   # 宽松验证的动作
   lenient_verify_actions = [ActionName.LAUNCH_APP, ActionName.OPEN_URL, ...]
   ```

## 元素定位策略

系统使用混合定位器，优先使用免费的 OpenCV，失败时回退到 AI。

### 定位流程

```
需要定位元素
    │
    ▼
┌─────────────────────────────────────┐
│ 1. 查找模块参考图                    │
│    apps/{module}/images/{name}.png  │
└─────────────────────────────────────┘
    │ 找到参考图
    ▼
┌─────────────────────────────────────┐
│ 2. OpenCV 模板匹配                   │
│    - 快速、免费、离线                │
│    - 适合固定 UI 元素               │
└─────────────────────────────────────┘
    │ 失败
    ▼
┌─────────────────────────────────────┐
│ 3. OpenCV 多尺度匹配                 │
│    - 适应不同分辨率屏幕              │
└─────────────────────────────────────┘
    │ 失败
    ▼
┌─────────────────────────────────────┐
│ 4. OpenCV 特征点匹配                 │
│    - 抗旋转、缩放                   │
│    - 适合复杂图标                   │
└─────────────────────────────────────┘
    │ 失败
    ▼
┌─────────────────────────────────────┐
│ 5. AI 视觉定位（回退）               │
│    - 需要 API 调用                  │
│    - 可处理动态内容                  │
└─────────────────────────────────────┘
```

### 定位策略选择

| 策略 | 使用场景 | 优点 | 缺点 |
|------|---------|------|------|
| `OPENCV_ONLY` | 纯离线场景 | 快速、免费 | 无法处理动态内容 |
| `AI_ONLY` | 开发调试 | 最灵活 | 慢、费钱 |
| `OPENCV_FIRST` | **默认推荐** | 平衡速度和准确性 | - |

### 参考图片质量要求

为了提高 OpenCV 匹配成功率：

1. **尺寸**：100-300px 宽度为佳
2. **清晰度**：边缘锐利、无模糊
3. **背景**：纯色或简单背景，避免复杂纹理
4. **唯一性**：确保元素在屏幕上是唯一的
5. **状态**：只截取默认状态，避免选中/高亮状态

### 动态元素处理

对于无法用参考图匹配的动态元素，使用 `dynamic:` 前缀：

```yaml
steps:
  - action: tap
    target_ref: "dynamic:屏幕上显示的第一个联系人头像"
    description: 点击第一个搜索结果
```

这将跳过 OpenCV，直接使用 AI 视觉理解来定位。

## 高级功能

### 自定义处理器

如需更复杂的逻辑，可创建自定义 handler：

```python
# apps/myapp/handler.py

from apps.base import AppHandler, DefaultHandler
from typing import Dict, Any, List

class Handler(DefaultHandler):
    """自定义处理器"""

    def plan(self, task: str, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        自定义任务规划逻辑

        返回空列表则使用 AI 规划
        """
        # 先尝试模板匹配
        steps = super().plan(task, context)
        if steps:
            return steps

        # 自定义逻辑
        if "特殊功能" in task:
            return [
                {"action": "launch_app", "package_name": "com.example.myapp"},
                {"action": "wait", "duration": 1.5},
                {"action": "tap", "target_ref": "special_button"}
            ]

        return []  # 使用 AI 规划

    def get_planner_prompt(self) -> str:
        """返回自定义的 AI 规划提示词"""
        # 先尝试加载文件
        custom = self.assets.get_prompt("planner")
        if custom:
            return custom

        # 返回自定义提示词
        return """你是我的应用的自动化规划器...

可用的参考图片：
- search_box
- search_button
...
"""
```

### 混合定位策略

系统会自动使用混合定位策略：

1. **OpenCV 模板匹配** - 快速、免费、离线
2. **OpenCV 多尺度匹配** - 适应不同分辨率
3. **OpenCV 特征点匹配** - 抗旋转/缩放
4. **AI 视觉定位** - 最后回退

确保参考图片清晰、无背景干扰，以提高 OpenCV 匹配成功率。

### 参考图片最佳实践

1. **尺寸适中**：不要太大（影响速度）或太小（细节不足）
2. **边缘清晰**：确保元素边界清晰
3. **背景简单**：尽量去除复杂背景
4. **多分辨率**：可为不同分辨率准备多个版本
5. **命名规范**：使用英文小写加下划线

## Planner Prompt 设计指南

模块的 `prompts/planner.txt` 是 AI 任务规划的核心，设计良好的 prompt 直接影响执行成功率。

### Prompt 文件位置

```
apps/{module}/prompts/planner.txt
```

### Prompt 结构模板

```
【角色定义】
你是 {应用名} 的自动化任务规划器...

【当前状态】
{运行时注入当前截图分析}

【可用参考图】
必须列出所有可用的参考图名称，AI 才能正确引用
- search_box         # 搜索输入框
- search_button      # 搜索按钮
- ...

【target_ref 使用规则】
明确说明何时使用参考图、何时使用 dynamic:

【输出格式】
JSON 格式说明

【示例】
提供详细的任务规划示例
```

### 关键设计原则

#### 1. 优先使用参考图，避免 dynamic:

```
【重要规则】
对于已有参考图的元素，必须使用参考图名称，不要用 dynamic:

✅ 正确: target_ref: "chrome_baidu_search_box"
❌ 错误: target_ref: "dynamic:百度搜索输入框"

只有在以下情况才使用 dynamic::
- 元素是动态内容（如搜索结果中的特定联系人）
- 没有对应的参考图
```

#### 2. 列出所有可用参考图

```
【可用参考图】
以下是本模块已准备的参考图，规划时必须使用这些名称：

首页元素:
- chrome_address_bar     # 地址栏
- chrome_menu_button     # 菜单按钮（三点）

百度搜索页面:
- chrome_baidu_search_box    # 百度搜索输入框
- chrome_baidu_search_button # 百度搜索按钮（"百度一下"）
```

#### 3. 提供详细的任务示例

```json
// 示例：打开百度搜索新闻
{
  "steps": [
    {
      "step": 1,
      "action": "launch_app",
      "description": "启动 Chrome 浏览器",
      "params": {"package_name": "com.android.chrome"}
    },
    {
      "step": 2,
      "action": "open_url",
      "description": "打开百度",
      "params": {"url": "https://www.baidu.com"}
    },
    {
      "step": 3,
      "action": "tap",
      "target_ref": "chrome_baidu_search_box",  // 使用参考图！
      "description": "点击百度搜索框"
    },
    {
      "step": 4,
      "action": "input_text",
      "params": {"text": "新闻"},
      "description": "输入搜索内容"
    },
    {
      "step": 5,
      "action": "tap",
      "target_ref": "chrome_baidu_search_button",  // 使用参考图！
      "description": "点击搜索按钮"
    }
  ]
}
```

#### 4. 智能路径规划

指导 AI 选择最优执行路径：

```
【智能路径规划】

1. 起点判断:
   - 如果任务是"打开百度搜索XXX"，应该先启动Chrome再open_url
   - 如果已经在百度页面，直接搜索即可

2. 应用状态检测:
   - 在桌面 → 启动应用 → 执行操作
   - 在应用内但非目标页面 → 返回 → 导航到目标
   - 已在目标页面 → 直接执行操作

3. 返回首页策略:
   - 使用 press_key(4) 循环检测返回
   - 不要用固定次数的返回
```

### 常见错误避免

| 错误 | 正确做法 |
|------|----------|
| 对已有参考图使用 `dynamic:` | 使用参考图名称 |
| 未列出可用参考图 | 在 prompt 中明确列出 |
| 示例中使用中文别名 | 示例中使用英文参考图名称 |
| 固定次数返回 | 循环检测是否到达首页 |

### 验证 Prompt 效果

```bash
# 测试任务规划
python test_planner.py plan screenshot.png "打开百度搜索天气"

# 检查输出的 target_ref 是否使用参考图名称
```

## 测试模块

```bash
# 查看已注册的模块
python run.py --modules

# 测试任务路由
python -c "
from apps import ModuleRegistry
ModuleRegistry.discover()
handler, score = ModuleRegistry.route('在我的应用中搜索内容')
print(f'路由到: {handler.module_info.name}, 得分: {score:.2f}')
"

# 执行任务
python run.py -t "打开我的应用"
```

## 示例模块

参考现有模块：

- `apps/system/` - 系统操作模块
- `apps/wechat/` - 微信模块
- `apps/chrome/` - Chrome 浏览器模块

## 常见问题

### Q: 模块没有被发现？

检查：
1. 模块目录是否在 `apps/` 下
2. 是否有 `config.yaml` 文件
3. 目录名是否以 `_` 开头（会被忽略）

### Q: 任务没有路由到我的模块？

检查：
1. `keywords` 是否包含相关词汇
2. 其他模块是否有更高的匹配度

### Q: OpenCV 匹配失败？

尝试：
1. 使用更清晰的参考图
2. 确保截取的元素边界完整
3. 避免透明背景
4. 检查分辨率是否匹配

### Q: 如何调试？

设置日志：
```python
runner = TaskRunner(adb)
runner.set_logger(lambda msg: print(f"[LOG] {msg}"))
```
