"""apps/chrome/workflow_executor.py
Chrome 工作流执行器 - 执行预定义的工作流

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
    Workflow, NavStep, ChromeScreen,
    SCREEN_DETECT_REFS, SCREEN_DETECT_REFS_FALLBACK,
    NAV_TO_HOME, WORKFLOWS, match_workflow
)


class WorkflowExecutor:
    """Chrome 工作流执行器"""

    # Chrome 包名
    CHROME_PACKAGE = "com.android.chrome"

    def __init__(self, task_runner, handler):
        """
        初始化执行器

        Args:
            task_runner: TaskRunner 实例（用于执行操作）
            handler: ChromeHandler 实例（用于获取参考图）
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
            self._logger(f"[ChromeWorkflow] {message}")
        else:
            print(f"[ChromeWorkflow] {message}")

    def _image_to_bytes(self, image: Image.Image) -> bytes:
        """将 PIL Image 转换为 bytes"""
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()

    def _ensure_chrome_running(self) -> bool:
        """
        确保 Chrome 已打开并在前台，且处于可用状态

        流程：
        1. 检查/启动 Chrome
        2. 确保回到主页或可用界面

        Returns:
            是否成功确保 Chrome 可用
        """
        self._log("")
        self._log("╔════════════════════════════════════════╗")
        self._log("║       【预置流程】正式任务前准备        ║")
        self._log("╚════════════════════════════════════════╝")
        self._log("")
        self._log("[预置] 步骤0: 使用系统指令启动 Chrome")

        # 无条件使用系统指令启动 Chrome
        self._log("  执行启动 Chrome 指令...")
        self.runner.adb.start_app(self.CHROME_PACKAGE)
        time.sleep(config.OPERATION_DELAY * 4)  # 等待 Chrome 启动

        # 验证 Chrome 是否启动成功
        current_app = self.runner.adb.get_current_app()
        self._log(f"  当前前台应用: {current_app}")

        if current_app != self.CHROME_PACKAGE:
            if current_app is None:
                self._log("  无法检测前台应用，通过截图验证...")
                time.sleep(config.OPERATION_DELAY * 2)
                current_screen = self.detect_screen()
                if current_screen == ChromeScreen.UNKNOWN:
                    self._log(f"  ✗ Chrome 启动失败")
                    return False
                else:
                    self._log(f"  ✓ 检测到 Chrome 界面: {current_screen.value}")
            else:
                self._log(f"  ✗ Chrome 启动失败，当前应用: {current_app}")
                return False
        else:
            self._log("  ✓ Chrome 已在前台")

        # 确保在可用界面
        return self._ensure_at_usable_screen()

    def _ensure_at_usable_screen(self, max_attempts: int = None) -> bool:
        """
        确保 Chrome 处于可用界面（主页或网页浏览界面）

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功
        """
        if max_attempts is None:
            max_attempts = config.WORKFLOW_HOME_MAX_ATTEMPTS

        self._log("")
        self._log("[预置] 步骤1: 确保 Chrome 在可用界面")

        for attempt in range(max_attempts):
            self._log(f"  检测第 {attempt + 1}/{max_attempts} 次...")

            # 截图检测当前界面
            screenshot = self.runner._capture_screenshot()
            screenshot_bytes = self._image_to_bytes(screenshot)

            # 检测当前界面
            current_screen = self.detect_screen(screenshot)

            # 如果在可用界面，返回成功
            if current_screen in [ChromeScreen.HOME, ChromeScreen.WEBPAGE, ChromeScreen.SEARCH_RESULTS]:
                self._log(f"  ✓ 已在可用界面: {current_screen.value}")
                self._log("")
                self._log("╔════════════════════════════════════════╗")
                self._log("║     【预置流程完成】开始执行正式任务    ║")
                self._log("╚════════════════════════════════════════╝")
                self._log("")
                return True

            # 尝试返回
            self._log(f"  当前界面: {current_screen.value}，尝试返回...")

            # 优先尝试点击取消/关闭按钮
            close_clicked = self._try_click_close_button(screenshot_bytes)
            if close_clicked:
                self._log(f"  已点击关闭/取消按钮")
                time.sleep(config.OPERATION_DELAY * 2)
                continue

            # 没有关闭按钮，按物理返回键
            self._log(f"  按物理返回键...")
            self.runner.adb.press_back()
            time.sleep(config.OPERATION_DELAY * 2)

        # 最后再检查一次
        current_screen = self.detect_screen()
        if current_screen in [ChromeScreen.HOME, ChromeScreen.WEBPAGE, ChromeScreen.SEARCH_RESULTS]:
            self._log(f"  ✓ 已在可用界面: {current_screen.value}")
            self._log("")
            self._log("╔════════════════════════════════════════╗")
            self._log("║     【预置流程完成】开始执行正式任务    ║")
            self._log("╚════════════════════════════════════════╝")
            self._log("")
            return True

        self._log(f"  ✗ 无法回到可用界面")
        return False

    def _try_click_close_button(self, screenshot_bytes: bytes) -> bool:
        """
        尝试点击关闭/取消按钮

        Returns:
            是否成功点击
        """
        # 尝试的按钮列表
        close_refs = ["chrome_close_button", "chrome_cancel_button"]

        for ref_name in close_refs:
            ref_paths = self.handler.get_image_variants(ref_name)
            if ref_paths:
                for ref_path in ref_paths:
                    try:
                        result = self.runner.hybrid_locator.locate(
                            screenshot_bytes,
                            ref_path,
                            LocateStrategy.OPENCV_ONLY
                        )
                        if result.success:
                            self._log(f"  找到 {ref_name}，点击")
                            self.runner.adb.tap(result.center_x, result.center_y)
                            return True
                    except Exception:
                        pass

        return False

    def detect_screen(self, screenshot: Optional[Image.Image] = None) -> ChromeScreen:
        """
        检测当前界面

        Args:
            screenshot: 屏幕截图，如果为 None 则自动截取

        Returns:
            当前界面类型
        """
        if screenshot is None:
            screenshot = self.runner._capture_screenshot()

        self._log("检测当前 Chrome 界面...")

        # 按优先级检测各界面
        detection_order = [
            ChromeScreen.HOME,
            ChromeScreen.ADDRESS_BAR,
            ChromeScreen.SEARCH_RESULTS,
            ChromeScreen.WEBPAGE,
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
                        self._log(f"  ✓ 检测到界面: {screen.value} (匹配: {ref_name})")
                        return screen
                    else:
                        self._log(f"  尝试 {ref_name}: 未匹配")
                except Exception as e:
                    self._log(f"  检测 {screen.value} 失败: {e}")

        self._log("  ✗ 未识别的界面")
        return ChromeScreen.UNKNOWN

    def navigate_to_home(self, max_attempts: int = None) -> bool:
        """
        导航回 Chrome 主页

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功到达主页
        """
        if max_attempts is None:
            max_attempts = config.WORKFLOW_HOME_MAX_ATTEMPTS

        self._log("=== 导航到 Chrome 主页 ===")

        for attempt in range(max_attempts):
            screenshot = self.runner._capture_screenshot()
            current_screen = self.detect_screen(screenshot)

            if current_screen == ChromeScreen.HOME:
                self._log(f"  ✓ 已到达主页 (尝试 {attempt + 1} 次)")
                return True

            self._log(f"  当前: {current_screen.value}, 尝试 {attempt + 1}/{max_attempts}")

            # 尝试点击主页按钮
            home_clicked = self._try_click_home_button(screenshot)
            if home_clicked:
                self._log(f"  已点击主页按钮")
                time.sleep(self._back_press_interval / 1000)
                continue

            # 没有主页按钮，按返回键
            self._log(f"  未找到主页按钮，按返回键...")
            self.runner.adb.press_back()
            time.sleep(self._back_press_interval / 1000)

        # 最后检查
        current_screen = self.detect_screen()
        if current_screen == ChromeScreen.HOME:
            self._log(f"  ✓ 已到达主页")
            return True

        self._log(f"  ✗ 未能到达主页，当前: {current_screen.value}")
        return False

    def _try_click_home_button(self, screenshot: Image.Image) -> bool:
        """
        尝试点击主页按钮
        """
        screenshot_bytes = self._image_to_bytes(screenshot)
        ref_paths = self.handler.get_image_variants("chrome_home_button")

        if ref_paths:
            for ref_path in ref_paths:
                try:
                    result = self.runner.hybrid_locator.locate(
                        screenshot_bytes,
                        ref_path,
                        LocateStrategy.OPENCV_FIRST
                    )
                    if result.success:
                        self._log(f"  找到主页按钮，点击 ({result.center_x}, {result.center_y})")
                        self.runner.adb.tap(result.center_x, result.center_y)
                        return True
                except Exception:
                    pass

        return False

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

        try:
            # 执行预置流程：确保 Chrome 在前台且可用
            preset_success = self._ensure_chrome_running()
            if not preset_success:
                self._log("  ⚠ 预置流程失败，但仍尝试继续执行正式任务...")

            # 检测当前界面
            current_screen = self.detect_screen()
            self._log(f"  当前界面: {current_screen.value}")
            self._log(f"  有效起点: {[s.value for s in workflow.valid_start_screens]}")

            # 确保在有效起始界面
            if current_screen not in workflow.valid_start_screens and current_screen != ChromeScreen.UNKNOWN:
                self._log(f"  不在有效起始界面，尝试导航...")
                if not self.navigate_to_home():
                    return {
                        "success": False,
                        "message": "无法导航到有效起始界面",
                        "data": None
                    }

            # 执行工作流步骤
            for i, step in enumerate(workflow.steps):
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

                    # 最后一次重试不需要等待
                    if retry < self._max_step_retries - 1:
                        if self._local_only:
                            wait_time = config.OPERATION_DELAY * 2
                            self._log(f"  [local_only] 等待 {wait_time}ms 后重试...")
                            time.sleep(wait_time / 1000)
                        else:
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
                if step.expect_screen and not self._local_only:
                    time.sleep(0.3)
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
            self._local_only = False

            # 任务完成后复位
            if config.WORKFLOW_RESET_AFTER_TASK:
                self._log("")
                self._log("╔════════════════════════════════════════╗")
                self._log("║       【复位流程】任务完成后复位        ║")
                self._log("╚════════════════════════════════════════╝")
                self._log("")
                try:
                    reset_success = self._ensure_at_usable_screen()
                    if reset_success:
                        self._log("✓ 复位成功")
                    else:
                        self._log("⚠️  复位失败，但不影响任务结果")
                except Exception as e:
                    self._log(f"⚠️  复位过程出现异常: {e}")

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

            elif action == "input_url":
                url = step_params.get("url", "")
                return self._action_input_url(url)

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
                return {"success": success, "message": "导航到主页" if success else "导航失败"}

            else:
                return {"success": False, "message": f"未知动作: {action}"}

        except Exception as e:
            return {"success": False, "message": str(e)}

    def _action_tap(self, target: str) -> Dict[str, Any]:
        """点击操作"""
        screenshot = self.runner._capture_screenshot()
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
        self._log(f"  [input_text] 开始，目标={target}, 文字={text[:30]}...")

        # 如果指定了目标，先点击激活
        if target:
            tap_result = self._action_tap(target)
            if not tap_result["success"]:
                return tap_result
            time.sleep(0.5)

        # 清空输入框
        self.runner.adb.clear_text_field()
        time.sleep(0.3)

        # 输入文字
        success = self.runner.adb.input_text_chinese(text)
        if success:
            return {"success": True, "message": f"输入文字: {text[:30]}..."}
        else:
            return {"success": False, "message": f"输入文字失败"}

    def _action_input_url(self, url: str) -> Dict[str, Any]:
        """
        输入网址（专用于地址栏）

        Args:
            url: 要输入的网址

        Returns:
            执行结果
        """
        self._log(f"  [input_url] 输入网址: {url}")

        # 清空地址栏
        self.runner.adb.clear_text_field()
        time.sleep(0.3)

        # 输入网址（网址通常是ASCII，但也支持中文域名）
        if all(ord(c) < 128 for c in url):
            # 纯 ASCII，使用普通输入
            success = self.runner.adb.input_text(url)
        else:
            # 包含非 ASCII，使用支持中文的方法
            success = self.runner.adb.input_text_chinese(url)

        if success:
            return {"success": True, "message": f"输入网址: {url}"}
        else:
            return {"success": False, "message": f"输入网址失败"}

    def _action_swipe(self, direction: str) -> Dict[str, Any]:
        """滑动操作"""
        self.runner.adb.swipe_direction(direction)
        return {"success": True, "message": f"滑动: {direction}"}

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
        """
        # 动态描述 - 需要 AI
        if target.startswith("dynamic:"):
            if self._local_only:
                self._log(f"  [local_only] 跳过动态目标: {target}")
                return None
            description = target[8:]
            return self.runner.locator.find_element(screenshot, description)

        # 参考图 - 使用 OpenCV
        ref_paths = self.handler.get_image_variants(target)
        if ref_paths:
            screenshot_bytes = self._image_to_bytes(screenshot)
            strategy = LocateStrategy.OPENCV_ONLY if self._local_only else LocateStrategy.OPENCV_FIRST

            for ref_path in ref_paths:
                result = self.runner.hybrid_locator.locate(
                    screenshot_bytes,
                    ref_path,
                    strategy
                )
                if result.success:
                    self._log(f"  匹配成功: {ref_path.name}")
                    return (result.center_x, result.center_y)

            if self._local_only:
                self._log(f"  [local_only] OpenCV匹配失败: {target}")
                return None

        # 非 local_only 模式回退到 AI
        if not self._local_only:
            return self.runner.locator.find_element(screenshot, target)

        return None

    def _try_recover(self, failed_step: NavStep, params: Dict[str, Any]) -> bool:
        """
        尝试从失败中恢复
        """
        self._log("  尝试恢复...")

        # 按返回键
        self.runner.adb.press_back()
        time.sleep(0.5)

        # 检查当前界面
        current = self.detect_screen()
        self._log(f"  恢复后界面: {current.value}")

        # 如果在可用界面，可以重新尝试
        if current in [ChromeScreen.HOME, ChromeScreen.WEBPAGE, ChromeScreen.SEARCH_RESULTS]:
            return True

        # 尝试导航回主页
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
        task: 任务描述
        param_hints: 参数提示

    Returns:
        解析出的参数
    """
    params = {}

    # 解析网址
    if "url" in param_hints:
        # 尝试匹配 URL
        url_match = re.search(r'(https?://\S+|www\.\S+|[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-z]{2,}\S*)', task)
        if url_match:
            url = url_match.group(1)
            # 自动补全 http://
            if not url.startswith('http'):
                url = 'https://' + url
            params["url"] = url

    # 解析搜索词
    if "query" in param_hints:
        # 搜索XXX / 查一下XXX / 百度一下XXX
        match = re.search(r'(?:搜索|查一下|百度一下|谷歌一下|查找|查询)\s*(.+)', task)
        if match:
            params["query"] = match.group(1).strip()

    return params
