"""
apps/{channel}/workflow_executor.py
{Channel}频道工作流执行器模板

使用说明：
1. 将 {Channel} 替换为频道名称（如 Douyin, Weibo）
2. 将 {channel} 替换为小写名称（如 douyin, weibo）
3. 将 {PACKAGE} 替换为应用包名（如 com.example.app）
"""

import re
import time
import io
from typing import Optional, Dict, Any, List, Tuple

from PIL import Image

import config
from core.hybrid_locator import LocateStrategy
from .workflows import (
    {Channel}Screen, Workflow, NavStep,
    SCREEN_DETECT_REFS, SCREEN_DETECT_REFS_FALLBACK
)


class WorkflowExecutor:
    """工作流执行器"""

    # 应用包名
    PACKAGE = "{PACKAGE}"

    def __init__(self, task_runner, handler):
        """
        初始化执行器

        Args:
            task_runner: TaskRunner 实例（用于执行操作）
            handler: Handler 实例（用于获取参考图）
        """
        self.runner = task_runner
        self.handler = handler
        self._logger = None
        self._max_back_presses = 5
        self._back_press_interval = 500

    def set_logger(self, logger_func):
        """设置日志函数"""
        self._logger = logger_func

    def _log(self, message: str):
        """记录日志"""
        if self._logger:
            self._logger(message)

    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """将 PIL Image 转换为 bytes"""
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

    def _render_template(self, template: str, params: Dict[str, Any]) -> str:
        """渲染模板字符串，替换 {param} 占位符"""
        result = template
        for key, value in params.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    # ============================================================
    # 应用启动和首页确认
    # ============================================================

    def _ensure_app_running(self) -> bool:
        """
        确保应用已打开并在前台

        Returns:
            是否成功确保应用在前台
        """
        self._log("")
        self._log("+" + "=" * 40 + "+")
        self._log("|       【预置流程】正式任务前准备        |")
        self._log("+" + "=" * 40 + "+")
        self._log("")
        self._log("[预置] 步骤0: 启动应用")

        # 启动应用
        self._log("  执行启动应用指令...")
        self.runner.adb.start_app(self.PACKAGE)
        time.sleep(config.OPERATION_DELAY * 4)

        # 验证应用是否启动
        current_app = self.runner.adb.get_current_app()
        self._log(f"  当前前台应用: {current_app}")

        if current_app != self.PACKAGE:
            if current_app is None:
                self._log("  无法检测前台应用，通过截图验证...")
                time.sleep(config.OPERATION_DELAY * 2)
                current_screen = self.detect_screen()
                if current_screen == {Channel}Screen.UNKNOWN:
                    self._log("  X 应用启动失败")
                    return False
                else:
                    self._log(f"  V 检测到应用界面: {current_screen.value}")
            else:
                self._log(f"  X 应用启动失败，当前应用: {current_app}")
                return False
        else:
            self._log("  V 应用已在前台")

        # 确保回到首页
        return self._ensure_at_home_screen()

    def _ensure_at_home_screen(self, max_attempts: int = 5) -> bool:
        """
        确保应用处于首页

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功回到首页
        """
        self._log("")
        self._log("[预置] 步骤1: 确保在首页")

        for attempt in range(max_attempts):
            self._log(f"  检测第 {attempt + 1}/{max_attempts} 次...")

            # 截图检测
            screenshot, top_offset = self.runner._capture_screenshot_cropped()
            screenshot_bytes = self._image_to_bytes(screenshot)

            # 获取首页参考图
            home_btn_paths = self.handler.get_image_variants("{channel}_home_button")
            back_paths = self.handler.get_image_variants("{channel}_back")

            # 构建检测目标
            targets = {}
            if home_btn_paths:
                targets["home_button"] = home_btn_paths
            if back_paths:
                targets["back_button"] = back_paths

            if not targets:
                self._log("  无可用参考图，按物理返回键")
                self.runner.adb.press_back()
                time.sleep(config.OPERATION_DELAY * 2)
                continue

            # 并行检测
            results = self.runner.hybrid_locator.locate_multiple_parallel(
                screenshot_bytes, targets
            )

            # 检查是否能看到首页标识
            home_result = results.get("home_button")
            if home_result and home_result.success:
                tap_y = home_result.center_y + top_offset
                self._log(f"  检测到首页标识，点击确认 ({home_result.center_x}, {tap_y})")
                self.runner.adb.tap(home_result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY * 2)
                self._log("  V 已进入首页")
                return True

            self._log("  未检测到首页标识，尝试返回...")

            # 点击返回按钮
            back_result = results.get("back_button")
            if back_result and back_result.success:
                tap_y = back_result.center_y + top_offset
                self._log(f"  找到返回按钮，点击 ({back_result.center_x}, {tap_y})")
                self.runner.adb.tap(back_result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY * 2)
                continue

            # 按物理返回键
            self._log("  未找到返回按钮，按物理返回键")
            self.runner.adb.press_back()
            time.sleep(config.OPERATION_DELAY * 2)

        self._log("  X 无法回到首页")
        return False

    # ============================================================
    # 界面检测
    # ============================================================

    def detect_screen(self, screenshot: Optional[Image.Image] = None) -> {Channel}Screen:
        """
        检测当前界面

        Args:
            screenshot: 屏幕截图，如果为 None 则自动截取

        Returns:
            当前界面类型
        """
        if screenshot is None:
            screenshot = self.runner._capture_screenshot()

        self._log("检测当前界面...")

        # 按优先级检测各界面
        detection_order = [
            {Channel}Screen.HOME,
            # TODO: 添加更多界面
        ]

        screenshot_bytes = self._image_to_bytes(screenshot)

        for screen in detection_order:
            # 获取主参考图和备用参考图
            ref_names = []
            if screen in SCREEN_DETECT_REFS:
                ref_names.append(SCREEN_DETECT_REFS[screen])
            if screen in SCREEN_DETECT_REFS_FALLBACK:
                ref_names.append(SCREEN_DETECT_REFS_FALLBACK[screen])

            for ref_name in ref_names:
                ref_path = self.handler.get_image_path(ref_name)
                if not ref_path or not ref_path.exists():
                    self._log(f"  参考图不存在: {ref_name}")
                    continue

                try:
                    result = self.runner.hybrid_locator.locate(
                        screenshot_bytes,
                        ref_path,
                        LocateStrategy.OPENCV_FIRST
                    )
                    if result.success:
                        self._log(f"  V 检测到界面: {screen.value} (匹配: {ref_name})")
                        return screen
                    else:
                        self._log(f"  尝试 {ref_name}: 未匹配")
                except Exception as e:
                    self._log(f"  检测 {screen.value} 失败: {e}")

        self._log("  X 未识别的界面")
        return {Channel}Screen.UNKNOWN

    # ============================================================
    # 导航
    # ============================================================

    def navigate_to_home(self, max_attempts: int = 5) -> bool:
        """
        导航回首页

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功
        """
        self._log("导航回首页...")

        for attempt in range(max_attempts):
            current = self.detect_screen()
            if current == {Channel}Screen.HOME:
                self._log(f"  V 已在首页")
                return True

            self._log(f"  尝试 {attempt + 1}/{max_attempts}: 当前界面 {current.value}")

            # 按返回键
            self.runner.adb.press_back()
            time.sleep(config.OPERATION_DELAY * 2)

        return False

    def navigate_to_home_with_ai_fallback(self, max_attempts: int = 5) -> Dict[str, Any]:
        """
        导航回首页，带 AI 回退

        Args:
            max_attempts: 最大尝试次数

        Returns:
            {"success": bool, "method": str, "message": str}
        """
        # 1. 先尝试预定义方法
        if self.navigate_to_home(max_attempts):
            return {
                "success": True,
                "method": "predefined",
                "message": "预定义方法成功导航到首页"
            }

        self._log("  预定义方法失败，尝试 AI 辅助导航...")

        # 2. 使用 AI 分析（如需要）
        # TODO: 实现 AI 辅助导航

        # 最终验证
        current_screen = self.detect_screen()
        if current_screen == {Channel}Screen.HOME:
            return {
                "success": True,
                "method": "ai_assisted",
                "message": "AI 辅助导航成功"
            }

        return {
            "success": False,
            "method": "failed",
            "message": f"无法导航到首页，当前界面: {current_screen.value}"
        }

    # ============================================================
    # 工作流执行
    # ============================================================

    def execute_workflow(
        self,
        workflow: Workflow,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        执行工作流

        Args:
            workflow: 工作流定义
            params: 工作流参数

        Returns:
            执行结果 {"success": bool, "message": str, "data": Any}
        """
        self._log(f"=== 执行工作流: {workflow.name} ===")
        self._log(f"  描述: {workflow.description}")
        self._log(f"  参数: {params}")

        # 检查必需参数
        missing_params = [p for p in workflow.required_params if p not in params]
        if missing_params:
            return {
                "success": False,
                "message": f"缺少必需参数: {missing_params}",
                "data": None
            }

        # 合并默认参数
        full_params = {**workflow.optional_params, **params}

        # 0. 确保应用已打开
        if not self._ensure_app_running():
            return {
                "success": False,
                "message": "无法启动应用",
                "data": None
            }

        # 1. 检测当前界面
        current_screen = self.detect_screen()
        self._log(f"  当前界面: {current_screen.value}")

        # 2. 确保在有效起始界面
        if current_screen not in workflow.valid_start_screens:
            self._log("  不在有效起始界面，导航到首页...")
            nav_result = self.navigate_to_home_with_ai_fallback()
            if not nav_result["success"]:
                return {
                    "success": False,
                    "message": nav_result["message"],
                    "data": None
                }

        # 3. 执行工作流步骤
        for i, step in enumerate(workflow.steps):
            step_desc = self._render_template(step.description, full_params)
            self._log(f"  步骤 {i + 1}: {step_desc}")

            result = self._execute_step(step, full_params)
            if not result["success"]:
                self._log(f"  X 步骤失败: {result['message']}")

                # 尝试恢复
                if self._try_recover(step, full_params):
                    result = self._execute_step(step, full_params)
                    if not result["success"]:
                        return {
                            "success": False,
                            "message": f"步骤 {i + 1} 失败: {result['message']}",
                            "data": None
                        }
                else:
                    return {
                        "success": False,
                        "message": f"步骤 {i + 1} 失败且无法恢复: {result['message']}",
                        "data": None
                    }

            self._log(f"  V 步骤 {i + 1} 完成")

            # 检查期望界面
            if step.expect_screen:
                time.sleep(0.3)
                actual_screen = self.detect_screen()
                if actual_screen != step.expect_screen:
                    self._log(f"  ! 界面不符: 期望 {step.expect_screen.value}, 实际 {actual_screen.value}")

        self._log("=== 工作流完成 ===")
        return {
            "success": True,
            "message": "工作流执行成功",
            "data": None
        }

    def _execute_step(self, step: NavStep, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个步骤

        Args:
            step: 步骤定义
            params: 参数

        Returns:
            {"success": bool, "message": str}
        """
        action = step.action
        target = self._render_template(step.target, params) if step.target else None
        step_params = {k: self._render_template(str(v), params) if isinstance(v, str) else v
                       for k, v in step.params.items()}

        try:
            if action == "tap":
                return self._action_tap(target)

            elif action == "press_key":
                keycode = step_params.get("keycode", 4)
                self.runner.adb.press_key(keycode)
                time.sleep(step.max_wait / 1000)
                return {"success": True, "message": "按键成功"}

            elif action == "wait":
                duration = step_params.get("duration", 1000)
                time.sleep(duration / 1000)
                return {"success": True, "message": "等待完成"}

            elif action == "input_text":
                text = step_params.get("text", "")
                return self._action_input_text(target, text)

            elif action == "check":
                return self._action_check(target)

            elif action == "swipe":
                direction = step_params.get("direction", "up")
                return self._action_swipe(direction)

            else:
                return {"success": False, "message": f"未知动作: {action}"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _action_tap(self, target: str) -> Dict[str, Any]:
        """点击目标"""
        ref_paths = self.handler.get_image_variants(target)
        if not ref_paths:
            return {"success": False, "message": f"找不到参考图: {target}"}

        screenshot, top_offset = self.runner._capture_screenshot_cropped()
        screenshot_bytes = self._image_to_bytes(screenshot)

        for ref_path in ref_paths:
            result = self.runner.hybrid_locator.locate(
                screenshot_bytes, ref_path, LocateStrategy.OPENCV_FIRST
            )
            if result.success:
                tap_y = result.center_y + top_offset
                self.runner.adb.tap(result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY)
                return {"success": True, "message": "点击成功"}

        return {"success": False, "message": f"未找到目标: {target}"}

    def _action_input_text(self, target: str, text: str) -> Dict[str, Any]:
        """输入文本"""
        # 先点击输入框
        tap_result = self._action_tap(target)
        if not tap_result["success"]:
            return tap_result

        time.sleep(config.OPERATION_DELAY)

        # 输入文本
        self.runner.adb.input_text(text)
        return {"success": True, "message": "输入成功"}

    def _action_check(self, target: str) -> Dict[str, Any]:
        """检查目标是否存在"""
        ref_path = self.handler.get_image_path(target)
        if not ref_path:
            return {"success": False, "message": f"找不到参考图: {target}"}

        screenshot = self.runner._capture_screenshot()
        screenshot_bytes = self._image_to_bytes(screenshot)

        result = self.runner.hybrid_locator.locate(
            screenshot_bytes, ref_path, LocateStrategy.OPENCV_FIRST
        )
        if result.success:
            return {"success": True, "message": "检查通过"}
        return {"success": False, "message": f"未找到目标: {target}"}

    def _action_swipe(self, direction: str) -> Dict[str, Any]:
        """滑动"""
        self.runner.adb.swipe(direction)
        time.sleep(config.OPERATION_DELAY)
        return {"success": True, "message": "滑动完成"}

    def _try_recover(self, failed_step: NavStep, params: Dict[str, Any]) -> bool:
        """
        尝试从失败中恢复

        Args:
            failed_step: 失败的步骤
            params: 参数

        Returns:
            是否恢复成功
        """
        self._log("  尝试恢复...")

        # 检测当前界面
        current = self.detect_screen()

        # 如果在未知界面，尝试回首页
        if current == {Channel}Screen.UNKNOWN:
            return self.navigate_to_home()

        return False


# ============================================================
# 参数解析
# ============================================================

def parse_task_params(task: str, param_hints: Dict[str, str]) -> Dict[str, Any]:
    """
    从任务描述中解析参数

    Args:
        task: 任务描述
        param_hints: 参数提示

    Returns:
        解析出的参数
    """
    params = {}

    # TODO: 根据频道特点实现参数解析逻辑
    # 示例：
    # if "keyword" in param_hints:
    #     match = re.search(r'搜索\s*(.+)', task)
    #     if match:
    #         params["keyword"] = match.group(1).strip()

    return params
