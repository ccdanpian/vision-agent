"""apps/chrome/workflows.py
Chrome 浏览器工作流定义 - 预定义的任务路径和状态机

每个工作流定义：
- 前置条件检测（当前在哪个界面）
- 导航到目标界面的路径
- 执行核心操作
- 完成后的状态
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import re


class ChromeScreen(Enum):
    """Chrome 界面状态"""
    UNKNOWN = "unknown"           # 未知界面
    HOME = "home"                 # 主页/新标签页
    WEBPAGE = "webpage"           # 网页浏览中
    SEARCH_RESULTS = "search_results"  # 搜索结果页
    ADDRESS_BAR = "address_bar"   # 地址栏激活
    TABS = "tabs"                 # 标签页列表
    MENU = "menu"                 # 菜单页面
    BOOKMARKS = "bookmarks"       # 书签页面
    HISTORY = "history"           # 历史记录页面
    DOWNLOADS = "downloads"       # 下载页面
    SETTINGS = "settings"         # 设置页面
    OTHER = "other"               # 其他界面（需要返回）


# 界面检测参考图映射
SCREEN_DETECT_REFS = {
    ChromeScreen.HOME: "chrome_home_page",           # Chrome 主页
    ChromeScreen.ADDRESS_BAR: "chrome_address_bar",  # 地址栏
    ChromeScreen.SEARCH_RESULTS: "chrome_baidu_search_input",  # 百度搜索结果
}

# 备用界面检测参考图
SCREEN_DETECT_REFS_FALLBACK = {
    ChromeScreen.HOME: "chrome_search_box",  # 主页搜索框
}


@dataclass
class NavStep:
    """导航步骤"""
    action: str                    # tap, press_key, swipe, wait, check, input_text, input_url
    target: Optional[str] = None   # 目标参考图或描述
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    expect_screen: Optional[ChromeScreen] = None  # 执行后期望的界面
    max_wait: int = 2000           # 最大等待时间 ms


@dataclass
class Workflow:
    """工作流定义"""
    name: str                      # 工作流名称
    description: str = ""         # 描述

    # 前置条件
    valid_start_screens: List[ChromeScreen] = field(default_factory=list)  # 可以开始执行的界面

    # 导航到起始点（如果不在有效起始界面）
    nav_to_start: List[NavStep] = field(default_factory=list)    # 导航到起始界面的步骤

    # 核心步骤（带参数占位符）
    steps: List[NavStep] = field(default_factory=list)           # 主要执行步骤

    # 完成后状态
    end_screen: ChromeScreen = ChromeScreen.HOME      # 完成后所在界面

    # 参数定义
    required_params: List[str] = field(default_factory=list)  # 必需参数
    optional_params: Dict[str, Any] = field(default_factory=dict)  # 可选参数及默认值


# ============================================================
# 基础导航工作流 - 返回 Chrome 主页
# ============================================================

NAV_TO_HOME = [
    NavStep(
        action="check",
        target="chrome_home_page",
        description="检查是否已在主页",
        expect_screen=ChromeScreen.HOME
    ),
    NavStep(
        action="press_key",
        params={"keycode": 4},  # BACK
        description="按返回键",
        max_wait=500
    ),
    NavStep(
        action="check",
        target="chrome_home_page",
        description="检查是否已在主页",
        expect_screen=ChromeScreen.HOME
    ),
    NavStep(
        action="press_key",
        params={"keycode": 4},
        description="再按返回键",
        max_wait=500
    ),
    NavStep(
        action="check",
        target="chrome_home_page",
        description="检查是否已在主页",
        expect_screen=ChromeScreen.HOME
    ),
    # 如果还不在主页，尝试点击主页按钮
    NavStep(
        action="tap",
        target="chrome_home_button",
        description="点击主页按钮",
        expect_screen=ChromeScreen.HOME
    ),
]


# ============================================================
# 打开网址工作流
# ============================================================

WORKFLOW_OPEN_URL = Workflow(
    name="open_url",
    description="打开指定网址",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击地址栏
        NavStep(
            action="tap",
            target="chrome_address_bar",
            description="点击地址栏",
            expect_screen=ChromeScreen.ADDRESS_BAR
        ),
        # 2. 清空并输入网址
        NavStep(
            action="input_url",
            params={"url": "{url}"},
            description="输入网址 {url}"
        ),
        # 3. 按回车确认
        NavStep(
            action="press_key",
            params={"keycode": 66},  # ENTER
            description="按回车打开网页"
        ),
        # 4. 等待页面加载
        NavStep(
            action="wait",
            params={"duration": 2000},
            description="等待页面加载"
        ),
    ],

    end_screen=ChromeScreen.WEBPAGE,
    required_params=["url"],
)


# ============================================================
# 打开网址工作流 - 本地匹配版本（无AI回退）
# ============================================================

WORKFLOW_OPEN_URL_LOCAL = Workflow(
    name="open_url_local",
    description="打开指定网址（纯本地匹配）",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击地址栏（使用参考图）
        NavStep(
            action="tap",
            target="chrome_address_bar",
            description="点击地址栏",
            expect_screen=ChromeScreen.ADDRESS_BAR
        ),
        # 2. 清空并输入网址
        NavStep(
            action="input_url",
            params={"url": "{url}"},
            description="输入网址 {url}"
        ),
        # 3. 按回车确认
        NavStep(
            action="press_key",
            params={"keycode": 66},  # ENTER
            description="按回车打开网页"
        ),
        # 4. 等待页面加载
        NavStep(
            action="wait",
            params={"duration": 2000},
            description="等待页面加载"
        ),
    ],

    end_screen=ChromeScreen.WEBPAGE,
    required_params=["url"],
)


# ============================================================
# 搜索工作流
# ============================================================

WORKFLOW_SEARCH_WEB = Workflow(
    name="search_web",
    description="在浏览器中搜索",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE, ChromeScreen.SEARCH_RESULTS],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击地址栏或搜索框
        NavStep(
            action="tap",
            target="chrome_address_bar",
            description="点击地址栏",
            expect_screen=ChromeScreen.ADDRESS_BAR
        ),
        # 2. 输入搜索词
        NavStep(
            action="input_text",
            target="chrome_search_input",
            params={"text": "{query}"},
            description="输入搜索词 {query}"
        ),
        # 3. 按回车搜索
        NavStep(
            action="press_key",
            params={"keycode": 66},  # ENTER
            description="按回车搜索"
        ),
        # 4. 等待搜索结果
        NavStep(
            action="wait",
            params={"duration": 2000},
            description="等待搜索结果"
        ),
    ],

    end_screen=ChromeScreen.SEARCH_RESULTS,
    required_params=["query"],
)


# ============================================================
# 搜索工作流 - 本地匹配版本（无AI回退）
# ============================================================

WORKFLOW_SEARCH_WEB_LOCAL = Workflow(
    name="search_web_local",
    description="在浏览器中搜索（纯本地匹配）",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击地址栏（使用参考图）
        NavStep(
            action="tap",
            target="chrome_address_bar",
            description="点击地址栏",
            expect_screen=ChromeScreen.ADDRESS_BAR
        ),
        # 2. 输入搜索词
        NavStep(
            action="input_text",
            target="chrome_search_input",
            params={"text": "{query}"},
            description="输入搜索词 {query}"
        ),
        # 3. 按回车搜索
        NavStep(
            action="press_key",
            params={"keycode": 66},  # ENTER
            description="按回车搜索"
        ),
        # 4. 等待搜索结果
        NavStep(
            action="wait",
            params={"duration": 2000},
            description="等待搜索结果"
        ),
    ],

    end_screen=ChromeScreen.SEARCH_RESULTS,
    required_params=["query"],
)


# ============================================================
# 打开百度工作流
# ============================================================

WORKFLOW_OPEN_BAIDU = Workflow(
    name="open_baidu",
    description="打开百度首页",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击地址栏
        NavStep(
            action="tap",
            target="chrome_address_bar",
            description="点击地址栏",
            expect_screen=ChromeScreen.ADDRESS_BAR
        ),
        # 2. 输入百度网址
        NavStep(
            action="input_url",
            params={"url": "baidu.com"},
            description="输入 baidu.com"
        ),
        # 3. 按回车确认
        NavStep(
            action="press_key",
            params={"keycode": 66},  # ENTER
            description="按回车打开百度"
        ),
        # 4. 等待页面加载
        NavStep(
            action="wait",
            params={"duration": 2000},
            description="等待百度首页加载"
        ),
    ],

    end_screen=ChromeScreen.WEBPAGE,
    required_params=[],
)


# ============================================================
# 打开百度工作流 - 本地匹配版本（无AI回退）
# ============================================================

WORKFLOW_OPEN_BAIDU_LOCAL = Workflow(
    name="open_baidu_local",
    description="打开百度首页（纯本地匹配）",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=NAV_TO_HOME,

    steps=[
        # 1. 点击地址栏（使用参考图）
        NavStep(
            action="tap",
            target="chrome_address_bar",
            description="点击地址栏",
            expect_screen=ChromeScreen.ADDRESS_BAR
        ),
        # 2. 输入百度网址
        NavStep(
            action="input_url",
            params={"url": "baidu.com"},
            description="输入 baidu.com"
        ),
        # 3. 按回车确认
        NavStep(
            action="press_key",
            params={"keycode": 66},  # ENTER
            description="按回车打开百度"
        ),
        # 4. 等待页面加载
        NavStep(
            action="wait",
            params={"duration": 2000},
            description="等待百度首页加载"
        ),
    ],

    end_screen=ChromeScreen.WEBPAGE,
    required_params=[],
)


# ============================================================
# 新建标签页工作流
# ============================================================

WORKFLOW_NEW_TAB = Workflow(
    name="new_tab",
    description="新建标签页",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE, ChromeScreen.SEARCH_RESULTS],

    nav_to_start=[],  # 可以从任何页面新建标签

    steps=[
        # 1. 点击标签页切换按钮
        NavStep(
            action="tap",
            target="chrome_tab_switcher",
            description="点击标签页切换按钮",
            expect_screen=ChromeScreen.TABS
        ),
        # 2. 点击新建标签按钮
        NavStep(
            action="tap",
            target="chrome_new_tab_button",
            description="点击新建标签按钮",
            expect_screen=ChromeScreen.HOME
        ),
    ],

    end_screen=ChromeScreen.HOME,
    required_params=[],
)


# ============================================================
# 刷新页面工作流
# ============================================================

WORKFLOW_REFRESH = Workflow(
    name="refresh",
    description="刷新当前页面",

    valid_start_screens=[ChromeScreen.WEBPAGE, ChromeScreen.SEARCH_RESULTS],

    nav_to_start=[],

    steps=[
        # 1. 点击菜单按钮
        NavStep(
            action="tap",
            target="chrome_menu_button",
            description="点击菜单按钮",
            expect_screen=ChromeScreen.MENU
        ),
        # 2. 点击刷新按钮
        NavStep(
            action="tap",
            target="chrome_refresh_button",
            description="点击刷新按钮"
        ),
        # 3. 等待页面刷新
        NavStep(
            action="wait",
            params={"duration": 2000},
            description="等待页面刷新"
        ),
    ],

    end_screen=ChromeScreen.WEBPAGE,
    required_params=[],
)


# ============================================================
# 查看书签工作流
# ============================================================

WORKFLOW_VIEW_BOOKMARKS = Workflow(
    name="view_bookmarks",
    description="查看书签列表",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=[],

    steps=[
        # 1. 点击菜单按钮
        NavStep(
            action="tap",
            target="chrome_menu_button",
            description="点击菜单按钮",
            expect_screen=ChromeScreen.MENU
        ),
        # 2. 点击书签
        NavStep(
            action="tap",
            target="chrome_bookmarks_menu",
            description="点击书签菜单",
            expect_screen=ChromeScreen.BOOKMARKS
        ),
    ],

    end_screen=ChromeScreen.BOOKMARKS,
    required_params=[],
)


# ============================================================
# 查看历史记录工作流
# ============================================================

WORKFLOW_VIEW_HISTORY = Workflow(
    name="view_history",
    description="查看历史记录",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=[],

    steps=[
        # 1. 点击菜单按钮
        NavStep(
            action="tap",
            target="chrome_menu_button",
            description="点击菜单按钮",
            expect_screen=ChromeScreen.MENU
        ),
        # 2. 点击历史记录
        NavStep(
            action="tap",
            target="chrome_history_menu",
            description="点击历史记录菜单",
            expect_screen=ChromeScreen.HISTORY
        ),
    ],

    end_screen=ChromeScreen.HISTORY,
    required_params=[],
)


# ============================================================
# 查看下载工作流
# ============================================================

WORKFLOW_VIEW_DOWNLOADS = Workflow(
    name="view_downloads",
    description="查看下载列表",

    valid_start_screens=[ChromeScreen.HOME, ChromeScreen.WEBPAGE],

    nav_to_start=[],

    steps=[
        # 1. 点击菜单按钮
        NavStep(
            action="tap",
            target="chrome_menu_button",
            description="点击菜单按钮",
            expect_screen=ChromeScreen.MENU
        ),
        # 2. 点击下载
        NavStep(
            action="tap",
            target="chrome_downloads_menu",
            description="点击下载菜单",
            expect_screen=ChromeScreen.DOWNLOADS
        ),
    ],

    end_screen=ChromeScreen.DOWNLOADS,
    required_params=[],
)


# ============================================================
# 关闭当前标签页工作流
# ============================================================

WORKFLOW_CLOSE_TAB = Workflow(
    name="close_tab",
    description="关闭当前标签页",

    valid_start_screens=[ChromeScreen.WEBPAGE, ChromeScreen.SEARCH_RESULTS, ChromeScreen.HOME],

    nav_to_start=[],

    steps=[
        # 1. 点击标签页切换按钮
        NavStep(
            action="tap",
            target="chrome_tab_switcher",
            description="点击标签页切换按钮",
            expect_screen=ChromeScreen.TABS
        ),
        # 2. 点击当前标签页的关闭按钮
        NavStep(
            action="tap",
            target="chrome_close_tab_button",
            description="点击关闭标签按钮"
        ),
    ],

    end_screen=ChromeScreen.HOME,
    required_params=[],
)


# ============================================================
# 工作流注册表
# ============================================================

WORKFLOWS: Dict[str, Workflow] = {
    "open_url": WORKFLOW_OPEN_URL,
    "open_url_local": WORKFLOW_OPEN_URL_LOCAL,
    "search_web": WORKFLOW_SEARCH_WEB,
    "search_web_local": WORKFLOW_SEARCH_WEB_LOCAL,
    "open_baidu": WORKFLOW_OPEN_BAIDU,
    "open_baidu_local": WORKFLOW_OPEN_BAIDU_LOCAL,
    "new_tab": WORKFLOW_NEW_TAB,
    "refresh": WORKFLOW_REFRESH,
    "view_bookmarks": WORKFLOW_VIEW_BOOKMARKS,
    "view_history": WORKFLOW_VIEW_HISTORY,
    "view_downloads": WORKFLOW_VIEW_DOWNLOADS,
    "close_tab": WORKFLOW_CLOSE_TAB,
}

# Local 工作流映射（用于回退）
LOCAL_TO_NORMAL_WORKFLOW = {
    "open_url_local": "open_url",
    "search_web_local": "search_web",
    "open_baidu_local": "open_baidu",
}


# ============================================================
# 简单任务模式（规则直接匹配）
# ============================================================

SIMPLE_TASK_PATTERNS = [
    # 打开网址
    {
        "patterns": [r"打开(?:网址|网站)?\s*(?P<url>https?://\S+)", r"访问\s*(?P<url>https?://\S+)"],
        "patterns_regex": True,
        "workflow": "open_url",
        "param_hints": {
            "url": "网址"
        }
    },

    # 搜索
    {
        "patterns": ["搜索", "查一下", "百度一下", "谷歌一下"],
        "not_contains": ["然后", "再", "接着"],
        "workflow": "search_web",
        "param_hints": {
            "query": "搜索词"
        }
    },

    # 打开百度
    {
        "patterns": ["打开百度", "进入百度", "百度首页"],
        "not_contains": ["搜索", "查"],
        "workflow": "open_baidu",
        "param_hints": {}
    },

    # 新建标签
    {
        "patterns": ["新建标签", "新标签页", "打开新标签"],
        "workflow": "new_tab",
        "param_hints": {}
    },

    # 刷新
    {
        "patterns": ["刷新", "重新加载"],
        "workflow": "refresh",
        "param_hints": {}
    },

    # 书签
    {
        "patterns": ["书签", "收藏夹"],
        "workflow": "view_bookmarks",
        "param_hints": {}
    },

    # 历史记录
    {
        "patterns": ["历史记录", "浏览历史"],
        "workflow": "view_history",
        "param_hints": {}
    },

    # 下载
    {
        "patterns": ["下载", "下载管理"],
        "not_contains": ["图片", "文件", "视频"],
        "workflow": "view_downloads",
        "param_hints": {}
    },

    # 关闭标签
    {
        "patterns": ["关闭标签", "关闭当前页", "关闭网页"],
        "workflow": "close_tab",
        "param_hints": {}
    },
]


# 复合任务关键词
COMPLEX_TASK_INDICATORS = [
    "然后", "再", "接着", "之后", "完成后",
    "并且", "同时", "顺便",
    "截图", "保存", "下载图片",
]


def is_complex_task(task: str) -> bool:
    """
    判断是否为复杂任务
    """
    # 包含复合任务指示词
    if any(indicator in task for indicator in COMPLEX_TASK_INDICATORS):
        return True

    # 包含多个动作词
    action_words = ["打开", "搜索", "刷新", "关闭", "下载", "保存"]
    action_count = sum(1 for w in action_words if w in task)
    return action_count >= 2


def match_simple_workflow(task: str) -> Optional[Dict[str, Any]]:
    """
    简单任务的规则匹配（快速路径）

    Args:
        task: 用户任务描述

    Returns:
        匹配结果或 None
    """
    if is_complex_task(task):
        return None

    for pattern_rule in SIMPLE_TASK_PATTERNS:
        patterns = pattern_rule.get("patterns", [])
        contains = pattern_rule.get("contains", [])
        not_contains = pattern_rule.get("not_contains", [])
        use_regex = pattern_rule.get("patterns_regex", False)

        # 检查是否匹配任一关键词
        matched = False
        extracted_params = {}

        for p in patterns:
            if use_regex:
                try:
                    match = re.search(p, task, re.IGNORECASE)
                    if match:
                        matched = True
                        # 提取命名组
                        extracted_params = match.groupdict()
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
                "extracted_params": extracted_params,
                "match_type": "simple"
            }

    return None


def get_workflow_descriptions() -> str:
    """获取所有工作流的描述（用于 LLM 选择）"""
    lines = []
    for name, wf in WORKFLOWS.items():
        params_str = ", ".join(wf.required_params) if wf.required_params else "无"
        lines.append(f"- {name}: {wf.description}")
        lines.append(f"  必需参数: {params_str}")
        if wf.optional_params:
            opt_str = ", ".join(f"{k}={v}" for k, v in wf.optional_params.items())
            lines.append(f"  可选参数: {opt_str}")
    return "\n".join(lines)


def match_workflow(task: str) -> Optional[Dict[str, Any]]:
    """
    匹配工作流（简单任务用规则，复杂任务返回 None 让 LLM 判断）
    """
    return match_simple_workflow(task)
