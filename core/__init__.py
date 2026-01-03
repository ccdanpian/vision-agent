"""
core/ - 核心模块

包含:
- ADBController: ADB 控制器，通过 ADB 命令控制设备
- TaskRunner: 任务执行器，整合所有层执行任务
- OpenCVLocator: OpenCV 元素定位器
- HybridLocator: 混合定位器 (OpenCV + AI)
"""

from core.adb_controller import ADBController
from core.task_runner import TaskRunner, TaskResult, TaskStatus, StepResult, StepStatus
from core.opencv_locator import OpenCVLocator, MatchMethod, MatchResult
from core.hybrid_locator import HybridLocator, LocateStrategy, LocateResult, create_hybrid_locator

__all__ = [
    # ADB
    "ADBController",
    # TaskRunner
    "TaskRunner",
    "TaskResult",
    "TaskStatus",
    "StepResult",
    "StepStatus",
    # OpenCV Locator
    "OpenCVLocator",
    "MatchMethod",
    "MatchResult",
    # Hybrid Locator
    "HybridLocator",
    "LocateStrategy",
    "LocateResult",
    "create_hybrid_locator",
]
