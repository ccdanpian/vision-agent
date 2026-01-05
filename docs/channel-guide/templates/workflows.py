"""
apps/{channel}/workflows.py
{Channel}频道工作流定义模板

使用说明：
1. 将 {Channel} 替换为频道名称（如 Douyin, Weibo）
2. 将 {channel} 替换为小写名称（如 douyin, weibo）
3. 根据实际应用定义界面状态和工作流
"""

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


# ============================================================
# 界面状态枚举
# ============================================================

class {Channel}Screen(Enum):
    """
    {Channel}界面状态

    定义应用的所有主要界面，用于：
    1. 界面检测
    2. 工作流起点验证
    3. 步骤执行后的状态验证
    """
    UNKNOWN = "unknown"           # 未知界面
    HOME = "home"                 # 首页
    # TODO: 添加更多界面状态
    # PROFILE = "profile"         # 个人页
    # SEARCH = "search"           # 搜索页
    # DETAIL = "detail"           # 详情页
    OTHER = "other"               # 其他界面


# ============================================================
# 界面检测参考图映射
# ============================================================

# 主参考图映射
SCREEN_DETECT_REFS = {
    {Channel}Screen.HOME: "{channel}_home",  # 首页特征元素
    # TODO: 添加更多界面的参考图映射
    # {Channel}Screen.PROFILE: "system/{channel}_profile_page",
}

# 备用参考图（主参考图匹配失败时使用）
SCREEN_DETECT_REFS_FALLBACK = {
    {Channel}Screen.HOME: "system/{channel}_home_page",
}


# ============================================================
# 导航步骤数据类
# ============================================================

@dataclass
class NavStep:
    """
    导航步骤

    支持的 action 类型：
    - tap: 点击目标
    - press_key: 按键（params.keycode）
    - swipe: 滑动
    - wait: 等待（params.duration）
    - check: 检查界面状态
    - input_text: 输入文本（params.text）
    - find_or_search: 查找或搜索
    - sub_workflow: 执行子工作流
    - screenshot: 截图
    - conditional: 条件执行
    """
    action: str                    # 动作类型
    target: Optional[str] = None   # 目标参考图或描述，支持 {param} 占位符
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""          # 步骤描述
    expect_screen: Optional[{Channel}Screen] = None  # 执行后期望的界面
    max_wait: int = 2000           # 最大等待时间 ms


# ============================================================
# 工作流数据类
# ============================================================

@dataclass
class Workflow:
    """
    工作流定义

    工作流是一系列步骤的组合，用于完成特定任务。
    """
    name: str                      # 工作流名称（英文，用于代码引用）
    description: str               # 描述（中文，用于显示和 LLM 理解）

    # 前置条件
    valid_start_screens: List[{Channel}Screen]  # 可以开始执行的界面

    # 导航到起始点
    nav_to_start: List[NavStep]    # 如果不在有效起始界面，执行这些步骤

    # 核心步骤
    steps: List[NavStep]           # 主要执行步骤

    # 完成后状态
    end_screen: {Channel}Screen    # 完成后所在界面

    # 参数定义
    required_params: List[str] = field(default_factory=list)  # 必需参数
    optional_params: Dict[str, Any] = field(default_factory=dict)  # 可选参数及默认值


# ============================================================
# 通用导航步骤
# ============================================================

# 返回首页的策略
NAV_TO_HOME = [
    NavStep(
        action="check",
        target="system/{channel}_home_page",
        description="检查是否已在首页",
        expect_screen={Channel}Screen.HOME
    ),
    NavStep(
        action="press_key",
        params={"keycode": 4},  # BACK
        description="按返回键",
        max_wait=500
    ),
    NavStep(
        action="check",
        target="system/{channel}_home_page",
        description="检查是否已在首页",
        expect_screen={Channel}Screen.HOME
    ),
    NavStep(
        action="press_key",
        params={"keycode": 4},
        description="再按返回键",
        max_wait=500
    ),
    NavStep(
        action="check",
        target="system/{channel}_home_page",
        description="最后检查",
        expect_screen={Channel}Screen.HOME
    ),
]


# ============================================================
# 工作流定义
# ============================================================

# 示例工作流：执行基本操作
WORKFLOW_EXAMPLE = Workflow(
    name="example_workflow",
    description="示例工作流",

    valid_start_screens=[{Channel}Screen.HOME],

    nav_to_start=NAV_TO_HOME,

    steps=[
        NavStep(
            action="tap",
            target="{channel}_button",
            description="点击按钮",
        ),
        NavStep(
            action="wait",
            params={"duration": 500},
            description="等待响应"
        ),
    ],

    end_screen={Channel}Screen.HOME,
    required_params=[],
    optional_params={},
)

# TODO: 添加更多工作流
# WORKFLOW_XXX = Workflow(...)


# ============================================================
# 工作流注册表
# ============================================================

WORKFLOWS: Dict[str, Workflow] = {
    "example_workflow": WORKFLOW_EXAMPLE,
    # TODO: 注册更多工作流
}


# ============================================================
# 任务分类
# ============================================================

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
    # TODO: 根据频道特点定义动作词
    action_words = ["打开", "点击", "搜索", "发送"]
    action_count = sum(1 for w in action_words if w in task)
    if action_count >= 2:
        return True

    return False


# ============================================================
# 简单任务模式匹配
# ============================================================

SIMPLE_TASK_PATTERNS = [
    # 示例模式
    {
        "patterns": ["打开{channel}"],  # 匹配的关键词
        "contains": [],                   # 必须包含的词
        "not_contains": ["然后", "再"],   # 不能包含的词
        "workflow": "example_workflow",   # 匹配的工作流
        "param_hints": {}                 # 参数提示
    },
    # TODO: 添加更多模式
]


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

        # 检查是否匹配任一关键词
        matched = False
        for p in patterns:
            if use_regex and any(c in p for c in '.*+?[]()'):
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
        params_str = ", ".join(wf.required_params) if wf.required_params else "无"
        lines.append(f"- {name}: {wf.description}")
        lines.append(f"  必需参数: {params_str}")
        if wf.optional_params:
            opt_str = ", ".join(f"{k}={v}" for k, v in wf.optional_params.items())
            lines.append(f"  可选参数: {opt_str}")
    return "\n".join(lines)


# 兼容函数
def match_workflow(task: str) -> Optional[Dict[str, Any]]:
    """匹配工作流（简单任务用规则，复杂任务返回 None 让 LLM 判断）"""
    return match_simple_workflow(task)
