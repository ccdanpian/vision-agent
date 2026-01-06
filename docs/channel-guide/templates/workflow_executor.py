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
        self._max_back_presses = config.WORKFLOW_MAX_BACK_PRESSES
        self._back_press_interval = config.WORKFLOW_BACK_PRESS_INTERVAL
        self._max_step_retries = config.WORKFLOW_MAX_STEP_RETRIES
        self._local_only = False  # 当前是否处于 local_only 模式

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

    def _ensure_at_home_screen(self, max_attempts: int = None) -> bool:
        """
        确保应用处于首页

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功回到首页
        """
        if max_attempts is None:
            max_attempts = config.WORKFLOW_HOME_MAX_ATTEMPTS

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

    def navigate_to_home(self, max_attempts: int = None) -> bool:
        """
        导航回首页

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功
        """
        if max_attempts is None:
            max_attempts = config.WORKFLOW_HOME_MAX_ATTEMPTS

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

    def navigate_to_home_with_ai_fallback(self, max_attempts: int = None) -> Dict[str, Any]:
        """
        导航回首页，带 AI 回退

        Args:
            max_attempts: 最大尝试次数

        Returns:
            {"success": bool, "method": str, "message": str}
        """
        if max_attempts is None:
            max_attempts = config.WORKFLOW_HOME_MAX_ATTEMPTS

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
        params: Dict[str, Any],
        local_only: bool = False
    ) -> Dict[str, Any]:
        """
        执行工作流

        Args:
            workflow: 工作流定义
            params: 工作流参数
            local_only: 是否仅使用本地匹配（禁用AI回退）

        Returns:
            执行结果 {"success": bool, "message": str, "data": Any}
        """
        # 设置 local_only 模式
        self._local_only = local_only

        self._log(f"=== 执行工作流: {workflow.name} ===")
        self._log(f"  描述: {workflow.description}")
        self._log(f"  参数: {params}")
        if local_only:
            self._log(f"  模式: local_only（纯本地匹配，无AI回退）")

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

        # 记录可跳过的步骤索引
        skip_to_step = 0

        # 使用 try-finally 确保任务完成后执行复位
        try:
            # ===============================================
            # 【智能优化】在预置流程之前先检测是否可以跳过导航
            # ===============================================
            if self._local_only:
                self._log("  [智能检测] 检测是否可跳过导航步骤...")
                skip_to_step = self._check_smart_skip(workflow, full_params)

                if skip_to_step > 0:
                    self._log(f"  ★ 智能跳过: 已在目标界面，跳过前 {skip_to_step} 步")
                    # 只确保应用在前台，不导航到首页
                    # self.runner.adb.start_app(APP_PACKAGE)
                else:
                    # 执行完整预置流程
                    preset_success = self._ensure_app_running()
                    if not preset_success:
                        self._log("  ⚠ 预置流程失败，但仍尝试继续执行正式任务...")
            else:
                # 非 local_only 模式：执行完整预置流程
                preset_success = self._ensure_app_running()
                if not preset_success:
                    self._log("  ⚠ 预置流程失败，但仍尝试继续执行正式任务...")

            # 如果已经智能跳过，不需要再检测界面和导航
            if skip_to_step == 0:
                # 检测当前界面
                current_screen = self.detect_screen()
                self._log(f"  当前界面: {current_screen.value}")

                # 确保在有效起始界面
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
                # 智能跳过已完成的步骤
                if i < skip_to_step:
                    step_desc = self._render_template(step.description, full_params)
                    self._log(f"  步骤 {i + 1}: {step_desc} [跳过]")
                    continue
                step_desc = self._render_template(step.description, full_params)
                self._log(f"  步骤 {i + 1}: {step_desc}")

                # 步骤执行与重试循环
                step_success = False
                last_error = ""

                for retry in range(self._max_step_retries):
                    if retry > 0:
                        self._log(f"  重试第 {retry}/{self._max_step_retries - 1} 次...")

                    result = self._execute_step(step, full_params)
                    if result["success"]:
                        step_success = True
                        break

                    last_error = result["message"]
                    self._log(f"  ✗ 步骤失败: {last_error}")

                    # 最后一次重试不需要恢复/等待
                    if retry < self._max_step_retries - 1:
                        if self._local_only:
                            # local_only 模式：简单等待后重试（避免调用 AI 的恢复逻辑）
                            wait_time = config.OPERATION_DELAY * 2  # 等待约 1 秒
                            self._log(f"  [local_only] 等待 {wait_time}ms 后重试...")
                            time.sleep(wait_time / 1000)
                        else:
                            # 正常模式：尝试恢复
                            if not self._try_recover(step, full_params):
                                self._log(f"  ✗ 恢复失败，继续重试...")

                if not step_success:
                    return {
                        "success": False,
                        "message": f"步骤 {i + 1} 失败（已重试{self._max_step_retries}次）: {last_error}",
                        "data": None
                    }

                self._log(f"  ✓ 步骤 {i + 1} 完成")

                # 检查期望界面
                if step.expect_screen:
                    time.sleep(0.3)
                    # local_only 模式下跳过完整界面检测（避免AI调用）
                    if self._local_only:
                        self._log(f"  [local_only] 跳过界面验证 (期望: {step.expect_screen.value})")
                    else:
                        actual_screen = self.detect_screen()
                        if actual_screen != step.expect_screen:
                            self._log(f"  ! 界面不符: 期望 {step.expect_screen.value}, 实际 {actual_screen.value}")

            self._log("=== 工作流完成 ===")
            return {
                "success": True,
                "message": "工作流执行成功",
                "data": None
            }

        finally:
            # 重置 local_only 模式
            self._local_only = False

            # 任务完成后执行复位（无论成功还是失败）
            self._log("")
            self._log("【复位流程】任务完成后复位")
            self._log("")

            try:
                reset_success = self._ensure_at_home_screen()
                if reset_success:
                    self._log("✓ 复位成功，已返回首页")
                else:
                    self._log("⚠️  复位失败，但不影响任务结果")
            except Exception as e:
                self._log(f"⚠️  复位过程出现异常: {e}")

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

        # 根据 local_only 模式选择定位策略
        strategy = LocateStrategy.OPENCV_ONLY if self._local_only else LocateStrategy.OPENCV_FIRST

        for ref_path in ref_paths:
            result = self.runner.hybrid_locator.locate(
                screenshot_bytes, ref_path, strategy
            )
            if result.success:
                tap_y = result.center_y + top_offset
                self.runner.adb.tap(result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY)
                return {"success": True, "message": "点击成功"}

        if self._local_only:
            self._log(f"  [local_only] OpenCV匹配失败: {target}")

        return {"success": False, "message": f"未找到目标: {target}"}

    def _action_input_text(self, target: str, text: str) -> Dict[str, Any]:
        """输入文本"""
        # 先点击输入框
        tap_result = self._action_tap(target)
        if not tap_result["success"]:
            return tap_result

        time.sleep(config.OPERATION_DELAY)

        # 先清空输入框（全选+删除）
        self._log("  清空输入框...")
        self.runner.adb.clear_text_field()
        time.sleep(0.2)

        # 输入文本（使用支持中文的方法）
        success = self.runner.adb.input_text_chinese(text)
        if success:
            return {"success": True, "message": "输入成功"}
        else:
            return {"success": False, "message": "输入失败"}

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

    def _check_smart_skip(
        self,
        workflow: Workflow,
        params: Dict[str, Any]
    ) -> int:
        """
        智能检测是否可以跳过前置步骤

        在预置流程之前调用，检测是否已在目标界面，可以跳过导航步骤。
        例如：如果已在聊天界面，可以跳过"点击联系人"步骤。

        Args:
            workflow: 当前工作流
            params: 工作流参数

        Returns:
            可跳过的步骤数（0 表示不跳过）
        """
        # 只在 local_only 模式下启用智能跳过
        if not self._local_only:
            return 0

        self._log("  [智能跳过] 检测当前界面...")

        # 获取截图
        screenshot = self.runner._capture_screenshot()
        screenshot_bytes = self._image_to_bytes(screenshot)

        # TODO: 根据工作流类型进行检测
        # 示例（发消息工作流）:
        # if workflow.name == "send_message_local":
        #     contact = params.get("contact", "")
        #     if contact:
        #         # 检测是否已在与该联系人的聊天界面
        #         chat_ref_paths = self.handler.get_image_variants(f"chatting_with_{contact}")
        #         if chat_ref_paths:
        #             for ref_path in chat_ref_paths:
        #                 result = self.runner.hybrid_locator.locate(
        #                     screenshot_bytes, ref_path, LocateStrategy.OPENCV_ONLY
        #                 )
        #                 if result.success:
        #                     self._log(f"  [智能跳过] ✓ 已在 {contact} 的聊天界面")
        #                     return 1  # 跳过第一步（点击联系人）

        return 0

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
