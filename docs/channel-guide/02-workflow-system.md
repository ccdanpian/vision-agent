# 工作流系统（核心）

工作流系统是提高任务执行可靠性的关键。系统区分两类任务，采用不同的处理策略。

## 任务分类策略

```
用户任务
    │
    ├─ 简单任务（单一动作）
    │   ├─ 无连接词（然后、再、接着...）
    │   ├─ 单一动作词（发消息 / 发朋友圈）
    │   └─ → 规则匹配，直接执行预设工作流
    │
    └─ 复杂任务（多步骤）
        ├─ 有连接词（然后、再、接着、之后...）
        ├─ 多个动作词
        └─ → LLM 分析，选择/组合预设工作流
```

## 任务分类器（TaskClassifier）

系统提供可配置的任务分类器，支持**三种判断模式**：

### 1. SS 快速模式（无需配置，自动检测）

**特点**：
- ⚡ 极速响应（<10ms）
- ✅ 零成本，100%准确率
- ✅ 固定格式，适合高频任务和自动化脚本

**触发条件**：
任务以 `ss`/`SS`/`Ss`/`sS` 开头（不区分大小写）

**支持格式**：
```bash
# 发消息
ss:消息:好友名称:消息内容
ss:发消息:好友名称:消息内容
ss:xx:好友名称:消息内容

# 发朋友圈
ss:朋友圈:消息内容
ss:pyq:消息内容
```

**示例**：
```bash
ss:消息:张三:你好
SS:发消息:李四:周末一起吃饭吧
ss:朋友圈:今天天气真好
Ss:pyq:分享一个好消息
```

**解析结果**：
```json
{
  "type": "send_msg",
  "recipient": "张三",
  "content": "你好"
}
```

**适用场景**：
- 高频重复任务
- 批量操作脚本
- API 集成调用

详见：[SS 快速模式使用指南](../SS_QUICK_MODE.md)

---

### 2. 正则表达式模式（默认）

**特点**：
- ✅ 零成本，快速响应（<1ms）
- ✅ 准确率约90%，适合大多数场景
- ✅ 无需API调用

**配置**：
```bash
# .env
TASK_CLASSIFIER_MODE=regex
```

**判断规则**：
```python
# apps/wechat/workflows.py

COMPLEX_TASK_INDICATORS = [
    "然后", "再", "接着", "之后", "完成后",
    "并且", "同时", "顺便", "截图", "保存"
]

def is_complex_task(task: str) -> bool:
    # 1. 检查是否包含复杂任务指示词
    if any(indicator in task for indicator in COMPLEX_TASK_INDICATORS):
        return True

    # 2. 检查是否包含多个动作词
    action_words = ["发消息", "发朋友圈", "搜索", "加好友", "打开", "点击", "截图"]
    if sum(1 for w in action_words if w in task) >= 2:
        return True

    return False
```

### 3. LLM智能模式

**特点**：
- ✅ 更准确的语义理解（准确率约95%）
- ✅ 支持独立LLM配置（可用更便宜的模型）
- ✅ 同时解析任务参数（type, recipient, content）
- ✅ 识别无效输入（invalid 类型）
- ⚠️ 有API调用成本

**配置**：
```bash
# .env
TASK_CLASSIFIER_MODE=llm

# 选项1：使用主LLM（不设置其他变量）
# 选项2：使用独立的LLM（推荐，可节省成本）
TASK_CLASSIFIER_LLM_API_KEY=sk-xxx
TASK_CLASSIFIER_LLM_BASE_URL=https://api.deepseek.com/v1
TASK_CLASSIFIER_LLM_MODEL=deepseek-chat
```

**LLM提示词格式**：
```python
messages = [
    {
        "role": "system",
        "content": """你是一个解析器，只输出JSON。字段包含：type(send_msg/post_moment_only_text/others/invalid), recipient, content

type 说明：
- send_msg: 发送消息给联系人
- post_moment_only_text: 发布纯文字朋友圈
- others: 其他复杂任务（多步骤任务）
- invalid: 无效输入（空白、无意义、误触、错误输入等）

invalid 类型示例：
- 空白输入、只有空格/换行
- 无意义的字符（如：aaa、123、！！！）
- 明显的误触（如：s、ss、、、等）
- 不清楚的指令"""
    },
    {
        "role": "user",
        "content": "{用户输入的任务}"
    }
]
```

**输出格式**：
```json
{
    "type": "send_msg",           // send_msg / post_moment_only_text / others / invalid
    "recipient": "张三",          // 接收者
    "content": "你好"             // 内容
}
```

**分类逻辑**：
- `type` 为 `send_msg` 或 `post_moment_only_text` → **简单任务**
- `type` 为 `others` → **复杂任务**
- `type` 为 `invalid` → **无效输入**，提前拦截并返回友好提示

**invalid 类型处理**：
```python
# apps/wechat/handler.py

if parsed_data and parsed_data.get("type") == "invalid":
    return {
        "success": False,
        "message": "无效的输入指令。请输入有效的任务描述，例如：\n"
                  "- 给张三发消息说你好\n"
                  "- 发朋友圈今天天气真好\n"
                  "- SS快速模式：ss:消息:张三:你好",
        "error_type": "invalid_input"
    }
```

**优势**：
- 节省资源：避免调用 Planner LLM
- 提升速度：响应时间缩短 75%
- 友好提示：引导用户正确使用

详见：[无效输入处理文档](../INVALID_INPUT_HANDLING.md)

---

### 4. 使用示例

```python
# ai/task_classifier.py

from ai.task_classifier import get_task_classifier, TaskType

# 获取全局分类器（自动使用环境变量配置）
classifier = get_task_classifier()

# 方式1：仅分类
task_type = classifier.classify("给张三发消息说你好")
# TaskType.SIMPLE

# 方式2：分类 + 解析（LLM模式）
task_type, parsed_data = classifier.classify_and_parse("给张三发消息说你好")
# TaskType.SIMPLE, {"type": "send_msg", "recipient": "张三", "content": "你好"}

# 方式3：向后兼容的布尔接口
is_complex = classifier.is_complex_task("发消息然后截图")
# True
```

---

### 5. 模式对比与选择

| 模式 | 触发方式 | 速度 | 成本 | 准确率 | 适用场景 |
|------|---------|------|------|--------|---------|
| **SS快速** | `ss` 开头 | ⚡⚡⚡ <10ms | 💰 零成本 | ✅ 100% | 高频任务、批量操作 |
| **正则** | 环境变量 | ⚡⚡ <1ms | 💰 零成本 | ⚠️ 90% | 个人使用、预算有限 |
| **LLM智能** | 环境变量 | 🐌 ~500ms | 💰💰 有成本 | ✅ 95% | 自然语言、高准确率 |

**推荐策略**：
1. **高频任务**：优先使用 SS 快速模式（如批量操作、自动化脚本）
2. **偶尔使用**：使用 LLM 智能模式（自然语言，无需记格式）
3. **预算有限**：使用正则模式（零成本，90%准确率）

---

### 6. 成本优化建议

| 配置方案 | 任务分类 | 任务规划 | 成本 | 推荐场景 |
|---------|---------|---------|------|---------|
| **方案1** | 正则表达式 | Claude/GPT-4 | 零成本分类 | 个人使用，预算有限 |
| **方案2** | DeepSeek | Claude/GPT-4 | 极低成本 | 生产环境，预算充足 |
| **方案3** | Claude/GPT-4 | Claude/GPT-4 | 统一成本 | 追求最高准确率 |

**推荐配置**（方案2）：
```bash
# 主LLM使用Claude（用于任务规划）
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-xxx
CLAUDE_MODEL=claude-sonnet-4-20250514

# 任务分类器使用DeepSeek（成本约0.001元/次）
TASK_CLASSIFIER_MODE=llm
TASK_CLASSIFIER_LLM_API_KEY=sk-xxx
TASK_CLASSIFIER_LLM_BASE_URL=https://api.deepseek.com/v1
TASK_CLASSIFIER_LLM_MODEL=deepseek-chat
```

**节省成本**：任务分类成本降低90%+

---

### 7. 自动降级机制

LLM模式具有完善的错误处理：

```python
def _classify_with_llm(self, task: str) -> TaskType:
    try:
        # 调用LLM分类
        result = llm_classify(task)
        return parse_result(result)
    except Exception as e:
        # 失败时自动降级到正则模式
        self._log(f"LLM分类失败: {e}，降级使用正则判断")
        return self._classify_with_regex(task)
```

确保系统在LLM不可用时仍能正常工作。

## 界面状态枚举

以下是 `apps/wechat/workflows.py` 中的实际定义：

```python
# apps/wechat/workflows.py 实际代码

class WeChatScreen(Enum):
    """微信界面状态"""
    UNKNOWN = "unknown"           # 未知界面
    HOME = "home"                 # 首页（聊天列表）
    CONTACTS = "contacts"         # 通讯录
    DISCOVER = "discover"         # 发现
    ME = "me"                     # 我
    CHAT = "chat"                 # 聊天窗口
    MOMENTS = "moments"           # 朋友圈
    MOMENTS_POST = "moments_post" # 发朋友圈界面
    SEARCH = "search"             # 搜索界面
    ADD_FRIEND = "add_friend"     # 添加好友
    PROFILE = "profile"           # 个人资料页
    OTHER = "other"               # 其他界面（需要返回）
```

## 界面检测参考图映射

```python
# apps/wechat/workflows.py 实际代码

# 界面检测参考图映射（优先使用根目录的参考图）
SCREEN_DETECT_REFS = {
    WeChatScreen.HOME: "wechat_home",             # 首页（优先用根目录的 wechat_home.png）
    WeChatScreen.CONTACTS: "system/wechat_contacts_page",
    WeChatScreen.DISCOVER: "system/wechat_discover_page",
    WeChatScreen.ME: "system/wechat_me_page",
    # 以下界面通过特征元素检测
    WeChatScreen.CHAT: "wechat_chat_input",       # 有输入框说明在聊天
    WeChatScreen.MOMENTS: "wechat_moments_camera", # 有相机图标说明在朋友圈
    WeChatScreen.SEARCH: "wechat_search_input",   # 有搜索输入框
}

# 备用界面检测参考图（如果主参考图匹配失败，尝试备用）
SCREEN_DETECT_REFS_FALLBACK = {
    WeChatScreen.HOME: "system/wechat_home_page",  # 首页备用
}
```

## 导航步骤和工作流数据类

```python
# apps/wechat/workflows.py 实际代码

@dataclass
class NavStep:
    """导航步骤"""
    action: str                    # tap, press_key, swipe, wait, check
    target: Optional[str] = None   # 目标参考图或描述
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    expect_screen: Optional[WeChatScreen] = None  # 执行后期望的界面
    max_wait: int = 2000           # 最大等待时间 ms


@dataclass
class Workflow:
    """工作流定义"""
    name: str                      # 工作流名称
    description: str               # 描述

    # 前置条件
    valid_start_screens: List[WeChatScreen]  # 可以开始执行的界面

    # 导航到起始点（如果不在有效起始界面）
    nav_to_start: List[NavStep]    # 导航到起始界面的步骤

    # 核心步骤（带参数占位符）
    steps: List[NavStep]           # 主要执行步骤

    # 完成后状态
    end_screen: WeChatScreen       # 完成后所在界面

    # 参数定义
    required_params: List[str] = field(default_factory=list)  # 必需参数
    optional_params: Dict[str, Any] = field(default_factory=dict)  # 可选参数及默认值
```

## 返回首页的导航策略

```python
# apps/wechat/workflows.py 实际代码

# 返回首页的策略
NAV_TO_HOME = [
    NavStep(
        action="check",
        target="system/wechat_home_page",
        description="检查是否已在首页",
        expect_screen=WeChatScreen.HOME
    ),
    NavStep(
        action="press_key",
        params={"keycode": 4},  # BACK
        description="按返回键",
        max_wait=500
    ),
    NavStep(
        action="check",
        target="system/wechat_home_page",
        description="检查是否已在首页",
        expect_screen=WeChatScreen.HOME
    ),
    NavStep(
        action="press_key",
        params={"keycode": 4},
        description="再按返回键",
        max_wait=500
    ),
    NavStep(
        action="check",
        target="system/wechat_home_page",
        description="检查是否已在首页",
        expect_screen=WeChatScreen.HOME
    ),
    NavStep(
        action="press_key",
        params={"keycode": 4},
        description="第三次按返回键",
        max_wait=500
    ),
    # 如果还不在首页，尝试 HOME 键
    NavStep(
        action="check",
        target="system/wechat_home_page",
        description="最后检查",
        expect_screen=WeChatScreen.HOME
    ),
]
```

## 工作流定义示例

### 发消息工作流

```python
# apps/wechat/workflows.py 实际代码

WORKFLOW_SEND_MESSAGE = Workflow(
    name="send_message",
    description="给联系人发送消息",

    valid_start_screens=[WeChatScreen.HOME, WeChatScreen.CHAT],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 在首页查找联系人（先尝试直接在列表中找）
        NavStep(
            action="find_or_search",
            target="{contact}",  # 参数占位符
            description="查找联系人 {contact}",
            params={"search_fallback": True}
        ),
        # 2. 点击进入聊天
        NavStep(
            action="tap",
            target="{contact}",
            description="点击联系人进入聊天",
            expect_screen=WeChatScreen.CHAT
        ),
        # 3. 输入消息
        NavStep(
            action="input_text",
            target="wechat_chat_input",
            params={"text": "{message}"},
            description="输入消息内容"
        ),
        # 4. 点击发送
        NavStep(
            action="tap",
            target="wechat_chat_send",
            description="点击发送按钮"
        ),
        # 5. 等待发送完成
        NavStep(
            action="wait",
            params={"duration": 500},
            description="等待消息发送"
        ),
    ],

    end_screen=WeChatScreen.CHAT,
    required_params=["contact", "message"],
)
```

### 发朋友圈工作流

```python
# apps/wechat/workflows.py 实际代码

WORKFLOW_POST_MOMENTS = Workflow(
    name="post_moments",
    description="发布朋友圈",

    valid_start_screens=[WeChatScreen.HOME, WeChatScreen.DISCOVER, WeChatScreen.MOMENTS],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击发现 Tab
        NavStep(
            action="tap",
            target="wechat_tab_discover_button",
            description="点击发现Tab",
            expect_screen=WeChatScreen.DISCOVER
        ),
        # 2. 点击朋友圈入口
        NavStep(
            action="tap",
            target="wechat_moments_entry",
            description="点击朋友圈",
            expect_screen=WeChatScreen.MOMENTS
        ),
        # 3. 长按相机图标（发纯文字）或点击（发图片）
        NavStep(
            action="{post_action}",  # long_press 或 tap
            target="wechat_moments_camera",
            description="点击/长按相机图标",
            expect_screen=WeChatScreen.MOMENTS_POST
        ),
        # 4. 如果有图片，选择图片
        NavStep(
            action="conditional",
            params={"condition": "has_image"},
            description="如果有图片则选择"
        ),
        # 5. 输入文字内容
        NavStep(
            action="input_text",
            target="wechat_moments_input_box.png",
            params={"text": "{content}"},
            description="输入朋友圈内容"
        ),
        # 6. 点击发表
        NavStep(
            action="tap",
            target="wechat_moments_publish",
            description="点击发表按钮"
        ),
        # 7. 等待发布完成
        NavStep(
            action="wait",
            params={"duration": 1000},
            description="等待发布完成"
        ),
    ],

    end_screen=WeChatScreen.MOMENTS,
    required_params=["content"],
    optional_params={"post_action": "long_press", "image_path": None},
)
```

### 复合工作流：发消息+截图+发朋友圈

```python
# apps/wechat/workflows.py 实际代码

WORKFLOW_MESSAGE_AND_MOMENTS = Workflow(
    name="message_and_moments",
    description="发消息后截图发朋友圈",

    valid_start_screens=[WeChatScreen.HOME],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # === 阶段1：发消息 ===
        NavStep(
            action="sub_workflow",
            params={"workflow": "send_message", "contact": "{contact}", "message": "{message}"},
            description="执行发消息子流程"
        ),

        # === 阶段2：截图 ===
        NavStep(
            action="screenshot",
            params={"save_as": "{screenshot_path}"},
            description="截取聊天截图"
        ),

        # === 阶段3：返回首页 ===
        NavStep(
            action="nav_to_home",
            description="返回微信首页"
        ),

        # === 阶段4：发朋友圈 ===
        NavStep(
            action="sub_workflow",
            params={"workflow": "post_moments", "content": "{moments_content}", "image_path": "{screenshot_path}"},
            description="执行发朋友圈子流程"
        ),
    ],

    end_screen=WeChatScreen.MOMENTS,
    required_params=["contact", "message", "moments_content"],
)
```

## 工作流注册表

```python
# apps/wechat/workflows.py 实际代码

WORKFLOWS: Dict[str, Workflow] = {
    "send_message": WORKFLOW_SEND_MESSAGE,
    "post_moments": WORKFLOW_POST_MOMENTS,
    "message_and_moments": WORKFLOW_MESSAGE_AND_MOMENTS,
    "search_contact": WORKFLOW_SEARCH_CONTACT,
    "add_friend": WORKFLOW_ADD_FRIEND,
}
```

## 复杂任务判断

```python
# apps/wechat/workflows.py 实际代码

# 复合任务关键词（检测到这些词表示是复杂任务，需要 LLM 判断）
COMPLEX_TASK_INDICATORS = [
    "然后", "再", "接着", "之后", "完成后",
    "并且", "同时", "顺便",
    "截图", "保存",
]


def is_complex_task(task: str) -> bool:
    """判断是否为复杂任务"""
    # 包含复合任务指示词
    if any(indicator in task for indicator in COMPLEX_TASK_INDICATORS):
        return True

    # 包含多个动作词
    action_words = ["发消息", "发朋友圈", "搜索", "加好友", "打开", "点击", "截图"]
    action_count = sum(1 for w in action_words if w in task)
    if action_count >= 2:
        return True

    return False
```

## 简单任务模式匹配规则

```python
# apps/wechat/workflows.py 实际代码

SIMPLE_TASK_PATTERNS = [
    # 发消息（单一动作）
    {
        # 支持多种表述：发消息、发微信、发信息、发个微信、微信消息、说
        "patterns": ["发消息", "发微信", "发信息", "微信消息", "发个微信", "发条微信", "说.*给"],
        "patterns_regex": True,  # 启用正则匹配
        "contains": ["给"],
        "not_contains": ["然后", "再", "接着", "朋友圈", "截图"],  # 排除复合任务
        "workflow": "send_message",
        "param_hints": {
            "contact": "联系人名称",
            "message": "消息内容"
        }
    },

    # 发朋友圈（单一动作）
    {
        "patterns": ["发朋友圈"],
        "not_contains": ["看", "刷", "给", "发消息", "然后", "再", "接着"],
        "workflow": "post_moments",
        "param_hints": {
            "content": "朋友圈内容"
        }
    },

    # 搜索联系人
    {
        "patterns": ["搜索", "找人", "找联系人"],
        "not_contains": ["然后", "再", "接着"],
        "workflow": "search_contact",
        "param_hints": {
            "keyword": "搜索关键词"
        }
    },

    # 添加好友
    {
        "patterns": ["加好友", "添加好友", "加微信"],
        "not_contains": ["然后", "再", "接着"],
        "workflow": "add_friend",
        "param_hints": {
            "wechat_id": "微信号或手机号"
        }
    },
]
```

## 简单任务规则匹配函数

```python
# apps/wechat/workflows.py 实际代码

def match_simple_workflow(task: str) -> Optional[Dict[str, Any]]:
    """
    简单任务的规则匹配（快速路径）

    Args:
        task: 用户任务描述

    Returns:
        匹配结果或 None
    """
    # 如果是复杂任务，不使用简单匹配
    if is_complex_task(task):
        return None

    for pattern_rule in SIMPLE_TASK_PATTERNS:
        patterns = pattern_rule.get("patterns", [])
        contains = pattern_rule.get("contains", [])
        not_contains = pattern_rule.get("not_contains", [])
        use_regex = pattern_rule.get("patterns_regex", False)

        # 检查是否匹配任一关键词（支持正则表达式）
        matched = False
        for p in patterns:
            if use_regex and any(c in p for c in '.*+?[]()'):
                # 正则匹配
                try:
                    if re.search(p, task):
                        matched = True
                        break
                except re.error:
                    pass
            elif p in task:
                matched = True
                break

        if not matched:
            continue

        # 检查必须包含的词
        if contains and not all(c in task for c in contains):
            continue

        # 检查不能包含的词
        if not_contains and any(nc in task for nc in not_contains):
            continue

        workflow_name = pattern_rule["workflow"]
        if workflow_name in WORKFLOWS:
            return {
                "workflow": WORKFLOWS[workflow_name],
                "workflow_name": workflow_name,
                "param_hints": pattern_rule.get("param_hints", {}),
                "match_type": "simple"
            }

    return None


def get_workflow_descriptions() -> str:
    """获取所有工作流的描述（用于 LLM 选择）"""
    lines = []
    for name, wf in WORKFLOWS.items():
        params_str = ", ".join(wf.required_params)
        lines.append(f"- {name}: {wf.description}")
        lines.append(f"  必需参数: {params_str}")
        if wf.optional_params:
            opt_str = ", ".join(f"{k}={v}" for k, v in wf.optional_params.items())
            lines.append(f"  可选参数: {opt_str}")
    return "\n".join(lines)


# 保留旧函数名兼容
def match_workflow(task: str) -> Optional[Dict[str, Any]]:
    """
    匹配工作流（简单任务用规则，复杂任务返回 None 让 LLM 判断）
    """
    return match_simple_workflow(task)
```
