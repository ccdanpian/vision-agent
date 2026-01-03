"""
ai/ - AI 模块

包含:
- VisionAgent: 视觉代理，使用多模态 LLM 分析屏幕
- Planner: 任务规划器，将任务分解为步骤
- Verifier: 结果验证器，验证操作结果
"""

from ai.vision_agent import VisionAgent, Action, ActionType, compare_screenshots
from ai.planner import Planner, TaskPlan, StepPlan, ActionName, TargetType, AssetsManager
from ai.verifier import Verifier, VerifyResult, BlockerType, SuggestionAction

__all__ = [
    # vision_agent
    "VisionAgent",
    "Action",
    "ActionType",
    "compare_screenshots",
    # planner
    "Planner",
    "TaskPlan",
    "StepPlan",
    "ActionName",
    "TargetType",
    "AssetsManager",
    # verifier
    "Verifier",
    "VerifyResult",
    "BlockerType",
    "SuggestionAction",
]
