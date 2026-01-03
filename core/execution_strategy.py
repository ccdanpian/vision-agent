"""
core/execution_strategy.py
执行策略 - 定义步骤的执行和验证策略

设计原则：
1. 确定性步骤快速执行，不等待验证
2. 只在关键节点进行 AI 验证
3. 连续简单步骤批量执行
"""
from enum import Enum
from typing import List, Set
from dataclasses import dataclass
from ai.planner import ActionName, StepPlan


class ExecutionLevel(Enum):
    """执行级别 - 决定如何执行和验证"""

    # Level 0: 直接执行，无需验证
    # 这些操作通过 ADB 直接完成，成功率接近 100%
    FIRE_AND_FORGET = 0

    # Level 1: 快速执行，轻量验证（只检查错误弹窗）
    # 这些操作可能失败，但不需要 AI 定位
    QUICK_VERIFY = 1

    # Level 2: 需要定位，轻量验证
    # 需要找到目标元素，但验证可以简化
    LOCATE_AND_EXECUTE = 2

    # Level 3: 完整 AI 流程
    # 需要 AI 定位 + AI 验证
    FULL_AI = 3


# 各级别包含的动作
# 注意：PRESS_KEY 需要根据是否有导航目标特殊处理，不放在这里
LEVEL_0_ACTIONS: Set[ActionName] = {
    ActionName.LAUNCH_APP,   # 直接启动应用
    ActionName.CALL,         # 直接拨打电话
    ActionName.OPEN_URL,     # 直接打开网址
    ActionName.GO_HOME,      # 返回桌面
    ActionName.WAIT,         # 等待
}

# 导航相关关键词，用于判断 PRESS_KEY 是否需要验证
NAVIGATION_KEYWORDS = [
    "回到", "返回", "进入", "打开", "到达",
    "首页", "主页", "主界面", "聊天列表",
    "退出", "关闭", "离开"
]

LEVEL_1_ACTIONS: Set[ActionName] = {
    ActionName.SWIPE,        # 滑动（方向已知）
}


@dataclass
class StepStrategy:
    """步骤执行策略"""
    level: ExecutionLevel
    need_screenshot_before: bool  # 执行前是否需要截图
    need_ai_locate: bool          # 是否需要 AI 定位
    need_verification: bool       # 是否需要验证
    ai_verification: bool         # 验证是否需要 AI
    wait_after_ms: int            # 执行后等待时间


def _has_navigation_goal(step: StepPlan) -> bool:
    """判断步骤是否有导航目标"""
    description = step.description or ""
    success_condition = step.success_condition or ""
    combined = description + success_condition

    for keyword in NAVIGATION_KEYWORDS:
        if keyword in combined:
            return True
    return False


def _is_back_to_home(step: StepPlan) -> bool:
    """判断步骤是否是返回首页/主页操作"""
    home_keywords = ["首页", "主页", "主界面", "聊天列表", "微信主", "返回微信"]
    description = step.description or ""
    for kw in home_keywords:
        if kw in description:
            return True
    return False


def get_step_strategy(step: StepPlan) -> StepStrategy:
    """
    根据步骤内容决定执行策略

    Args:
        step: 步骤计划

    Returns:
        执行策略
    """
    action = step.action
    target_ref = step.target_ref

    # PRESS_KEY 特殊处理
    if action == ActionName.PRESS_KEY:
        keycode = step.params.get("keycode", 4)

        # "返回首页"类操作：验证已内置在执行逻辑中（循环检测返回按钮）
        # 其他按键：不需要验证
        # 两者都用 FIRE_AND_FORGET，但返回首页需要更长等待时间
        if keycode == 4 and _is_back_to_home(step):
            return StepStrategy(
                level=ExecutionLevel.FIRE_AND_FORGET,
                need_screenshot_before=False,
                need_ai_locate=False,
                need_verification=False,  # 验证已内置
                ai_verification=False,
                wait_after_ms=300
            )
        else:
            return StepStrategy(
                level=ExecutionLevel.FIRE_AND_FORGET,
                need_screenshot_before=False,
                need_ai_locate=False,
                need_verification=False,
                ai_verification=False,
                wait_after_ms=100
            )

    # Level 0: 直接执行的操作
    if action in LEVEL_0_ACTIONS:
        # 根据动作类型设置不同的等待时间
        if action == ActionName.LAUNCH_APP:
            wait_ms = 500  # 应用启动需要较长时间
        elif action == ActionName.OPEN_URL:
            wait_ms = 2500  # 网页加载需要等待
        else:
            wait_ms = 100

        return StepStrategy(
            level=ExecutionLevel.FIRE_AND_FORGET,
            need_screenshot_before=False,
            need_ai_locate=False,
            need_verification=False,
            ai_verification=False,
            wait_after_ms=wait_ms
        )

    # Level 1: 滑动等简单操作
    if action in LEVEL_1_ACTIONS:
        return StepStrategy(
            level=ExecutionLevel.QUICK_VERIFY,
            need_screenshot_before=False,
            need_ai_locate=False,
            need_verification=False,  # 滑动通常不需要验证
            ai_verification=False,
            wait_after_ms=200
        )

    # input_text 特殊处理：输入后不需要 AI 验证
    # AI 验证会在后续关键步骤（如点击搜索、发送）时进行
    if action == ActionName.INPUT_TEXT:
        if target_ref and target_ref.startswith("dynamic:"):
            # 动态定位输入框
            return StepStrategy(
                level=ExecutionLevel.FULL_AI,
                need_screenshot_before=True,
                need_ai_locate=True,
                need_verification=False,  # 输入不需要验证
                ai_verification=False,
                wait_after_ms=300
            )
        elif target_ref:
            # 参考图定位输入框
            return StepStrategy(
                level=ExecutionLevel.LOCATE_AND_EXECUTE,
                need_screenshot_before=True,
                need_ai_locate=False,
                need_verification=False,
                ai_verification=False,
                wait_after_ms=300
            )
        else:
            # 无目标，假设焦点已在输入框
            return StepStrategy(
                level=ExecutionLevel.QUICK_VERIFY,
                need_screenshot_before=True,
                need_ai_locate=False,
                need_verification=False,
                ai_verification=False,
                wait_after_ms=300
            )

    # 有目标的操作（tap, long_press）
    if target_ref:
        # 动态描述需要 AI
        if target_ref.startswith("dynamic:"):
            return StepStrategy(
                level=ExecutionLevel.FULL_AI,
                need_screenshot_before=True,
                need_ai_locate=True,
                need_verification=True,
                ai_verification=True,
                wait_after_ms=1000  # 动态定位需要更长等待时间
            )
        else:
            # 有参考图，可以用 OpenCV
            return StepStrategy(
                level=ExecutionLevel.LOCATE_AND_EXECUTE,
                need_screenshot_before=True,
                need_ai_locate=False,  # 先用 OpenCV
                need_verification=False,
                ai_verification=False,
                wait_after_ms=300
            )

    # 默认：需要完整流程（tap/long_press 无目标）
    return StepStrategy(
        level=ExecutionLevel.FULL_AI,
        need_screenshot_before=True,
        need_ai_locate=True,
        need_verification=True,
        ai_verification=True,
        wait_after_ms=500
    )


def can_batch_execute(steps: List[StepPlan]) -> List[List[StepPlan]]:
    """
    将步骤分组，连续的 Level 0 步骤可以批量执行

    Args:
        steps: 步骤列表

    Returns:
        分组后的步骤列表
    """
    if not steps:
        return []

    batches = []
    current_batch = []
    current_level = None

    for step in steps:
        strategy = get_step_strategy(step)

        # Level 0 步骤可以批量
        if strategy.level == ExecutionLevel.FIRE_AND_FORGET:
            if current_level == ExecutionLevel.FIRE_AND_FORGET:
                current_batch.append(step)
            else:
                if current_batch:
                    batches.append(current_batch)
                current_batch = [step]
                current_level = ExecutionLevel.FIRE_AND_FORGET
        else:
            # 非 Level 0 步骤单独成组
            if current_batch:
                batches.append(current_batch)
            batches.append([step])
            current_batch = []
            current_level = None

    if current_batch:
        batches.append(current_batch)

    return batches


def should_verify_at_end(steps: List[StepPlan]) -> bool:
    """
    判断是否应该在最后进行一次综合验证

    如果最后几步都是简单操作，应该在结束时验证任务是否完成
    """
    if not steps:
        return False

    # 检查最后 3 步
    last_steps = steps[-3:] if len(steps) >= 3 else steps

    for step in last_steps:
        strategy = get_step_strategy(step)
        if strategy.level >= ExecutionLevel.FULL_AI:
            # 如果最后有需要验证的步骤，不需要额外的结束验证
            return False

    return True
