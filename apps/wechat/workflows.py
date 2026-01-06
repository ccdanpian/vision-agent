"""
apps/wechat/workflows.py
微信工作流定义 - 预定义的任务路径和状态机

每个工作流定义：
- 前置条件检测（当前在哪个界面）
- 导航到目标界面的路径
- 执行核心操作
- 完成后的状态
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from enum import Enum
import re

# 导入任务分类器
from ai.task_classifier import get_task_classifier


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


# ============================================================
# 基础导航工作流
# ============================================================

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


# ============================================================
# 发消息工作流
# ============================================================

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


# ============================================================
# 发朋友圈工作流
# ============================================================

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


# ============================================================
# 复合工作流：发消息 + 截图 + 发朋友圈
# ============================================================

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


# ============================================================
# 搜索联系人工作流
# ============================================================

WORKFLOW_SEARCH_CONTACT = Workflow(
    name="search_contact",
    description="搜索联系人",

    valid_start_screens=[WeChatScreen.HOME],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击搜索按钮
        NavStep(
            action="tap",
            target="wechat_search_button",
            description="点击搜索按钮",
            expect_screen=WeChatScreen.SEARCH
        ),
        # 2. 输入搜索关键词
        NavStep(
            action="input_text",
            target="wechat_search_input",
            params={"text": "{keyword}"},
            description="输入搜索关键词"
        ),
        # 3. 等待搜索结果
        NavStep(
            action="wait",
            params={"duration": 1000},
            description="等待搜索结果"
        ),
        # 4. 点击搜索结果中的联系人
        NavStep(
            action="tap",
            target="dynamic:搜索结果中的{keyword}",
            description="点击搜索结果"
        ),
    ],

    end_screen=WeChatScreen.CHAT,
    required_params=["keyword"],
)


# ============================================================
# 添加好友工作流
# ============================================================

WORKFLOW_ADD_FRIEND = Workflow(
    name="add_friend",
    description="添加新好友",

    valid_start_screens=[WeChatScreen.HOME],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击 + 号
        NavStep(
            action="tap",
            target="wechat_add_button",
            description="点击+号按钮"
        ),
        # 2. 点击添加朋友
        NavStep(
            action="tap",
            target="wechat_menu_add_friend",
            description="点击添加朋友",
            expect_screen=WeChatScreen.ADD_FRIEND
        ),
        # 3. 输入微信号/手机号
        NavStep(
            action="input_text",
            target="wechat_add_search_input",
            params={"text": "{wechat_id}"},
            description="输入微信号"
        ),
        # 4. 点击搜索
        NavStep(
            action="tap",
            target="dynamic:搜索按钮",
            description="点击搜索"
        ),
        # 5. 等待搜索结果
        NavStep(
            action="wait",
            params={"duration": 1500},
            description="等待搜索结果"
        ),
        # 6. 点击添加到通讯录
        NavStep(
            action="tap",
            target="wechat_add_contact_button",
            description="点击添加到通讯录"
        ),
        # 7. 发送好友申请
        NavStep(
            action="tap",
            target="wechat_add_send_button",
            description="点击发送申请"
        ),
    ],

    end_screen=WeChatScreen.ADD_FRIEND,
    required_params=["wechat_id"],
    optional_params={"verify_message": ""},
)


# ============================================================
# 发消息工作流 - 本地匹配版本（无AI回退）
# ============================================================

WORKFLOW_SEND_MESSAGE_LOCAL = Workflow(
    name="send_message_local",
    description="给联系人发送消息（纯本地匹配）",

    valid_start_screens=[WeChatScreen.HOME],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 用联系人参考图在聊天列表定位（通过别名系统映射）
        NavStep(
            action="tap",
            target="{contact}",  # 通过别名系统映射到 contacts/ 目录下的参考图
            description="点击联系人 {contact}",
            expect_screen=WeChatScreen.CHAT
        ),
        # 2. 点击输入框（使用参考图）
        NavStep(
            action="input_text",
            target="wechat_chat_input",
            params={"text": "{message}"},
            description="输入消息内容"
        ),
        # 3. 点击发送按钮（使用参考图）
        NavStep(
            action="tap",
            target="wechat_chat_send",
            description="点击发送按钮"
        ),
        # 4. 等待发送完成
        NavStep(
            action="wait",
            params={"duration": 500},
            description="等待消息发送"
        ),
    ],

    end_screen=WeChatScreen.CHAT,
    required_params=["contact", "message"],
)


# ============================================================
# 发朋友圈工作流 - 本地匹配版本（无AI回退）
# ============================================================

WORKFLOW_POST_MOMENTS_ONLY_TEXT_LOCAL = Workflow(
    name="post_moments_only_text_local",
    description="发布纯文字朋友圈（纯本地匹配）",

    valid_start_screens=[WeChatScreen.HOME],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击发现 Tab（使用参考图）
        NavStep(
            action="tap",
            target="wechat_tab_discover_button",
            description="点击发现Tab",
            expect_screen=WeChatScreen.DISCOVER
        ),
        # 2. 点击朋友圈入口（使用参考图）
        NavStep(
            action="tap",
            target="wechat_moments_entry",
            description="点击朋友圈",
            expect_screen=WeChatScreen.MOMENTS
        ),
        # 3. 长按相机图标发纯文字（使用参考图）
        NavStep(
            action="long_press",
            target="wechat_moments_camera",
            description="长按相机图标",
            expect_screen=WeChatScreen.MOMENTS_POST
        ),
        # 4. 输入文字内容（使用参考图定位输入框）
        NavStep(
            action="input_text",
            target="wechat_moments_input_box",
            params={"text": "{content}"},
            description="输入朋友圈内容"
        ),
        # 5. 点击发表（使用参考图）
        NavStep(
            action="tap",
            target="wechat_moments_publish",
            description="点击发表按钮"
        ),
        # 6. 等待发布完成
        NavStep(
            action="wait",
            params={"duration": 1000},
            description="等待发布完成"
        ),
    ],

    end_screen=WeChatScreen.MOMENTS,
    required_params=["content"],
)


# ============================================================
# 工作流注册表
# ============================================================

WORKFLOWS: Dict[str, Workflow] = {
    "send_message": WORKFLOW_SEND_MESSAGE,
    "send_message_local": WORKFLOW_SEND_MESSAGE_LOCAL,
    "post_moments": WORKFLOW_POST_MOMENTS,
    "post_moments_only_text_local": WORKFLOW_POST_MOMENTS_ONLY_TEXT_LOCAL,
    "message_and_moments": WORKFLOW_MESSAGE_AND_MOMENTS,
    "search_contact": WORKFLOW_SEARCH_CONTACT,
    "add_friend": WORKFLOW_ADD_FRIEND,
}

# Local 工作流映射（用于回退）
LOCAL_TO_NORMAL_WORKFLOW = {
    "send_message_local": "send_message",
    "post_moments_only_text_local": "post_moments",
}


# ============================================================
# 任务模式匹配规则
# ============================================================

# ============================================================
# 简单任务模式（规则直接匹配）
# ============================================================

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


# 复合任务关键词（检测到这些词表示是复杂任务，需要 LLM 判断）
# 保留用于向后兼容和正则模式
COMPLEX_TASK_INDICATORS = [
    "然后", "再", "接着", "之后", "完成后",
    "并且", "同时", "顺便",
    "截图", "保存",
]


def is_complex_task(task: str) -> bool:
    """
    判断是否为复杂任务

    使用任务分类器判断（支持正则和LLM两种模式，通过环境变量配置）
    """
    classifier = get_task_classifier()
    return classifier.is_complex_task(task)


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
