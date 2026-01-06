"""
apps/wechat/workflow_executor.py
工作流执行器 - 执行预定义的工作流

职责：
- 检测当前界面状态
- 导航到工作流起始点
- 执行工作流步骤
- 错误恢复和重试
"""
import time
import re
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from PIL import Image

import config
from core.hybrid_locator import LocateStrategy
from .workflows import (
    Workflow, NavStep, WeChatScreen,
    SCREEN_DETECT_REFS, SCREEN_DETECT_REFS_FALLBACK,
    NAV_TO_HOME, WORKFLOWS, match_workflow
)


class WorkflowExecutor:
    """工作流执行器"""

    def __init__(self, task_runner, handler):
        """
        初始化执行器

        Args:
            task_runner: TaskRunner 实例（用于执行操作）
            handler: WeChatHandler 实例（用于获取参考图）
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
            self._logger(f"[Workflow] {message}")
        else:
            print(f"[Workflow] {message}")

    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """将 PIL Image 转换为 bytes"""
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

    def _ensure_wechat_running(self) -> bool:
        """
        确保微信已打开并在前台，且处于首页状态

        流程：
        1. 检查/启动微信
        2. 确保回到首页（消息Tab页面）

        Returns:
            是否成功确保微信在首页
        """
        WECHAT_PACKAGE = "com.tencent.mm"

        self._log("")
        self._log("╔════════════════════════════════════════╗")
        self._log("║       【预置流程】正式任务前准备        ║")
        self._log("╚════════════════════════════════════════╝")
        self._log("")
        self._log("[预置] 步骤0: 使用系统指令启动微信")

        # 无条件使用系统指令启动微信（确保微信在前台）
        self._log("  执行启动微信指令...")
        self.runner.adb.start_app(WECHAT_PACKAGE)
        time.sleep(config.OPERATION_DELAY * 4)  # 等待微信启动

        # 验证微信是否启动成功
        current_app = self.runner.adb.get_current_app()
        self._log(f"  当前前台应用: {current_app}")

        if current_app != WECHAT_PACKAGE:
            if current_app is None:
                self._log("  无法检测前台应用，通过截图验证...")
                time.sleep(config.OPERATION_DELAY * 2)
                current_screen = self.detect_screen()
                if current_screen == WeChatScreen.UNKNOWN:
                    self._log(f"  ✗ 微信启动失败")
                    return False
                else:
                    self._log(f"  ✓ 检测到微信界面: {current_screen.value}")
            else:
                self._log(f"  ✗ 微信启动失败，当前应用: {current_app}")
                return False
        else:
            self._log("  ✓ 微信已在前台")

        # === 确保回到首页（消息Tab页面）===
        return self._ensure_at_home_screen()

    def _ensure_at_home_screen(self, max_attempts: int = None) -> bool:
        """
        确保微信处于首页（消息页面）

        流程：
        1. 用 wechat_news_button 检测是否能看到底部消息Tab
        2. 如果能看到，直接返回成功
        3. 如果看不到，优先点击取消按钮，其次点击返回按钮
        4. 重复直到能看到消息Tab

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功回到首页
        """
        if max_attempts is None:
            max_attempts = config.WORKFLOW_HOME_MAX_ATTEMPTS

        self._log("")
        self._log("[预置] 步骤1: 确保微信在消息页面")

        for attempt in range(max_attempts):
            self._log(f"  检测第 {attempt + 1}/{max_attempts} 次...")
            # 使用裁剪截图（去除状态栏和导航栏）
            screenshot, top_offset = self.runner._capture_screenshot_cropped()
            screenshot_bytes = self._image_to_bytes(screenshot)

            # 获取所有需要检测的目标
            home_btn_paths = self.handler.get_image_variants("wechat_home_button")
            cancel_paths = self.handler.get_image_variants("wechat_cancel_button")
            back_paths = self.handler.get_image_variants("wechat_back")

            # 调试：显示获取到的变体
            self._log(f"    home_button 变体: {[p.name for p in home_btn_paths] if home_btn_paths else '无'}")
            self._log(f"    cancel_button 变体: {[p.name for p in cancel_paths] if cancel_paths else '无'}")
            self._log(f"    back_button 变体: {[p.name for p in back_paths] if back_paths else '无'}")

            # 构建并行检测目标
            targets = {}
            if home_btn_paths:
                targets["home_button"] = home_btn_paths
            if cancel_paths:
                targets["cancel_button"] = cancel_paths
            if back_paths:
                targets["back_button"] = back_paths

            if not targets:
                self._log(f"  无可用参考图，按物理返回键")
                self.runner.adb.press_back()
                time.sleep(config.OPERATION_DELAY * 2)
                continue

            # 统计总变体数
            total_variants = sum(len(paths) for paths in targets.values())
            self._log(f"  并行检测 {len(targets)} 个目标, 共 {total_variants} 个变体（仅OpenCV）...")
            results = self.runner.hybrid_locator.locate_multiple_parallel(
                screenshot_bytes, targets
            )

            # 检查是否能看到消息Tab
            home_result = results.get("home_button")
            if home_result and home_result.success:
                # 点击 home_button 确保进入聊天列表页（坐标需要加上 top_offset）
                tap_y = home_result.center_y + top_offset
                self._log(f"  检测到消息Tab，点击进入聊天界面 ({home_result.center_x}, {tap_y}) [原始y={home_result.center_y}, offset={top_offset}]")
                self.runner.adb.tap(home_result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY * 2)
                self._log(f"  ✓ 已进入消息页面")
                self._log("")
                self._log("╔════════════════════════════════════════╗")
                self._log("║     【预置流程完成】开始执行正式任务    ║")
                self._log("╚════════════════════════════════════════╝")
                self._log("")
                return True

            self._log(f"  未检测到消息Tab，尝试返回...")

            # 优先点击取消按钮
            cancel_result = results.get("cancel_button")
            if cancel_result and cancel_result.success:
                tap_y = cancel_result.center_y + top_offset
                self._log(f"  找到取消按钮，点击 ({cancel_result.center_x}, {tap_y}) [原始y={cancel_result.center_y}]")
                self.runner.adb.tap(cancel_result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY * 2)
                continue

            # 其次点击返回按钮
            # 注意：由于已经裁剪掉了系统导航栏，不再需要过滤底部区域
            back_result = results.get("back_button")
            if back_result and back_result.success:
                tap_y = back_result.center_y + top_offset
                self._log(f"  找到返回按钮，点击 ({back_result.center_x}, {tap_y}) [原始y={back_result.center_y}]")
                self.runner.adb.tap(back_result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY * 2)
                continue

            # 都没找到，等待后重试（不使用物理返回键）
            self._log(f"  未找到取消/返回按钮，等待后重试...")
            time.sleep(config.OPERATION_DELAY * 2)

        # 最后再检查一次（仅OpenCV）- 使用裁剪截图
        self._log(f"  最终检测...")
        screenshot, top_offset = self.runner._capture_screenshot_cropped()
        screenshot_bytes = self._image_to_bytes(screenshot)

        home_btn_paths = self.handler.get_image_variants("wechat_home_button")
        if home_btn_paths:
            results = self.runner.hybrid_locator.locate_multiple_parallel(
                screenshot_bytes, {"home_button": home_btn_paths}
            )
            home_result = results.get("home_button")

            if home_result and home_result.success:
                # 点击 home_button 确保进入聊天列表页（坐标加上 top_offset）
                tap_y = home_result.center_y + top_offset
                self._log(f"  检测到消息Tab，点击进入聊天界面 ({home_result.center_x}, {tap_y}) [原始y={home_result.center_y}]")
                self.runner.adb.tap(home_result.center_x, tap_y)
                time.sleep(config.OPERATION_DELAY * 2)
                self._log(f"  ✓ 已进入消息页面")
                self._log("")
                self._log("╔════════════════════════════════════════╗")
                self._log("║     【预置流程完成】开始执行正式任务    ║")
                self._log("╚════════════════════════════════════════╝")
                self._log("")
                return True

        self._log(f"  ✗ 无法回到消息页面")
        self._log("[预置] 预置流程失败，无法继续执行正式任务")
        return False

    def detect_screen(self, screenshot: Optional[Image.Image] = None) -> WeChatScreen:
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

        # 按优先级检测各界面（首页最优先）
        detection_order = [
            WeChatScreen.HOME,
            WeChatScreen.CONTACTS,
            WeChatScreen.DISCOVER,
            WeChatScreen.ME,
            WeChatScreen.CHAT,
            WeChatScreen.MOMENTS,
            WeChatScreen.SEARCH,
        ]

        # 转换截图为 bytes（hybrid_locator 需要）
        screenshot_bytes = self._image_to_bytes(screenshot)

        for screen in detection_order:
            # 获取主参考图和备用参考图
            ref_names = []
            if screen in SCREEN_DETECT_REFS:
                ref_names.append(SCREEN_DETECT_REFS[screen])
            if screen in SCREEN_DETECT_REFS_FALLBACK:
                ref_names.append(SCREEN_DETECT_REFS_FALLBACK[screen])

            for ref_name in ref_names:
                # 获取参考图路径
                ref_path = self.handler.get_image_path(ref_name)
                if not ref_path or not ref_path.exists():
                    self._log(f"  参考图不存在: {ref_name}")
                    continue

                # 使用 OpenCV 检测
                try:
                    result = self.runner.hybrid_locator.locate(
                        screenshot_bytes,
                        ref_path,
                        LocateStrategy.OPENCV_FIRST
                    )
                    if result.success:
                        self._log(f"  ✓ 检测到界面: {screen.value} (匹配: {ref_name})")
                        return screen
                    else:
                        self._log(f"  尝试 {ref_name}: 未匹配")
                except Exception as e:
                    self._log(f"  检测 {screen.value} 失败: {e}")

        self._log("  ✗ 未识别的界面")
        return WeChatScreen.UNKNOWN

    # 返回/取消按钮的参考图名称（系统会自动查找 _v1, _v2 等变体）
    _BACK_BUTTON_REFS = [
        "wechat_back",           # 返回按钮（左上角箭头）
    ]
    _CANCEL_BUTTON_REFS = [
        "wechat_cancel_button",  # 取消按钮
        "dynamic:取消",          # 动态查找取消
    ]

    def _try_click_back_or_cancel(self, screenshot: Image.Image) -> bool:
        """
        尝试点击返回或取消按钮

        策略：
        1. 先检查是否有返回按钮（包括所有变体），有则点击
        2. 再检查是否有取消按钮，有则点击
        3. 都没有则返回 False

        Returns:
            是否成功点击了按钮
        """
        screenshot_bytes = self._image_to_bytes(screenshot)

        # 1. 尝试点击返回按钮（使用变体匹配）
        for ref_name in self._BACK_BUTTON_REFS:
            ref_paths = self.handler.get_image_variants(ref_name)
            if ref_paths:
                try:
                    if len(ref_paths) > 1:
                        self._log(f"  尝试匹配 {ref_name} (+{len(ref_paths)-1} 变体)")
                        result = self.runner.hybrid_locator.locate_with_variants(
                            screenshot_bytes,
                            ref_paths,
                            LocateStrategy.OPENCV_FIRST
                        )
                    else:
                        result = self.runner.hybrid_locator.locate(
                            screenshot_bytes,
                            ref_paths[0],
                            LocateStrategy.OPENCV_FIRST
                        )
                    if result.success:
                        matched = result.details.get('matched_variant', ref_paths[0].name)
                        self._log(f"  找到返回按钮: {matched}, 点击 ({result.center_x}, {result.center_y})")
                        self.runner.adb.tap(result.center_x, result.center_y)
                        return True
                except Exception as e:
                    self._log(f"  匹配 {ref_name} 失败: {e}")

        # 2. 尝试点击取消按钮
        for ref_name in self._CANCEL_BUTTON_REFS:
            if ref_name.startswith("dynamic:"):
                # 动态查找（使用 VisionAgent）
                coords = self.runner.locator.find_element(screenshot, ref_name[8:])
                if coords:
                    self._log(f"  找到取消按钮: {ref_name}, 点击 ({coords[0]}, {coords[1]})")
                    self.runner.adb.tap(coords[0], coords[1])
                    return True
            else:
                ref_path = self.handler.get_image_path(ref_name)
                if ref_path and ref_path.exists():
                    try:
                        result = self.runner.hybrid_locator.locate(
                            screenshot_bytes,
                            ref_path,
                            LocateStrategy.OPENCV_FIRST
                        )
                        if result.success:
                            self._log(f"  找到取消按钮: {ref_name}, 点击 ({result.center_x}, {result.center_y})")
                            self.runner.adb.tap(result.center_x, result.center_y)
                            return True
                    except Exception:
                        pass

        return False

    def navigate_to_home(self, max_attempts: int = None) -> bool:
        """
        导航回首页

        策略：
        1. 检测是否已在首页（用参考图 system/wechat_home_page）
        2. 检查是否有返回按钮或取消按钮，有则点击
        3. 如果没有按钮，按物理返回键
        4. 重复直到到达首页或超过最大次数

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功到达首页
        """
        if max_attempts is None:
            max_attempts = config.WORKFLOW_HOME_MAX_ATTEMPTS

        self._log("=== 导航到首页 ===")

        for attempt in range(max_attempts):
            # 截图检测当前界面
            screenshot = self.runner._capture_screenshot()
            current_screen = self.detect_screen(screenshot)

            if current_screen == WeChatScreen.HOME:
                self._log(f"  ✓ 已到达首页 (尝试 {attempt + 1} 次)")
                return True

            self._log(f"  当前: {current_screen.value}, 尝试 {attempt + 1}/{max_attempts}")

            # 尝试点击返回或取消按钮
            if self._try_click_back_or_cancel(screenshot):
                self._log(f"  已点击界面按钮")
            else:
                # 没有找到按钮，按物理返回键
                self._log(f"  未找到返回/取消按钮，按物理返回键...")
                self.runner.adb.press_back()  # KEYCODE_BACK = 4

            time.sleep(self._back_press_interval / 1000)

        # 最后再检查一次
        current_screen = self.detect_screen()
        if current_screen == WeChatScreen.HOME:
            self._log(f"  ✓ 已到达首页")
            return True

        self._log(f"  ✗ 预定义方法未能到达首页，当前: {current_screen.value}")
        return False

    def navigate_to_home_with_ai_fallback(self, max_attempts: int = None) -> Dict[str, Any]:
        """
        导航回首页，带 AI 回退

        流程：
        1. 先尝试预定义方法
        2. 如果失败，让 AI 分析当前界面并尝试导航

        Args:
            max_attempts: 预定义方法的最大尝试次数

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

        # 2. 使用 AI 分析并尝试导航
        for ai_attempt in range(config.WORKFLOW_AI_FALLBACK_ATTEMPTS):
            screenshot = self.runner._capture_screenshot()

            # 让 AI 分析当前界面并给出导航建议
            ai_result = self._ai_navigate_step(screenshot, ai_attempt + 1)

            if ai_result["at_home"]:
                self._log(f"  ✓ AI 辅助成功到达首页 (尝试 {ai_attempt + 1} 次)")
                return {
                    "success": True,
                    "method": "ai_assisted",
                    "message": f"AI 辅助导航成功 (尝试 {ai_attempt + 1} 次)"
                }

            if not ai_result["action_taken"]:
                # AI 无法识别或无法给出建议
                self._log(f"  AI 无法继续导航: {ai_result['message']}")
                break

            time.sleep(0.5)

        # 最终验证
        current_screen = self.detect_screen()
        if current_screen == WeChatScreen.HOME:
            return {
                "success": True,
                "method": "ai_assisted",
                "message": "AI 辅助导航成功"
            }

        return {
            "success": False,
            "method": "failed",
            "message": f"预定义方法和 AI 辅助都无法导航到首页，当前界面: {current_screen.value}"
        }

    def _ai_navigate_step(self, screenshot: Image.Image, attempt: int) -> Dict[str, Any]:
        """
        让 AI 分析界面并执行一步导航

        Returns:
            {"at_home": bool, "action_taken": bool, "message": str}
        """
        try:
            # 先检查是否已在首页
            current_screen = self.detect_screen(screenshot)
            if current_screen == WeChatScreen.HOME:
                return {"at_home": True, "action_taken": False, "message": "已在首页"}

            # 调用 AI 分析
            vision_agent = self.runner.planner.vision

            prompt = f"""分析当前微信界面截图，我需要返回微信首页（聊天列表页面）。

当前状态：
- 这是第 {attempt} 次尝试用 AI 导航
- 预定义的返回按钮检测已失败

请分析截图并告诉我：
1. 当前在什么界面？
2. 如何返回首页？具体应该点击哪里？

如果可以导航，返回 JSON：
{{"can_navigate": true, "action": "tap", "description": "点击位置描述", "x": 像素X, "y": 像素Y}}

如果当前已经在首页，返回：
{{"can_navigate": false, "at_home": true}}

如果无法确定如何导航，返回：
{{"can_navigate": false, "at_home": false, "reason": "原因"}}

只返回 JSON，不要其他内容。"""

            import base64
            from io import BytesIO
            buffer = BytesIO()
            screenshot.save(buffer, format='PNG')
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            response = vision_agent._call_openai_compatible(
                "你是 Android 界面分析助手，负责分析屏幕截图并给出导航建议。只返回 JSON。",
                prompt,
                image_base64=image_base64,
                json_mode=True
            )

            self._log(f"  AI 导航响应: {response[:150]}...")

            # 解析响应
            import json
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())

                if result.get("at_home"):
                    return {"at_home": True, "action_taken": False, "message": "AI 判断已在首页"}

                if result.get("can_navigate"):
                    # 执行 AI 建议的操作
                    x = result.get("x")
                    y = result.get("y")
                    action = result.get("action", "tap")
                    desc = result.get("description", "AI 建议的位置")

                    if x and y:
                        self._log(f"  AI 建议: {action} ({x}, {y}) - {desc}")
                        if action == "tap":
                            self.runner.adb.tap(x, y)
                        elif action == "back":
                            self.runner.adb.press_back()
                        return {"at_home": False, "action_taken": True, "message": f"执行 AI 建议: {desc}"}

                return {
                    "at_home": False,
                    "action_taken": False,
                    "message": result.get("reason", "AI 无法给出导航建议")
                }

        except Exception as e:
            self._log(f"  AI 导航分析失败: {e}")

        return {"at_home": False, "action_taken": False, "message": f"AI 分析异常"}

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

        # 使用 try-finally 确保任务完成后执行复位
        # 记录可跳过的步骤索引
        skip_to_step = 0

        try:
            # ===============================================
            # 【智能优化】在预置流程之前先检测是否可以跳过导航
            # ===============================================
            if self._local_only:
                self._log("")
                self._log("╔════════════════════════════════════════╗")
                self._log("║    【智能检测】检测是否可跳过导航步骤    ║")
                self._log("╚════════════════════════════════════════╝")
                self._log("")

                skip_to_step = self._check_smart_skip(workflow, full_params)

                if skip_to_step > 0:
                    self._log(f"  ★ 智能跳过: 已在目标界面，跳过前 {skip_to_step} 步")
                    self._log(f"  跳过完整预置流程，仅确保微信在前台...")

                    # 只确保微信在前台，不导航到首页
                    WECHAT_PACKAGE = "com.tencent.mm"
                    current_app = self.runner.adb.get_current_app()
                    if current_app != WECHAT_PACKAGE:
                        self._log(f"  微信不在前台，启动微信...")
                        self.runner.adb.start_app(WECHAT_PACKAGE)
                        time.sleep(config.OPERATION_DELAY * 4)

                    self._log("")
                    self._log("╔════════════════════════════════════════╗")
                    self._log("║     【预置流程跳过】直接执行正式任务    ║")
                    self._log("╚════════════════════════════════════════╝")
                    self._log("")
                else:
                    self._log(f"  未检测到可跳过情况，执行完整预置流程")
                    # 执行完整预置流程
                    preset_success = self._ensure_wechat_running()
                    if not preset_success:
                        self._log("  ⚠ 预置流程失败，但仍尝试继续执行正式任务...")
            else:
                # 非 local_only 模式：执行完整预置流程
                preset_success = self._ensure_wechat_running()
                if not preset_success:
                    self._log("  ⚠ 预置流程失败，但仍尝试继续执行正式任务...")

            # 如果已经智能跳过，不需要再检测界面和导航
            if skip_to_step == 0:
                # 检测当前界面
                current_screen = self.detect_screen()
                self._log(f"  当前界面: {current_screen.value}")
                self._log(f"  有效起点: {[s.value for s in workflow.valid_start_screens]}")

                # 确保在有效起始界面
                # 策略：如果不确定在正确位置，就先导航到首页
                need_navigate = False

                if current_screen == WeChatScreen.UNKNOWN:
                    # 未识别的界面，必须先回首页
                    self._log(f"  未识别界面，需要先回首页")
                    need_navigate = True
                elif current_screen not in workflow.valid_start_screens:
                    # 不在有效起始界面
                    self._log(f"  不在有效起始界面，需要先回首页")
                    need_navigate = True
                elif current_screen != WeChatScreen.HOME and WeChatScreen.HOME in workflow.valid_start_screens:
                    # 虽然在有效起点（如 CHAT），但首页也是有效起点，优先回首页
                    # 因为从首页开始更可靠
                    self._log(f"  当前在 {current_screen.value}，但优先从首页开始")
                    need_navigate = True

                if need_navigate:
                    self._log(f"  === 导航到首页（带 AI 回退）===")
                    nav_result = self.navigate_to_home_with_ai_fallback()

                    if not nav_result["success"]:
                        self._log(f"  ✗ 导航失败: {nav_result['message']}")
                        return {
                            "success": False,
                            "message": nav_result["message"],
                            "data": None
                        }

                    self._log(f"  ✓ 已确认在首页 (方法: {nav_result['method']})")

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

                # 检查是否到达期望界面
                if step.expect_screen:
                    time.sleep(0.3)  # 等待界面切换
                    # local_only 模式下跳过完整界面检测（避免AI调用）
                    if self._local_only:
                        self._log(f"  [local_only] 跳过界面验证 (期望: {step.expect_screen.value})")
                    else:
                        actual_screen = self.detect_screen()
                        if actual_screen != step.expect_screen:
                            self._log(f"  ! 界面不符: 期望 {step.expect_screen.value}, 实际 {actual_screen.value}")

            self._log(f"=== 工作流完成 ===")
            return {
                "success": True,
                "message": "工作流执行成功",
                "data": None
            }

        finally:
            # 重置 local_only 模式
            self._local_only = False

            # 根据配置决定是否执行复位
            if config.WORKFLOW_RESET_AFTER_TASK:
                # 任务完成后执行复位（无论成功还是失败）
                self._log("")
                self._log("╔════════════════════════════════════════╗")
                self._log("║       【复位流程】任务完成后复位        ║")
                self._log("╚════════════════════════════════════════╝")
                self._log("")

                try:
                    reset_success = self._ensure_at_home_screen()
                    if reset_success:
                        self._log("✓ 复位成功，已返回首页")
                    else:
                        self._log("⚠️  复位失败，但不影响任务结果")
                except Exception as e:
                    self._log(f"⚠️  复位过程出现异常: {e}")
                    self._log("  （不影响任务结果）")
            else:
                self._log("")
                self._log("  [配置] 跳过复位流程 (WORKFLOW_RESET_AFTER_TASK=false)")
                self._log("")

    def _execute_step(
        self,
        step: NavStep,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行单个步骤"""
        action = step.action
        target = self._render_template(step.target, params) if step.target else None
        step_params = {
            k: self._render_template(str(v), params) if isinstance(v, str) else v
            for k, v in step.params.items()
        }

        try:
            if action == "check":
                # 检查界面状态
                current = self.detect_screen()
                if step.expect_screen and current == step.expect_screen:
                    return {"success": True, "message": "界面匹配"}
                return {"success": False, "message": f"界面不匹配: {current.value}"}

            elif action == "tap":
                return self._action_tap(target)

            elif action == "long_press":
                return self._action_long_press(target, step_params.get("duration", 1000))

            elif action == "input_text":
                text = step_params.get("text", "")
                return self._action_input_text(target, text)

            elif action == "press_key":
                keycode = step_params.get("keycode", 4)
                self.runner.adb.input_keyevent(keycode)
                return {"success": True, "message": f"按键 {keycode}"}

            elif action == "swipe":
                direction = step_params.get("direction", "up")
                return self._action_swipe(direction)

            elif action == "wait":
                duration = step_params.get("duration", 500)
                time.sleep(duration / 1000)
                return {"success": True, "message": f"等待 {duration}ms"}

            elif action == "screenshot":
                save_as = step_params.get("save_as")
                screenshot = self.runner._capture_screenshot()
                if save_as:
                    screenshot.save(save_as)
                return {"success": True, "message": "截图成功", "data": screenshot}

            elif action == "nav_to_home":
                success = self.navigate_to_home()
                return {"success": success, "message": "导航到首页" if success else "导航失败"}

            elif action == "sub_workflow":
                # 执行子工作流
                sub_name = step_params.get("workflow")
                if sub_name not in WORKFLOWS:
                    return {"success": False, "message": f"未知工作流: {sub_name}"}

                sub_workflow = WORKFLOWS[sub_name]
                # 传递参数
                sub_params = {k: v for k, v in step_params.items() if k != "workflow"}
                return self.execute_workflow(sub_workflow, sub_params)

            elif action == "find_or_search":
                # 先尝试直接找，找不到就搜索
                return self._action_find_or_search(target, step_params.get("search_fallback", True))

            elif action == "conditional":
                # 条件执行（跳过处理）
                return {"success": True, "message": "条件步骤跳过"}

            else:
                return {"success": False, "message": f"未知动作: {action}"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _action_tap(self, target: str) -> Dict[str, Any]:
        """点击操作"""
        screenshot = self.runner._capture_screenshot()

        # 尝试定位目标
        coords = self._locate_target(target, screenshot)
        if not coords:
            return {"success": False, "message": f"未找到目标: {target}"}

        x, y = coords
        self.runner.adb.tap(x, y)
        return {"success": True, "message": f"点击 ({x}, {y})"}

    def _action_long_press(self, target: str, duration: int = 1000) -> Dict[str, Any]:
        """长按操作"""
        screenshot = self.runner._capture_screenshot()

        coords = self._locate_target(target, screenshot)
        if not coords:
            return {"success": False, "message": f"未找到目标: {target}"}

        x, y = coords
        self.runner.adb.long_press(x, y, duration)
        return {"success": True, "message": f"长按 ({x}, {y}) {duration}ms"}

    def _action_input_text(self, target: Optional[str], text: str) -> Dict[str, Any]:
        """输入文字"""
        self._log(f"  [input_text] 开始，目标={target}, 文字={text[:20]}...")

        # 如果指定了目标，先点击激活
        if target:
            self._log(f"  [input_text] 步骤1: 点击输入框")
            tap_result = self._action_tap(target)
            if not tap_result["success"]:
                return tap_result
            time.sleep(0.5)  # 等待输入框获得焦点

        # 先清空输入框（全选+删除）
        self._log(f"  [input_text] 步骤2: 清空输入框")
        self.runner.adb.clear_text_field()
        time.sleep(0.5)  # 等待清空完成

        # 输入文字（使用支持中文的方法）
        self._log(f"  [input_text] 步骤3: 输入文字")
        success = self.runner.adb.input_text_chinese(text)
        if success:
            self._log(f"  [input_text] 完成")
            return {"success": True, "message": f"输入文字: {text[:20]}..."}
        else:
            self._log(f"  [input_text] 失败")
            return {"success": False, "message": f"输入文字失败: {text[:20]}..."}

    def _action_swipe(self, direction: str) -> Dict[str, Any]:
        """滑动操作"""
        self.runner.adb.swipe_direction(direction)
        return {"success": True, "message": f"滑动: {direction}"}

    def _action_find_or_search(self, target: str, search_fallback: bool) -> Dict[str, Any]:
        """查找目标，找不到则搜索"""
        screenshot = self.runner._capture_screenshot()

        # 1. 先尝试直接在当前界面找
        coords = self._locate_target(target, screenshot)
        if coords:
            return {"success": True, "message": f"直接找到: {target}", "data": coords}

        if not search_fallback:
            return {"success": False, "message": f"未找到: {target}"}

        # 2. 使用搜索功能
        self._log(f"    直接查找失败，尝试搜索: {target}")

        # 点击搜索按钮
        search_result = self._action_tap("wechat_search_button")
        if not search_result["success"]:
            return {"success": False, "message": "无法打开搜索"}

        time.sleep(0.5)

        # 输入搜索关键词（使用支持中文的方法）
        self.runner.adb.input_text_chinese(target)
        time.sleep(1)

        # 在搜索结果中查找
        screenshot = self.runner._capture_screenshot()
        coords = self._locate_target(f"dynamic:搜索结果中的{target}", screenshot)
        if coords:
            return {"success": True, "message": f"搜索找到: {target}", "data": coords}

        return {"success": False, "message": f"搜索未找到: {target}"}

    def _locate_target(
        self,
        target: str,
        screenshot: Image.Image
    ) -> Optional[Tuple[int, int]]:
        """
        定位目标

        Args:
            target: 目标名称（参考图名称或 dynamic:描述）
            screenshot: 屏幕截图

        Returns:
            (x, y) 坐标或 None

        Note:
            当 self._local_only=True 时，使用 OPENCV_ONLY 策略，不回退 AI
        """
        # 动态描述 - 需要 AI（VisionAgent）
        if target.startswith("dynamic:"):
            if self._local_only:
                self._log(f"  [local_only] 跳过动态目标: {target}")
                return None
            description = target[8:]
            return self.runner.locator.find_element(screenshot, description)

        # 参考图 - 根据 local_only 选择策略
        # 获取所有变体路径（主图 + _v1, _v2, ...）
        ref_paths = self.handler.get_image_variants(target)
        if ref_paths:
            screenshot_bytes = self._image_to_bytes(screenshot)
            # local_only 模式使用 OPENCV_ONLY，否则使用 OPENCV_FIRST（带AI回退）
            strategy = LocateStrategy.OPENCV_ONLY if self._local_only else LocateStrategy.OPENCV_FIRST

            # 尝试所有变体
            for ref_path in ref_paths:
                result = self.runner.hybrid_locator.locate(
                    screenshot_bytes,
                    ref_path,
                    strategy
                )
                if result.success:
                    self._log(f"  匹配成功: {ref_path.name}")
                    return (result.center_x, result.center_y)

            # 所有变体都失败
            if self._local_only:
                self._log(f"  [local_only] OpenCV匹配失败（已尝试 {len(ref_paths)} 个变体）: {target}")
                return None

        # 非 local_only 模式才回退到 AI（VisionAgent）
        if not self._local_only:
            return self.runner.locator.find_element(screenshot, target)

        return None

    def _get_contact_english_name(self, contact: str) -> Optional[str]:
        """
        从别名系统获取联系人的英文标识

        例如: 张华 -> contacts/wechat_contacts_zhanghua -> zhanghua

        Args:
            contact: 联系人中文名

        Returns:
            英文标识，如 "zhanghua"，未找到则返回 None
        """
        # 通过别名获取参考图路径
        ref_path = self.handler.get_image_path(contact)
        if not ref_path:
            return None

        # 从路径中提取英文名
        # 例如: contacts/wechat_contacts_zhanghua.png -> zhanghua
        filename = ref_path.stem  # wechat_contacts_zhanghua
        prefix = "wechat_contacts_"
        if filename.startswith(prefix):
            return filename[len(prefix):]  # zhanghua

        return None

    def _check_smart_skip(
        self,
        workflow: Workflow,
        params: Dict[str, Any]
    ) -> int:
        """
        智能检测是否可以跳过前置步骤

        检测逻辑：
        - send_message_local: 如果已在与该联系人的聊天界面，跳过点击联系人步骤
        - post_moments_only_text_local: 如果已在朋友圈页面，跳过导航步骤

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

        # 获取裁剪后的截图
        screenshot, top_offset = self.runner._capture_screenshot_cropped()
        screenshot_bytes = self._image_to_bytes(screenshot)

        # 根据工作流类型进行检测
        if workflow.name == "send_message_local":
            # 检测是否已在与指定联系人的聊天界面
            contact = params.get("contact", "")
            if contact:
                # 通过别名系统获取联系人的英文标识
                # 例如: 张华 -> contacts/wechat_contacts_zhanghua -> 提取 zhanghua
                contact_english = self._get_contact_english_name(contact)
                if contact_english:
                    chat_ref_name = f"wechat_chatting_with_{contact_english}"
                else:
                    # 如果没有找到别名，直接用原名尝试
                    chat_ref_name = f"wechat_chatting_with_{contact}"

                chat_ref_paths = self.handler.get_image_variants(chat_ref_name)

                if chat_ref_paths:
                    self._log(f"  [智能跳过] 检测是否在 {contact} 的聊天界面 (参考图: {chat_ref_name})...")
                    for ref_path in chat_ref_paths:
                        result = self.runner.hybrid_locator.locate(
                            screenshot_bytes,
                            ref_path,
                            LocateStrategy.OPENCV_ONLY
                        )
                        if result.success:
                            self._log(f"  [智能跳过] ✓ 已在 {contact} 的聊天界面 (匹配: {ref_path.name})")
                            return 1  # 跳过第一步（点击联系人）
                    self._log(f"  [智能跳过] 未检测到 {contact} 的聊天界面")
                else:
                    self._log(f"  [智能跳过] 没有 {chat_ref_name} 参考图，跳过检测")

        elif workflow.name == "post_moments_only_text_local":
            # 检测是否已在朋友圈页面（通过相机图标判定）
            camera_ref_paths = self.handler.get_image_variants("wechat_moments_camera")

            if camera_ref_paths:
                self._log(f"  [智能跳过] 检测是否在朋友圈页面...")
                for ref_path in camera_ref_paths:
                    result = self.runner.hybrid_locator.locate(
                        screenshot_bytes,
                        ref_path,
                        LocateStrategy.OPENCV_ONLY
                    )
                    if result.success:
                        self._log(f"  [智能跳过] ✓ 已在朋友圈页面 (匹配: {ref_path.name})")
                        return 2  # 跳过前两步（点击发现Tab + 点击朋友圈入口）
                self._log(f"  [智能跳过] 未检测到朋友圈页面")
            else:
                self._log(f"  [智能跳过] 没有 wechat_moments_camera 参考图，跳过检测")

        return 0

    def _try_recover(self, failed_step: NavStep, params: Dict[str, Any]) -> bool:
        """
        尝试从失败中恢复

        策略：
        1. 按返回键
        2. 检查界面
        3. 尝试导航回正确的界面
        """
        self._log("  尝试恢复...")

        # 先按返回键
        self.runner.adb.press_back()
        time.sleep(0.5)

        # 检查当前界面
        current = self.detect_screen()
        self._log(f"  恢复后界面: {current.value}")

        # 如果在首页，可以重新尝试
        if current == WeChatScreen.HOME:
            return True

        # 尝试导航回首页
        return self.navigate_to_home(max_attempts=config.WORKFLOW_RECOVER_NAV_ATTEMPTS)

    def _render_template(self, template: Optional[str], params: Dict[str, Any]) -> Optional[str]:
        """渲染模板字符串，替换 {param} 占位符"""
        if template is None:
            return None

        result = template
        for key, value in params.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result


def parse_task_params(task: str, param_hints: Dict[str, str]) -> Dict[str, Any]:
    """
    从任务描述中解析参数

    Args:
        task: 任务描述，如 "给张三发消息说你好"
        param_hints: 参数提示

    Returns:
        解析出的参数
    """
    params = {}

    # 解析联系人名称
    if "contact" in param_hints:
        # 尝试多种格式：
        # 1. "给XXX：" (冒号分隔)
        # 2. "给XXX发/说" (传统格式)
        match = re.search(r'给\s*([^\s:：，。\d]+?)(?:[：:]|发|说|$)', task)
        if match:
            params["contact"] = match.group(1)

    # 解析消息内容
    if "message" in param_hints:
        # 1. 先尝试冒号后的内容
        match = re.search(r'[:：]\s*(.+)', task)
        if match:
            params["message"] = match.group(1).strip()
        else:
            # 2. 尝试引号内容
            match = re.search(r'[""「」\'](.*?)[""」」\']', task)
            if match:
                params["message"] = match.group(1)
            else:
                # 3. 尝试 "说XXX"
                match = re.search(r'说\s*([^，。]+?)(?:$|，|。|然后|截图|发朋友圈)', task)
                if match:
                    params["message"] = match.group(1).strip()
                elif "moments_content" in param_hints:
                    # 如果没有明确的消息内容，且是复合任务，使用默认消息
                    params["message"] = "你好"

    # 解析朋友圈内容
    if "content" in param_hints or "moments_content" in param_hints:
        key = "content" if "content" in param_hints else "moments_content"
        # 引号内容（第二个引号内容，第一个可能是消息）
        quotes = re.findall(r'[""「」\'](.*?)[""」」\']', task)
        if len(quotes) >= 2:
            params[key] = quotes[1]  # 第二个引号是朋友圈内容
        elif len(quotes) == 1 and "message" not in params:
            params[key] = quotes[0]
        else:
            # "发朋友圈XXX"
            match = re.search(r'发朋友圈\s*(.+)', task)
            if match:
                params[key] = match.group(1).strip()
            elif key == "moments_content":
                # 复合任务默认使用消息内容作为朋友圈配文
                if "message" in params:
                    params[key] = f"分享一下：{params['message']}"

    # 解析搜索关键词
    if "keyword" in param_hints:
        match = re.search(r'搜索\s*(.+)', task)
        if match:
            params["keyword"] = match.group(1).strip()

    # 解析微信号
    if "wechat_id" in param_hints:
        match = re.search(r'(?:加|添加)[^\d]*(\d+|[a-zA-Z][\w-]+)', task)
        if match:
            params["wechat_id"] = match.group(1)

    return params
