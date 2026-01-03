# VisionAgent: One-Shot Object Detection 完整架构设计

## 目录

1. [核心理念](#核心理念)
2. [系统架构总览](#系统架构总览)
3. [参考图库设计](#参考图库设计)
4. [Layer 1: 任务规划器 (Planner)](#layer-1-任务规划器-planner)
5. [Layer 2: 元素定位器 (Locator)](#layer-2-元素定位器-locator)
6. [Layer 3: 动作执行器 (Executor)](#layer-3-动作执行器-executor)
7. [Layer 4: 结果验证器 (Verifier)](#layer-4-结果验证器-verifier)
8. [任务执行器 (TaskRunner)](#任务执行器-taskrunner)
9. [Fallback 机制详解](#fallback-机制详解)
10. [任务类型详细流程](#任务类型详细流程)
11. [错误处理与恢复](#错误处理与恢复)
12. [配置与环境](#配置与环境)
13. [测试指南](#测试指南)

---

## 核心理念

### 为什么使用双图片匹配？

| 方式 | 优点 | 缺点 |
|------|------|------|
| 文字描述 | 灵活 | 容易混淆相似名称（乐读 vs 微信读书） |
| **参考图匹配** | 精准，基于像素特征 | 需要维护参考图库 |

### 基本原则

1. **优先使用双图输入**：参考图 + 截图（One-Shot Detection）
2. **预置常用参考图**：图标、UI 元素、状态验证图
3. **动态描述作为备选**：当无参考图时使用 `dynamic:描述` 方式
4. **多层验证**：操作后验证结果，失败则重试或执行 fallback
5. **Fallback 机制**：定位失败时自动执行备选动作（如滑动）后重试

### 定位优先级

```
1. 参考图匹配 (find_element_by_image)
   ↓ 如果参考图不存在
2. 别名解析 → 参考图匹配
   ↓ 如果别名未找到
3. 动态描述定位 (find_element)
   ↓ 如果定位失败且有 fallback
4. 执行 fallback → 重新定位（最多3次）
```

---

## 系统架构总览

```
用户输入任务: "给张三发微信消息说你好"
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    TaskRunner (任务执行器)                       │
│                 整合所有层，协调执行完整任务流程                   │
└─────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 1: Planner (任务规划器)                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ 当前截图     │ +  │ 任务描述     │ →  │ 步骤列表 + 参考图映射 │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                  │
│  输出: TaskPlan { analysis, steps[], success_criteria }         │
└─────────────────────────────────────────┬───────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
              ┌──────────┐          ┌──────────┐          ┌──────────┐
              │  Step 1  │          │  Step 2  │          │  Step N  │
              └────┬─────┘          └────┬─────┘          └────┬─────┘
                   │                     │                     │
     ┌─────────────┴─────────────────────┴─────────────────────┘
     │
     ▼ (对每个 Step 循环执行)
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 2: Locator (元素定位器)                 │
│                       VisionAgent 实现                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 模式A: 双图匹配                                              ││
│  │ ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  ││
│  │ │ 参考图       │ +  │ 当前截图     │ →  │ bbox (0-1000)   │  ││
│  │ └─────────────┘    └─────────────┘    └─────────────────┘  ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 模式B: 描述定位                                              ││
│  │ ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  ││
│  │ │ 文字描述     │ +  │ 当前截图     │ →  │ bbox (0-1000)   │  ││
│  │ └─────────────┘    └─────────────┘    └─────────────────┘  ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│                              ▼                                   │
│              bbox_to_center() → 像素坐标 (x, y)                  │
└─────────────────────────────────────────┬───────────────────────┘
                                          │
                              ┌───────────┴───────────┐
                              │ 定位失败且有 fallback? │
                              └───────────┬───────────┘
                                    │ 是
                                    ▼
                    ┌─────────────────────────────────┐
                    │ 执行 fallback (滑动/等待等)      │
                    │ 重新截图 → 再次定位              │
                    │ 最多重试 3 次                   │
                    └─────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 3: Executor (动作执行器)                │
│                      ADBController 实现                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ 动作类型     │ +  │ 坐标/参数    │ →  │ ADB 命令执行         │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                  │
│  支持动作: tap, long_press, swipe, input_text, press_key,       │
│           wait, go_home                                         │
└─────────────────────────────────────────┬───────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Layer 4: Verifier (结果验证器)                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ 期望状态     │ +  │ 当前截图     │ →  │ VerifyResult        │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                  │
│  输出: { verified, confidence, blocker?, suggestion }           │
└─────────────────────────────────────────┬───────────────────────┘
                                          │
                         ┌────────────────┴────────────────┐
                         │                                 │
                    成功 ▼                            失败 ▼
               ┌─────────────┐                    ┌─────────────┐
               │ 执行下一步   │                    │ 错误恢复流程 │
               └─────────────┘                    │ - dismiss   │
                                                  │ - retry     │
                                                  │ - replan    │
                                                  │ - abort     │
                                                  └─────────────┘
```

---

## 参考图库设计

### 目录结构

```
assets/
├── icons/                          # 应用图标 (72x72 ~ 192x192)
│   ├── wechat.png                 # 微信 ✓
│   ├── chrome.png                 # Chrome ✓
│   ├── setting.png                # 设置 ✓
│   ├── call.png                   # 电话 ✓
│   ├── wechat_contacts.png        # 微信通讯录 ✓
│   ├── wechat_search.png          # 微信搜索 ✓
│   ├── send_button.png            # 发送按钮 ✓
│   ├── xiaotiancai.png            # 小天才 ✓
│   └── ... (待添加更多)
│
├── ui/                             # 通用 UI 元素 (各种尺寸)
│   ├── navigation/                # 导航元素
│   │   ├── back_arrow_black.png
│   │   ├── back_arrow_white.png
│   │   └── ...
│   │
│   ├── actions/                   # 操作按钮
│   │   ├── search_icon.png
│   │   ├── add_plus.png
│   │   └── ...
│   │
│   ├── dialogs/                   # 对话框按钮
│   │   ├── confirm_button.png
│   │   ├── close_x.png
│   │   └── ...
│   │
│   ├── input/                     # 输入相关
│   │   └── ...
│   │
│   └── media/                     # 媒体控制
│       └── ...
│
├── states/                         # 状态验证参考图 (缩略图 360x640)
│   ├── system/
│   │   ├── home_screen.png        # 桌面
│   │   └── ...
│   │
│   └── wechat/
│       ├── main.png               # 微信主界面
│       └── ...
│
├── custom/                         # 用户自定义 + 动态生成
│   └── temp/                      # 临时参考图（任务结束后清理）
│
└── index.json                      # 参考图索引和元数据
```

### index.json 结构

```json
{
  "version": "1.0",
  "icons": {
    "wechat": {
      "path": "icons/wechat.png",
      "aliases": ["微信", "WeChat"],
      "package": "com.tencent.mm",
      "exists": true
    }
  },
  "ui": {
    "search_icon": {
      "path": "ui/actions/search_icon.png",
      "description": "搜索图标/放大镜",
      "exists": false
    }
  },
  "states": {
    "wechat_main": {
      "path": "states/wechat/main.png",
      "description": "微信主界面",
      "exists": false
    }
  }
}
```

### AssetsManager 使用

```python
from ai.planner import AssetsManager

assets = AssetsManager()

# 获取参考图
img = assets.get_image("wechat")  # 直接名称
img = assets.get_image("微信")    # 使用别名（自动解析）

# 别名解析
ref_name = assets.resolve_alias("微信")  # 返回 "wechat"

# 获取可用参考图列表
refs = assets.get_available_refs()
# 返回 {"icons": [...], "ui": [...], "states": [...]}
```

---

## Layer 1: 任务规划器 (Planner)

### 职责

将用户的自然语言任务分解为可执行的步骤序列。

### 代码位置

`ai/planner.py` - `Planner` 类

### 输入

| 参数 | 类型 | 说明 |
|------|------|------|
| task | string | 用户任务描述 |
| screenshot | Image | 当前屏幕截图 |
| history | list | 已执行的步骤历史（可选） |

### 输出数据结构

```python
@dataclass
class StepPlan:
    step: int                              # 步骤序号
    action: ActionName                      # 动作类型
    target_ref: Optional[str] = None       # 参考图名称或 "dynamic:描述"
    target_type: Optional[TargetType] = None  # icon/ui/dynamic/state
    description: str = ""                  # 操作描述
    params: Dict[str, Any] = field(...)   # 额外参数
    verify_ref: Optional[str] = None       # 验证用的参考图名称
    success_condition: Optional[str] = None # 成功条件描述
    fallback: Optional[Dict] = None        # 备选方案 ⭐重要
    timeout: int = 3000                    # 超时时间 (ms)
    retry: int = 2                         # 重试次数
    wait_before: int = 0                   # 执行前等待 (ms)
    wait_after: int = 300                  # 执行后等待 (ms)

@dataclass
class TaskPlan:
    analysis: Dict[str, Any]       # 分析结果
    steps: List[StepPlan]          # 步骤列表
    success_criteria: str = ""     # 成功标准
    potential_issues: List[str] = field(...)  # 潜在问题
```

### 动作类型

```python
class ActionName(Enum):
    TAP = "tap"
    LONG_PRESS = "long_press"
    SWIPE = "swipe"
    INPUT_TEXT = "input_text"
    PRESS_KEY = "press_key"
    WAIT = "wait"
    GO_HOME = "go_home"  # 特殊动作：返回桌面（连续两次 HOME）
```

### 示例输出

```json
{
  "analysis": {
    "current_screen": "手机桌面，显示多个应用图标",
    "target_state": "微信聊天界面，与张三的对话",
    "estimated_steps": 6
  },
  "steps": [
    {
      "step": 1,
      "action": "tap",
      "target_ref": "wechat",
      "target_type": "icon",
      "description": "点击微信图标打开应用",
      "verify_ref": "wechat_main",
      "fallback": {
        "action": "swipe",
        "params": {"direction": "left"},
        "description": "左滑桌面查找微信图标"
      },
      "timeout": 3000,
      "retry": 2
    },
    {
      "step": 2,
      "action": "tap",
      "target_ref": "wechat_search",
      "target_type": "icon",
      "description": "点击微信搜索图标",
      "fallback": {
        "action": "tap",
        "target_ref": "dynamic:顶部搜索栏区域"
      }
    },
    {
      "step": 3,
      "action": "input_text",
      "params": {"text": "张三"},
      "description": "输入联系人名称"
    },
    {
      "step": 4,
      "action": "tap",
      "target_ref": "dynamic:搜索结果中名为张三的联系人",
      "target_type": "dynamic",
      "description": "点击搜索结果中的张三"
    },
    {
      "step": 5,
      "action": "input_text",
      "target_ref": "dynamic:底部消息输入框",
      "params": {"text": "你好"},
      "description": "输入消息内容"
    },
    {
      "step": 6,
      "action": "tap",
      "target_ref": "send_button",
      "target_type": "icon",
      "description": "点击发送按钮",
      "success_condition": "消息出现在聊天记录中"
    }
  ],
  "success_criteria": "消息成功发送，显示在聊天记录中",
  "potential_issues": [
    "微信可能需要登录",
    "联系人可能不存在"
  ]
}
```

---

## Layer 2: 元素定位器 (Locator)

### 职责

在屏幕截图中定位目标元素，返回精确坐标。

### 代码位置

- `ai/vision_agent.py` - `VisionAgent` 类（AI 定位）
- `core/hybrid_locator.py` - `HybridLocator` 类（混合定位器）

### 混合定位架构（重要设计）

系统采用**混合定位策略**，优先使用免费快速的 OpenCV，失败时自动回退到 AI：

```
需要定位元素 (target_ref)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. 检查 target_ref 格式                                      │
│    - 以 "dynamic:" 开头 → 直接使用 AI 定位                   │
│    - 否则 → 尝试 OpenCV 定位                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (非 dynamic)
┌─────────────────────────────────────────────────────────────┐
│ 2. 查找参考图                                                │
│    - apps/{module}/images/{name}.png                        │
│    - 支持变体: {name}_v2.png, {name}_v3.png ...             │
│    - 变体命名从 _v2 开始，不是 _v1                           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (找到参考图)
┌─────────────────────────────────────────────────────────────┐
│ 3. OpenCV 模板匹配 (快速、免费、离线)                         │
│    - 标准模板匹配 cv2.matchTemplate                          │
│    - 置信度阈值: 0.75                                        │
└─────────────────────────────────────────────────────────────┘
    │ 失败
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. OpenCV 多尺度匹配                                         │
│    - 适应不同分辨率屏幕                                      │
│    - 尺度范围: 0.5x - 1.5x                                   │
└─────────────────────────────────────────────────────────────┘
    │ 失败
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. OpenCV 特征点匹配 (ORB)                                   │
│    - 抗旋转、缩放变换                                        │
│    - 适合复杂图标                                            │
└─────────────────────────────────────────────────────────────┘
    │ 失败
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. AI 视觉定位 (回退)                                        │
│    - 调用 VisionAgent.find_element_by_image                 │
│    - 需要 API 调用，较慢                                     │
│    - 可处理 OpenCV 无法识别的动态内容                        │
└─────────────────────────────────────────────────────────────┘
```

### 定位策略枚举

```python
class LocateStrategy(Enum):
    OPENCV_ONLY = "opencv_only"     # 纯离线，只用 OpenCV
    AI_ONLY = "ai_only"             # 只用 AI（调试用）
    OPENCV_FIRST = "opencv_first"   # 默认：OpenCV 优先，失败回退 AI
```

### target_ref 格式说明

| 格式 | 示例 | 定位方式 | 说明 |
|------|------|---------|------|
| 参考图名称 | `chrome_baidu_search_box` | OpenCV → AI | 优先 OpenCV，快速 |
| 别名 | `搜索框` | OpenCV → AI | 自动解析为参考图名称 |
| 动态描述 | `dynamic:底部输入框` | 仅 AI | 跳过 OpenCV，直接 AI |

**重要**：应优先使用参考图名称，只有无法提前准备参考图的动态内容才使用 `dynamic:`

### 两种定位模式

#### 模式 A: 双图匹配（优先使用）

```python
def find_element_by_image(
    self,
    reference_image: Image.Image,
    screenshot: Image.Image
) -> Optional[Tuple[int, int]]:
    """
    通过参考图片在屏幕截图中查找元素

    返回: (x, y) 像素坐标，未找到返回 None
    """
```

**Prompt 核心内容:**
```
Task: Detect the Reference Image (Image 1) inside the Screenshot (Image 2).

【Instructions】
1. Visual Matching: Match by shape, color, icon design
2. Coordinate System: 0-1000 scale for both X and Y
3. Precision: Match by visual features, NOT by guessing text

【Output】
{"found": true, "xmin": int, "ymin": int, "xmax": int, "ymax": int, "confidence": float}
或
{"found": false, "reason": "...", "suggestion": "..."}
```

#### 模式 B: 描述定位（备选）

```python
def find_element(
    self,
    image: Image.Image,
    element_description: str
) -> Optional[Tuple[int, int]]:
    """
    使用文字描述在屏幕中查找元素

    返回: (x, y) 像素坐标，未找到返回 None
    """
```

### 坐标转换

LLM 返回 0-1000 范围的 bbox，需要转换为像素坐标：

```python
def _bbox_to_center(self, bbox: dict, width: int, height: int) -> Tuple[int, int]:
    """将 0-1000 的 bbox 转换为中心点像素坐标"""
    xmin, ymin = bbox["xmin"], bbox["ymin"]
    xmax, ymax = bbox["xmax"], bbox["ymax"]

    # 计算中心点百分比
    x_center = (xmin + xmax) / 2 / 1000
    y_center = (ymin + ymax) / 2 / 1000

    # 转换为像素坐标
    return int(x_center * width), int(y_center * height)
```

### TaskRunner 中的定位优先级实现

```python
def _locate_target(self, step: StepPlan, screenshot: Image) -> Optional[tuple]:
    target_ref = step.target_ref

    # 1. 动态描述
    if target_ref.startswith("dynamic:"):
        description = target_ref[8:]
        return self.locator.find_element(screenshot, description)

    # 2. 参考图匹配
    ref_image = self.assets.get_image(target_ref)
    if ref_image is None:
        # 尝试别名解析
        resolved = self.assets.resolve_alias(target_ref)
        if resolved:
            ref_image = self.assets.get_image(resolved)

    if ref_image is not None:
        return self.locator.find_element_by_image(ref_image, screenshot)

    # 3. 回退到描述定位
    return self.locator.find_element(screenshot, step.description)
```

---

## 执行策略分层设计（重要）

系统采用**四级执行策略**，根据步骤复杂度智能决定执行方式，大幅减少 AI 调用次数。

### 执行级别定义

```python
class ExecutionLevel(Enum):
    FIRE_AND_FORGET = 0   # 直接执行，无需验证
    QUICK_VERIFY = 1       # 快速执行，轻量验证
    LOCATE_AND_EXECUTE = 2 # 需要定位，轻量验证
    FULL_AI = 3            # 完整 AI 流程
```

### 各级别详细说明

| 级别 | 动作 | 特点 | 等待时间 |
|------|------|------|----------|
| **Level 0** | `launch_app`, `call`, `open_url`, `go_home`, `wait`, `press_key`(无导航目标) | 直接 ADB 执行，无需截图和验证 | 100-2500ms |
| **Level 1** | `swipe` | 方向已知，快速执行 | 200ms |
| **Level 2** | `tap`/`input_text` + 参考图 | 需要 OpenCV 定位 | 300ms |
| **Level 3** | `tap`/`input_text` + `dynamic:` | 需要 AI 定位 + AI 验证 | 500-1000ms |

### Level 0 动作的特殊等待时间

```python
if action == ActionName.LAUNCH_APP:
    wait_ms = 500    # 应用启动需要较长时间
elif action == ActionName.OPEN_URL:
    wait_ms = 2500   # 网页加载需要等待
else:
    wait_ms = 100
```

### 批量执行优化

连续的 Level 0 步骤会被分组批量执行：

```
原始步骤：[launch_app] → [wait] → [open_url] → [wait] → [tap dynamic:xxx]

批量分组：
  批次1: [launch_app, wait, open_url, wait]  ← 快速连续执行，0 次 AI 调用
  批次2: [tap dynamic:xxx]                    ← 单独执行，需要 AI
```

### 执行效率对比

```
旧流程（每步都慢）：
步骤1: 截图 → AI定位 → 执行 → 截图 → AI验证 → 等待
步骤2: 截图 → AI定位 → 执行 → 截图 → AI验证 → 等待
...
总计：6步任务 = 12+ 次 AI 调用

新流程（智能分层）：
[批次1: Level 0 步骤] → 直接连续执行，0 次 AI 调用
[批次2: Level 3 步骤] → 截图 → AI定位 → 执行 → AI验证
...
总计：6步任务 = 2-4 次 AI 调用
```

### 代码位置

- `core/execution_strategy.py` - 策略定义和步骤分类
- `core/task_runner.py` - `_execute_step_fast()` 和 `_execute_step_with_strategy()`

---

## 中文输入编码设计

### 问题背景

ADB 原生 `input text` 命令只支持 ASCII 字符，中文会乱码。

### 解决方案：ADBKeyboard + Base64 编码

系统优先使用 Base64 编码方式避免 shell 传参的编码问题：

```python
def input_text_chinese(self, text: str) -> bool:
    import base64

    # 方法1: ADBKeyboard Base64 方式（首选）
    encoded = base64.b64encode(text.encode('utf-8')).decode('ascii')
    result = self._run_adb(
        "shell", "am", "broadcast",
        "-a", "ADB_INPUT_B64",
        "--es", "msg", encoded
    )

    if result.returncode == 0 and "Broadcast completed" in result.stdout:
        return True

    # 方法2: ADBKeyboard 标准方式（备用）
    result = self._run_adb(
        "shell", "am", "broadcast",
        "-a", "ADB_INPUT_TEXT",
        "--es", "msg", text
    )
    return result.returncode == 0
```

### 为什么使用 Base64？

- 避免 shell 转义问题
- 避免不同 shell 环境的编码差异
- ADBKeyboard 支持 `ADB_INPUT_B64` 动作，自动解码

---

## 返回首页循环检测

### 问题背景

执行 "返回微信首页" 时，需要循环按返回键直到到达首页，而不是固定按几次。

### 设计原则

```
执行 "返回首页"
    │
    ▼
┌───────────────────────────────────────┐
│ 循环检测（最多 10 次）                 │
│   1. 截图                             │
│   2. 检测当前是否已在首页             │
│      - 使用参考图匹配首页特征         │
│      - 或 AI 判断                     │
│   3. 如果在首页 → 结束               │
│   4. 如果不在 → 按返回键 → 继续循环  │
└───────────────────────────────────────┘
```

### 实现要点

- 使用 `wechat_tab_chat.png` 等参考图检测是否在首页
- 每次按返回后等待 300ms 让动画完成
- 设置最大次数防止死循环

---

## Layer 3: 动作执行器 (Executor)

### 职责

执行具体的 ADB 操作。

### 代码位置

`core/adb_controller.py` - `ADBController` 类

### 支持的操作

| 动作 | 方法 | 参数 |
|------|------|------|
| tap | `adb.tap(x, y)` | 坐标 |
| long_press | `adb.long_press(x, y, duration)` | 坐标, 时长(ms) |
| swipe | `adb.swipe(x1, y1, x2, y2, duration)` | 起点, 终点, 时长 |
| input_text | `adb.input_text(text)` | 文本 |
| press_key | `adb.input_keyevent(keycode)` | 按键码 |

### 常用按键码

```python
KEYCODES = {
    "HOME": 3,
    "BACK": 4,
    "CALL": 5,
    "END_CALL": 6,
    "VOLUME_UP": 24,
    "VOLUME_DOWN": 25,
    "POWER": 26,
    "ENTER": 66,
    "DEL": 67,
}
```

### 特殊动作: go_home

**重要**: 返回桌面需要连续按两次 HOME 键

```python
def _execute_go_home(self) -> bool:
    """
    返回桌面首页
    连续按两次 HOME 键，确保从任何应用回到桌面首页
    """
    # 第一次 HOME
    self.adb.press_home()
    time.sleep(0.3)

    # 第二次 HOME
    self.adb.press_home()
    time.sleep(0.5)

    return True
```

**原因**:
- 第一次 HOME：如果在应用内部页面，可能只回到应用首页
- 第二次 HOME：确保从应用首页回到系统桌面

### 中文输入

```python
def _execute_input_text(self, step: StepPlan) -> bool:
    text = step.params.get("text", "")

    # 检测是否包含中文
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)

    if has_chinese:
        # 使用 ADBKeyboard 的 broadcast 方式
        cmd = f'adb shell am broadcast -a ADB_INPUT_TEXT --es msg "{text}"'
        subprocess.run(cmd, shell=True)
    else:
        self.adb.input_text(text)
```

---

## Layer 4: 结果验证器 (Verifier)

### 职责

验证操作是否成功，检测阻挡物，提供恢复建议。

### 代码位置

`ai/verifier.py` - `Verifier` 类

### 验证结果数据结构

```python
@dataclass
class VerifyResult:
    verified: bool              # 是否验证通过
    confidence: float           # 置信度 (0-1)
    current_state: str          # 当前状态描述
    matches_expected: bool      # 是否匹配期望状态
    screen_changed: bool        # 屏幕是否有变化
    change_description: str     # 变化描述
    blocker: Optional[Blocker]  # 检测到的阻挡物
    suggestion: SuggestionAction  # 建议动作
    suggestion_detail: str      # 建议详情
```

### 建议动作类型

```python
class SuggestionAction(Enum):
    CONTINUE = "continue"    # 验证通过，继续下一步
    RETRY = "retry"          # 重试当前步骤
    SKIP = "skip"            # 跳过当前步骤
    WAIT = "wait"            # 等待一段时间
    DISMISS = "dismiss"      # 关闭弹窗
    ABORT = "abort"          # 中止任务
    REPLAN = "replan"        # 重新规划
```

### 阻挡物检测

```python
class BlockerType(Enum):
    NONE = "none"
    POPUP = "popup"           # 普通弹窗
    DIALOG = "dialog"         # 对话框
    PERMISSION = "permission" # 权限请求
    AD = "ad"                 # 广告
    ERROR = "error"           # 错误提示
    LOADING = "loading"       # 加载中
    KEYBOARD = "keyboard"     # 键盘弹出
    UNKNOWN = "unknown"

@dataclass
class Blocker:
    type: BlockerType
    description: str
    dismiss_suggestion: Optional[DismissSuggestion] = None

@dataclass
class DismissSuggestion:
    action: str                    # tap / press_key / swipe
    target_ref: Optional[str]      # 参考图名称或 dynamic:描述
    description: str
    keycode: Optional[int] = None
```

### 验证方式

#### 方式 1: 参考图验证

```python
def verify_with_reference(
    self,
    expected_ref: Image.Image,
    current_screenshot: Image.Image,
    success_condition: Optional[str] = None
) -> VerifyResult:
    """使用参考图验证当前状态"""
```

#### 方式 2: 描述验证

```python
def verify_with_description(
    self,
    current_screenshot: Image.Image,
    expected_description: str,
    previous_screenshot: Optional[Image.Image] = None
) -> VerifyResult:
    """使用文字描述验证当前状态"""
```

#### 方式 3: 快速变化检测

```python
def quick_check(
    self,
    before_screenshot: Image.Image,
    after_screenshot: Image.Image,
    expected_change: str
) -> Tuple[bool, str]:
    """快速检查操作是否有效果"""
    # 先用像素比较，再用 LLM 确认
```

---

## 模块路由系统

系统采用**模块化架构**，每个应用（微信、Chrome、系统设置等）都有独立的模块，任务执行前先路由到对应模块。

### 模块目录结构

```
apps/
├── __init__.py              # ModuleRegistry 注册表
├── base.py                  # AppHandler 基类
├── wechat/
│   ├── config.yaml          # 模块配置（包名、关键词）
│   ├── tasks.yaml           # 预定义任务模板
│   ├── handler.py           # 自定义处理器（可选）
│   ├── images/              # 模块参考图
│   │   └── aliases.yaml     # 中文别名
│   └── prompts/
│       └── planner.txt      # 模块专属 planner prompt
├── chrome/
│   └── ...
└── system/
    └── ...
```

### 路由流程

```
用户任务: "打开微信给张三发消息"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ModuleRegistry.route(task)                                   │
│                                                              │
│ 评分算法:                                                    │
│   1. 任务模板匹配 (权重 0.5) - 匹配 tasks.yaml 中的 pattern │
│   2. 关键词匹配 (权重 0.4) - 匹配 config.yaml 中的 keywords │
│   3. 包名匹配 (权重 0.1) - 任务中包含包名                   │
│                                                              │
│ 选择得分最高的模块                                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 加载模块的 AppHandler                                        │
│   - 加载 config.yaml                                        │
│   - 加载 images/ 参考图                                     │
│   - 加载 prompts/planner.txt                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ handler.plan(task) - 尝试模板匹配                            │
│   - 匹配成功 → 使用预定义步骤（快速、免费）                 │
│   - 匹配失败 → 调用 AI planner（灵活、需 API）              │
└─────────────────────────────────────────────────────────────┘
```

### 预定义模板 vs AI 规划

| 类型 | 使用场景 | 示例 |
|------|---------|------|
| **预定义模板** | 简单、固定的系统级操作 | 打开微信、返回桌面、音量调节 |
| **AI 规划** | 复杂、动态的交互操作 | 发消息、搜索、多步骤任务 |

### 代码位置

- `apps/__init__.py` - `ModuleRegistry` 类
- `apps/base.py` - `AppHandler` 基类和 `DefaultHandler`

---

## Replan 重规划机制

当执行过程中遇到意外情况，系统可以重新规划后续步骤。

### 触发 Replan 的场景

1. **进入意外界面**：点击后进入非预期页面
2. **多次重试失败**：某个步骤多次执行都失败
3. **阻挡物无法处理**：遇到无法自动关闭的弹窗
4. **状态不匹配**：当前界面与预期差异太大

### Replan 执行流程

```
验证结果: suggestion = REPLAN
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ planner.replan(                                              │
│     original_task,          # 原始任务                      │
│     current_screenshot,     # 当前截图                      │
│     failed_step,            # 失败的步骤                    │
│     failure_reason,         # 失败原因                      │
│     executed_steps          # 已执行的步骤                  │
│ )                                                            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ AI 分析当前状态，生成新的步骤计划                            │
│   - 考虑已执行的步骤                                        │
│   - 考虑当前屏幕状态                                        │
│   - 生成从当前状态到目标状态的新路径                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
用新计划替换剩余步骤，继续执行
```

### 代码示例

```python
if verify_result.suggestion == SuggestionAction.REPLAN:
    new_plan = self.planner.replan(
        original_task=task,
        current_screenshot=self._capture_screenshot(),
        failed_step=step,
        failure_reason=result.error_message,
        executed_steps=executed_steps
    )
    # 用新计划替换剩余步骤
    remaining_steps = new_plan.steps
```

---

## 任务执行器 (TaskRunner)

### 职责

整合 Planner、Locator、Executor、Verifier，执行完整任务流程。

### 代码位置

`core/task_runner.py` - `TaskRunner` 类

### 初始化

```python
runner = TaskRunner(
    adb=ADBController("192.168.1.100:5555"),
    llm_config=LLMConfig.from_env(),
    assets_dir=Path("assets"),
    temp_dir=Path("temp")
)
```

### 执行任务

```python
result = runner.run("给张三发微信消息说你好")

# 或简单模式
success = runner.run_simple("打开微信")
```

### 执行结果

```python
@dataclass
class TaskResult:
    status: TaskStatus          # PENDING/RUNNING/SUCCESS/FAILED/ABORTED
    plan: Optional[TaskPlan]
    step_results: List[StepResult]
    total_time: float
    error_message: str

@dataclass
class StepResult:
    step: StepPlan
    status: StepStatus          # PENDING/RUNNING/SUCCESS/FAILED/SKIPPED
    start_time: float
    end_time: float
    retry_count: int
    error_message: str
    screenshot_before: Optional[Image]
    screenshot_after: Optional[Image]
    verify_result: Optional[VerifyResult]
```

### 执行流程

```
1. 截取当前屏幕
2. 调用 Planner 生成任务计划
3. 对每个步骤循环执行:
   a. 执行前等待 (wait_before)
   b. 截取执行前截图
   c. 重试循环 (最多 retry+1 次):
      - 定位目标 (_locate_with_fallback)
      - 执行动作 (_execute_action)
      - 执行后等待 (wait_after)
      - 截取执行后截图
      - 验证结果 (_verify_step)
      - 根据验证结果决定下一步
   d. 记录步骤结果
4. 返回任务结果
```

---

## Fallback 机制详解

### 什么是 Fallback？

当定位目标元素失败时，执行备选动作（如滑动屏幕），然后重新尝试定位。

### 代码实现

```python
def _locate_with_fallback(
    self,
    step: StepPlan,
    screenshot: Optional[Image.Image],
    max_fallback_attempts: int = 3
) -> Optional[tuple]:
    """定位目标元素，失败则尝试 fallback"""

    # 1. 首次尝试定位
    coords = self._locate_target(step, screenshot)
    if coords is not None:
        return coords

    # 2. 检查是否有 fallback 配置
    if not step.fallback:
        self._log("定位失败，无 fallback 配置")
        return None

    self._log(f"定位失败，尝试 fallback: {step.fallback}")

    # 3. fallback 循环
    for attempt in range(max_fallback_attempts):
        self._log(f"Fallback 尝试 {attempt + 1}/{max_fallback_attempts}")

        # 执行 fallback 动作
        fallback_success = self._execute_fallback(step.fallback)
        if not fallback_success:
            continue

        # 等待屏幕稳定
        time.sleep(0.5)

        # 重新截图并定位
        new_screenshot = self._capture_screenshot()
        coords = self._locate_target(step, new_screenshot)

        if coords is not None:
            self._log("Fallback 成功，定位到目标")
            return coords

    self._log(f"达到最大 fallback 尝试次数")
    return None
```

### Fallback 动作类型

```python
def _execute_fallback(self, fallback: Dict) -> bool:
    action = fallback.get("action", "")
    params = fallback.get("params", {})

    if action == "swipe":
        direction = params.get("direction", "up")
        return self._execute_swipe_direction(direction)

    elif action == "tap":
        # 需要先定位再点击
        ...

    elif action == "press_key":
        keycode = params.get("keycode", 4)  # 默认 BACK
        return self.adb.input_keyevent(keycode)

    elif action == "wait":
        duration = params.get("duration", 1000)
        time.sleep(duration / 1000)
        return True
```

### Fallback 配置示例

```json
{
  "step": 1,
  "action": "tap",
  "target_ref": "wechat",
  "fallback": {
    "action": "swipe",
    "params": {"direction": "left"},
    "description": "左滑桌面查找微信图标"
  }
}
```

### 使用场景

| 场景 | Fallback 配置 |
|------|---------------|
| 图标不在当前桌面页 | `{"action": "swipe", "params": {"direction": "left"}}` |
| 列表项需要滚动 | `{"action": "swipe", "params": {"direction": "up"}}` |
| 需要返回后重试 | `{"action": "press_key", "params": {"keycode": 4}}` |
| 等待加载完成 | `{"action": "wait", "params": {"duration": 2000}}` |

---

## 任务类型详细流程

### 类型 1: 打开应用

**任务**: "打开微信"

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 检查当前状态                                         │
├─────────────────────────────────────────────────────────────┤
│ Planner 分析截图:                                           │
│ - 是否已在微信? → 任务完成                                  │
│ - 是否在桌面? → Step 2                                      │
│ - 在其他应用? → 先执行 go_home                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1.5: 返回桌面 (go_home)                                │
├─────────────────────────────────────────────────────────────┤
│ press_key(3)  // 第一次 HOME                                │
│ wait(300ms)                                                  │
│ press_key(3)  // 第二次 HOME                                │
│ wait(500ms)                                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: 定位微信图标                                         │
├─────────────────────────────────────────────────────────────┤
│ 1. find_element_by_image(wechat.png, screenshot)            │
│    ↓ 找到 → Step 3                                          │
│    ↓ 未找到 → 执行 fallback                                 │
│                                                              │
│ 2. fallback: swipe left                                      │
│    → 重新截图 → 再次定位                                    │
│    → 最多尝试 3 次                                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 点击微信图标                                         │
├─────────────────────────────────────────────────────────────┤
│ adb.tap(x, y)                                                │
│ wait(1000ms)                                                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 验证结果                                             │
├─────────────────────────────────────────────────────────────┤
│ Verifier 检查:                                               │
│ - 匹配微信主界面? → 成功 ✓                                  │
│ - 检测到弹窗? → 处理弹窗后重验                              │
│ - 屏幕无变化? → 重试点击                                    │
└─────────────────────────────────────────────────────────────┘
```

### 类型 2: 发送消息

**任务**: "给张三发微信消息说你好"

```
Phase 1: 打开微信并进入聊天
  → (参考类型1流程)

Phase 2: 搜索联系人
  Step: tap wechat_search / "dynamic:搜索框"
  Step: input_text "张三"
  Step: wait 1000ms

Phase 3: 选择联系人
  Step: tap "dynamic:搜索结果中的张三"
  Verify: 进入聊天窗口

Phase 4: 发送消息
  Step: tap "dynamic:底部输入框"
  Step: input_text "你好"
  Step: tap send_button
  Verify: 消息显示在聊天记录中
```

---

## 错误处理与恢复

### 错误类型

| 类型 | 描述 | 恢复策略 |
|------|------|----------|
| 定位失败 | 无法找到目标元素 | 执行 fallback / 报告 |
| 操作无效 | 屏幕无变化 | 调整坐标重试 |
| 状态异常 | 进入非预期界面 | replan |
| 弹窗阻挡 | 出现意外弹窗 | dismiss |
| 网络错误 | 网络相关失败 | 等待重试 |

### 弹窗处理

```python
def _handle_blocker(self, blocker: Blocker) -> bool:
    if blocker.dismiss_suggestion is None:
        # 默认按返回键
        self.adb.press_back()
        return True

    suggestion = blocker.dismiss_suggestion

    if suggestion.action == "tap":
        # 定位并点击关闭按钮
        coords = self.locator.find_element(screenshot, suggestion.target_ref)
        if coords:
            self.adb.tap(coords[0], coords[1])

    elif suggestion.action == "press_key":
        self.adb.input_keyevent(suggestion.keycode or 4)

    return True
```

### 重新规划

当步骤失败且 Verifier 建议 REPLAN 时：

```python
if result.verify_result.suggestion == SuggestionAction.REPLAN:
    new_plan = self.planner.replan(
        original_task=task,
        current_screenshot=self._capture_screenshot(),
        failed_step=step,
        failure_reason=result.error_message,
        executed_steps=executed_steps
    )
    # 用新计划替换剩余步骤
```

---

## 配置与环境

### 环境变量 (.env)

```bash
# LLM 提供商: claude / openai / custom
LLM_PROVIDER=custom

# Custom LLM 配置 (推荐使用 OpenRouter + Gemini)
CUSTOM_LLM_API_KEY=sk-or-v1-xxx
CUSTOM_LLM_BASE_URL=https://openrouter.ai/api/v1
CUSTOM_LLM_MODEL=google/gemini-2.5-flash-preview

# 其他配置
ADB_PATH=adb
OPERATION_DELAY=0.3
```

### LLMConfig 使用

```python
from config import LLMConfig, get_preset_config

# 方式1: 从环境变量加载
config = LLMConfig.from_env()

# 方式2: 使用预设
config = get_preset_config("deepseek", api_key="sk-xxx")

# 方式3: 自定义
config = LLMConfig.custom(
    api_key="sk-xxx",
    base_url="https://api.example.com/v1",
    model="my-model"
)
```

---

## 测试指南

### 不需要手机的测试

```bash
# 测试 AssetsManager
python test_planner.py

# 测试任务规划 (需要截图和API)
python test_planner.py plan screenshot.png "打开微信"

# 测试元素定位
python test_planner.py locate screenshot.png "微信图标"

# 测试双图匹配
python test_planner.py match assets/icons/wechat.png screenshot.png

# 测试验证器
python test_planner.py verify screenshot.png "已打开微信主界面"

# 完整流程测试
python test_planner.py flow screenshot.png "打开微信"
```

### 需要手机的测试

```bash
# 连接手机
adb connect 192.168.1.100:5555

# 运行完整任务
python -c "
from core import TaskRunner, ADBController

adb = ADBController('192.168.1.100:5555')
adb.connect()

runner = TaskRunner(adb)
result = runner.run('打开微信')
print(f'结果: {result.status}')
"
```

---

## 文件结构

```
remote/
├── ai/
│   ├── __init__.py
│   ├── vision_agent.py      # Locator 实现
│   ├── planner.py           # Planner + AssetsManager
│   └── verifier.py          # Verifier 实现
│
├── assets/
│   ├── icons/               # 应用图标
│   ├── ui/                  # UI 元素
│   ├── states/              # 状态验证图
│   └── index.json           # 参考图索引
│
├── core/
│   ├── __init__.py
│   ├── adb_controller.py    # Executor 实现
│   └── task_runner.py       # TaskRunner 整合器
│
├── docs/
│   ├── one_shot_design.md   # 本文档
│   ├── setup_guide.md       # 手机配置指南
│   └── test_guide.md        # 测试指南
│
├── temp/                    # 临时文件目录
├── config.py                # 配置管理
├── test_planner.py          # 测试脚本
├── test_vision.py           # 视觉测试脚本
├── requirements.txt         # 依赖
└── .env                     # 环境变量
```

---

## 总结

VisionAgent 采用 **4 层架构** 实现 Android 自动化：

1. **Planner**: 将自然语言任务分解为步骤序列，指定参考图和 fallback
2. **Locator**: 优先使用双图匹配定位，备选描述定位，支持 fallback 重试
3. **Executor**: 通过 ADB 执行具体操作，特殊处理 go_home 和中文输入
4. **Verifier**: 验证操作结果，检测阻挡物，提供恢复建议

**核心特性**：
- One-Shot Object Detection：参考图 + 截图精准定位
- Fallback 机制：定位失败自动执行备选动作后重试
- 阻挡物检测：自动识别和处理弹窗
- 错误恢复：支持重试、重新规划、中止等策略
