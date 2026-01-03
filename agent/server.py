"""
agent/server.py
手机端 Agent 服务 - 在手机上运行，本地执行所有操作

在 Termux 中运行:
    python agent/server.py --port 8765

特点:
- 截图在本地完成（毫秒级）
- LLM 调用从手机直接发起
- 只通过网络传输小量 JSON 消息
"""
import asyncio
import json
import time
import argparse
import base64
import io
from typing import Optional, Dict, Any, List
from pathlib import Path
import sys

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from aiohttp import web
import config
from core.adb_controller import ADBController
from core.screen_capture import ScreenCapture
from ai.vision_agent import VisionAgent, ActionType, Action, compare_screenshots, detect_loop


class PhoneAgent:
    """
    手机端 Agent - 本地执行截图、LLM分析、操作
    """

    def __init__(self, llm_provider: str = "custom"):
        # 本地 ADB（连接自己）
        self.adb = ADBController("localhost:5555")
        self.screen = ScreenCapture(self.adb)
        self.vision = VisionAgent(provider=llm_provider)
        # 设置 VisionAgent 的日志回调
        self.vision.set_logger(self._log)

        self._current_task: Optional[Dict] = None
        self._task_status = "idle"
        self._task_log: list = []

    def _log(self, message: str):
        """记录日志"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        self._task_log.append(log_entry)
        # 保留最近 100 条日志
        if len(self._task_log) > 100:
            self._task_log = self._task_log[-100:]

    async def execute_task(self, task_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行任务

        Args:
            task_type: 任务类型 (wechat_call, video_call, custom)
            params: 任务参数

        Returns:
            任务结果
        """
        self._task_status = "running"
        self._current_task = {"type": task_type, "params": params}
        self._task_log = []

        self._log(f"收到任务: type={task_type}, params={params}")

        try:
            if task_type == "wechat_call":
                result = await self._run_wechat_call(params)
            elif task_type == "video_call":
                result = await self._run_video_call(params)
            elif task_type == "custom":
                result = await self._run_custom_task(params)
            else:
                result = {"success": False, "error": f"未知任务类型: {task_type}"}

            self._task_status = "completed"
            return result

        except Exception as e:
            import traceback
            self._log(f"任务异常: {e}")
            self._log(traceback.format_exc())
            self._task_status = "failed"
            return {"success": False, "error": str(e), "logs": self._task_log}

    async def _run_wechat_call(self, params: Dict) -> Dict:
        """执行微信视频通话任务"""
        contact_name = params.get("contact_name")
        if not contact_name:
            return {"success": False, "error": "缺少 contact_name 参数"}

        self._log(f"开始微信视频通话任务: {contact_name}")

        # Step 1: 唤醒屏幕
        self._log("唤醒屏幕...")
        self.adb.wake_up()
        await asyncio.sleep(0.5)

        # Step 2: 解锁（如果需要）
        self._log("检查屏幕状态...")
        img = self.screen.capture()
        matched, state = self.vision.check_screen_state(
            img, ["主屏幕/桌面", "锁屏界面", "微信主界面"]
        )
        self._log(f"屏幕状态: {state}")

        if "锁屏" in state:
            self._log("上滑解锁...")
            width, height = self.adb.get_screen_size()
            self.adb.swipe(width // 2, height * 3 // 4, width // 2, height // 4, 300)
            await asyncio.sleep(0.5)

        # Step 3: 打开微信
        self._log("打开微信...")
        self.adb.press_home()
        await asyncio.sleep(0.3)
        self.adb.start_app("com.tencent.mm", "com.tencent.mm.ui.LauncherUI")
        await asyncio.sleep(2)

        # Step 4: 搜索联系人
        self._log(f"搜索联系人: {contact_name}")
        img = self.screen.capture()
        pos = self.vision.find_element(img, "搜索图标 或 放大镜图标")
        if pos:
            self.adb.tap(pos[0], pos[1])
        else:
            width, _ = self.adb.get_screen_size()
            self.adb.tap(width // 2, 150)
        await asyncio.sleep(0.5)

        self.adb.input_text(contact_name)
        await asyncio.sleep(1)

        # Step 5: 点击联系人
        self._log("点击联系人进入聊天...")
        img = self.screen.capture()
        action = self.vision.analyze_screen(
            img,
            f"在搜索结果中找到联系人'{contact_name}'并点击",
            context="微信搜索结果页面"
        )
        if action.action_type == ActionType.TAP and action.x and action.y:
            self.adb.tap(action.x, action.y)
        else:
            width, _ = self.adb.get_screen_size()
            self.adb.tap(width // 2, 300)
        await asyncio.sleep(1)

        # Step 6: 发起视频通话
        self._log("发起视频通话...")
        img = self.screen.capture()
        pos = self.vision.find_element(img, "视频通话图标 或 摄像头图标")
        if pos:
            self.adb.tap(pos[0], pos[1])
            await asyncio.sleep(1)
            self._log("视频通话已发起")
            return {"success": True, "message": "视频通话已发起", "logs": self._task_log}

        # 尝试点击 + 号
        pos = self.vision.find_element(img, "加号按钮 或 + 图标")
        if pos:
            self.adb.tap(pos[0], pos[1])
            await asyncio.sleep(0.5)

            img = self.screen.capture()
            pos = self.vision.find_element(img, "视频通话 选项")
            if pos:
                self.adb.tap(pos[0], pos[1])
                self._log("视频通话已发起")
                return {"success": True, "message": "视频通话已发起", "logs": self._task_log}

        return {"success": False, "error": "未能发起视频通话", "logs": self._task_log}

    async def _run_video_call(self, params: Dict) -> Dict:
        """执行普通视频电话任务"""
        phone_number = params.get("phone_number")
        if not phone_number:
            return {"success": False, "error": "缺少 phone_number 参数"}

        self._log(f"开始视频电话任务: {phone_number}")

        # Step 1: 唤醒并解锁
        self.adb.wake_up()
        await asyncio.sleep(0.5)

        # Step 2: 拨号
        self._log(f"拨打号码: {phone_number}")
        self.adb.dial(phone_number)
        await asyncio.sleep(1.5)

        # Step 3: 查找视频通话按钮
        self._log("查找视频通话按钮...")
        img = self.screen.capture()
        pos = self.vision.find_element(img, "视频通话按钮 或 Video call")
        if pos:
            self.adb.tap(pos[0], pos[1])
            self._log("视频电话已拨出")
            return {"success": True, "message": "视频电话已拨出", "logs": self._task_log}

        # 尝试找普通拨号按钮
        pos = self.vision.find_element(img, "绿色拨号按钮")
        if pos:
            self.adb.tap(pos[0], pos[1])
            self._log("语音电话已拨出（未找到视频通话按钮）")
            return {"success": True, "message": "语音电话已拨出", "logs": self._task_log}

        return {"success": False, "error": "未能拨打电话", "logs": self._task_log}

    def _try_shortcut(self, task: str) -> Optional[Dict]:
        """
        尝试快捷命令，简单任务不走 LLM

        注意：只有纯粹的单一命令才走快捷方式
        复合任务（包含逗号、"然后"、"并"等）交给 LLM 处理

        Returns:
            执行结果，如果不匹配快捷命令则返回 None
        """
        task_lower = task.lower().strip()

        # 复合任务不走快捷命令，交给 LLM 处理
        if any(sep in task_lower for sep in ["，", ",", "然后", "接着", "再", "并且", "同时"]):
            self._log(f"检测到复合任务，跳过快捷命令")
            return None

        # 任务太长也不走快捷命令（可能是复杂描述）
        if len(task) > 20:
            return None

        # 返回桌面/主页
        if any(kw in task_lower for kw in ["返回桌面", "回到桌面", "回桌面", "主屏幕", "home", "回到主页"]):
            self._log("快捷命令: 按 HOME 键")
            self.adb.press_home()
            return {"success": True, "message": "已返回桌面", "shortcut": True}

        # 返回上一级
        if any(kw in task_lower for kw in ["返回", "后退", "back", "上一页", "返回上一级"]):
            self._log("快捷命令: 按返回键")
            self.adb.press_back()
            return {"success": True, "message": "已返回上一级", "shortcut": True}

        # 截图
        if any(kw in task_lower for kw in ["截图", "screenshot", "截屏"]):
            self._log("快捷命令: 截图")
            self.screen.capture()
            return {"success": True, "message": "截图完成", "shortcut": True}

        # 音量加
        if any(kw in task_lower for kw in ["音量加", "声音大", "volume up", "调大音量"]):
            self._log("快捷命令: 音量+")
            self.adb.input_keyevent(24)
            return {"success": True, "message": "音量已增加", "shortcut": True}

        # 音量减
        if any(kw in task_lower for kw in ["音量减", "声音小", "volume down", "调小音量"]):
            self._log("快捷命令: 音量-")
            self.adb.input_keyevent(25)
            return {"success": True, "message": "音量已减小", "shortcut": True}

        # 注意: "打开应用"类任务不走快捷命令，交给 LLM 智能规划
        # 这样 LLM 会先判断当前界面、回到桌面、滑动查找应用图标、然后点击打开
        # 比直接 adb.start_app() 更智能

        return None

    async def _run_custom_task(self, params: Dict) -> Dict:
        """执行自定义任务（基于 LLM 的通用任务）"""
        task_description = params.get("task")
        if not task_description:
            return {"success": False, "error": "缺少 task 参数"}

        self._log(f"===== 开始自定义任务 =====")
        self._log(f"任务描述: {task_description}")
        self._log(f"VisionAgent 配置: use_grid={self.vision.use_grid}, grid_major={self.vision.grid_major}")

        max_steps = params.get("max_steps", 10)
        debug_mode = params.get("debug", False)
        debug_screenshots: List[str] = []  # 存储 debug 截图 (base64)

        # 历史操作记录（用于避免循环）
        action_history: List[Action] = []
        # 上一次的截图（用于检测操作是否生效）
        prev_screenshot = None
        # 连续无效操作计数
        ineffective_count = 0

        if debug_mode:
            self._log(f"[DEBUG] Debug 模式已开启，将返回每步的截图")

        for step in range(max_steps):
            self._log(f"")
            self._log(f"========== Step {step + 1}/{max_steps} ==========")

            # 1. 截图
            self._log("[1] 正在截图...")
            img = self.screen.capture()
            self._log(f"    截图完成: 原始尺寸 {img.size[0]}x{img.size[1]}")

            # 1.1 检测操作是否生效（与上一次截图对比）
            if prev_screenshot is not None:
                has_changed, diff_ratio = compare_screenshots(prev_screenshot, img)
                self._log(f"    屏幕变化: {'是' if has_changed else '否'} (差异: {diff_ratio*100:.1f}%)")
                if not has_changed:
                    ineffective_count += 1
                    self._log(f"    警告: 连续 {ineffective_count} 次操作未生效")
                else:
                    ineffective_count = 0  # 重置计数

            # Debug 模式: 保存截图
            if debug_mode:
                img_debug = img.copy()
                if img_debug.mode == 'RGBA':
                    img_debug = img_debug.convert('RGB')
                buffer = io.BytesIO()
                img_debug.save(buffer, format="JPEG", quality=85)
                debug_screenshots.append({
                    "step": step + 1,
                    "phase": "before_action",
                    "image": base64.b64encode(buffer.getvalue()).decode()
                })

            # 2. 检测循环（连续3次相同操作）
            if detect_loop(action_history, loop_count=3):
                self._log(f"[警告] 检测到循环! 连续3次相同操作，任务失败")
                result = {
                    "success": False,
                    "error": "检测到操作循环，AI 陷入死循环",
                    "steps": step + 1,
                    "logs": self._task_log
                }
                if debug_mode:
                    result["debug_screenshots"] = debug_screenshots
                return result

            # 3. 调用 LLM 分析（传入历史记录）
            self._log(f"[2] 调用 LLM 分析...")
            self._log(f"    任务: {task_description}")
            if action_history:
                self._log(f"    历史操作数: {len(action_history)}")

            # 如果连续多次无效，添加提示
            context = None
            if ineffective_count >= 2:
                context = f"注意：之前{ineffective_count}次操作都没有使屏幕发生变化，请尝试不同的位置或方法"

            action = self.vision.analyze_screen(
                img,
                task_description,
                context=context,
                history=action_history if action_history else None
            )

            # 4. 打印 LLM 返回结果
            self._log(f"[3] LLM 返回结果:")
            self._log(f"    action_type: {action.action_type.value}")
            self._log(f"    坐标: x={action.x}, y={action.y}, x2={action.x2}, y2={action.y2}")
            self._log(f"    text: {action.text}")
            self._log(f"    reason: {action.reason}")

            # 记录历史
            action_history.append(action)

            if action.action_type == ActionType.SUCCESS:
                self._log(f"[结果] 任务成功!")
                result = {"success": True, "message": action.reason, "steps": step + 1, "logs": self._task_log}
                if debug_mode:
                    result["debug_screenshots"] = debug_screenshots
                return result

            if action.action_type == ActionType.FAILED:
                self._log(f"[结果] 任务失败: {action.reason}")
                result = {"success": False, "error": action.reason, "steps": step + 1, "logs": self._task_log}
                if debug_mode:
                    result["debug_screenshots"] = debug_screenshots
                return result

            # 5. 执行操作
            self._log(f"[4] 执行操作:")
            if action.action_type == ActionType.TAP and action.x and action.y:
                x, y = int(action.x), int(action.y)
                self._log(f"    >>> TAP ({x}, {y})")
                self.adb.tap(x, y)
            elif action.action_type == ActionType.LONG_PRESS and action.x and action.y:
                x, y = int(action.x), int(action.y)
                duration = action.duration or 1000
                self._log(f"    >>> LONG_PRESS ({x}, {y}) {duration}ms")
                self.adb.long_press(x, y, duration)
            elif action.action_type == ActionType.SWIPE and action.x and action.y and action.x2 and action.y2:
                x, y, x2, y2 = int(action.x), int(action.y), int(action.x2), int(action.y2)
                self._log(f"    >>> SWIPE ({x}, {y}) -> ({x2}, {y2})")
                self.adb.swipe(x, y, x2, y2)
            elif action.action_type == ActionType.INPUT_TEXT and action.text:
                self._log(f"    >>> INPUT_TEXT: {action.text}")
                self.adb.input_text(action.text)
            elif action.action_type == ActionType.PRESS_KEY and action.keycode:
                self._log(f"    >>> PRESS_KEY: {action.keycode}")
                self.adb.input_keyevent(int(action.keycode))
            elif action.action_type == ActionType.WAIT:
                wait_time = (action.duration or 1000) / 1000
                self._log(f"    >>> WAIT {wait_time}s")
                await asyncio.sleep(wait_time)
            elif action.action_type == ActionType.NONE:
                self._log(f"    >>> NONE (仅输出坐标: x={action.x}, y={action.y})")
                # 不执行任何操作，直接返回成功
                result = {"success": True, "message": action.reason, "x": action.x, "y": action.y, "steps": step + 1, "logs": self._task_log}
                if debug_mode:
                    result["debug_screenshots"] = debug_screenshots
                return result
            else:
                self._log(f"    >>> 未知操作: {action.action_type.value}")

            # 保存当前截图用于下次对比
            prev_screenshot = img

            self._log(f"[5] 等待 0.5s 后继续...")
            await asyncio.sleep(0.5)

        self._log(f"[结果] 达到最大步数限制 ({max_steps})")
        result = {"success": False, "error": "达到最大步数限制", "steps": max_steps, "logs": self._task_log}
        if debug_mode:
            result["debug_screenshots"] = debug_screenshots
        return result

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "status": self._task_status,
            "task": self._current_task,
            "logs": self._task_log[-20:],  # 最近 20 条日志
        }

    def capture_screen_base64(self) -> str:
        """截图并返回 base64（用于远程预览）"""
        import base64
        import io

        img = self.screen.capture()
        # 压缩用于预览
        img.thumbnail((400, 800))
        # RGBA 转 RGB（JPEG 不支持 RGBA）
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=50)
        return base64.b64encode(buffer.getvalue()).decode()

    def capture_screen_with_grid(self, save_path: str = None) -> str:
        """截图并返回 base64，可选保存到本地（网格功能已移除，保留接口兼容）"""
        import base64
        import io

        img = self.screen.capture()
        original_size = img.size

        # 保存到本地（可选）
        if save_path:
            img.save(save_path)
            self._log(f"截图已保存: {save_path} ({original_size[0]}x{original_size[1]})")

        # 返回 base64（不压缩，保持原始尺寸）
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode()


# HTTP API 服务
agent: Optional[PhoneAgent] = None


async def handle_task(request: web.Request) -> web.Response:
    """处理任务请求（普通模式，等待完成后返回）"""
    try:
        data = await request.json()
        task_type = data.get("type", "custom")
        params = data.get("params", {})

        # 异步执行任务
        result = await agent.execute_task(task_type, params)
        return web.json_response(result)

    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)


async def handle_task_stream(request: web.Request) -> web.StreamResponse:
    """处理任务请求（流式模式，实时返回日志和截图）"""
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)

    try:
        data = await request.json()
        task_type = data.get("type", "custom")
        params = data.get("params", {})

        # 只支持 custom 任务的流式模式
        if task_type != "custom":
            await _send_sse(response, "error", {"message": "流式模式只支持 custom 任务"})
            return response

        task_description = params.get("task")
        if not task_description:
            await _send_sse(response, "error", {"message": "缺少 task 参数"})
            return response

        max_steps = params.get("max_steps", 10)
        debug_mode = params.get("debug", False)

        # 历史操作记录（用于避免循环）
        action_history: List[Action] = []
        # 上一次的截图（用于检测操作是否生效）
        prev_screenshot = None
        # 连续无效操作计数
        ineffective_count = 0

        agent._task_status = "running"
        agent._task_log = []

        await _send_sse(response, "start", {"task": task_description, "debug": debug_mode})
        agent._log(f"===== 开始自定义任务 (流式) =====")
        agent._log(f"任务描述: {task_description}")

        for step in range(max_steps):
            await _send_sse(response, "step", {"step": step + 1, "max_steps": max_steps})
            agent._log(f"========== Step {step + 1}/{max_steps} ==========")

            # 1. 截图
            agent._log("[1] 正在截图...")
            img = agent.screen.capture()
            agent._log(f"    截图完成: {img.size[0]}x{img.size[1]}")

            # 1.1 检测操作是否生效
            if prev_screenshot is not None:
                has_changed, diff_ratio = compare_screenshots(prev_screenshot, img)
                agent._log(f"    屏幕变化: {'是' if has_changed else '否'} (差异: {diff_ratio*100:.1f}%)")
                if not has_changed:
                    ineffective_count += 1
                    agent._log(f"    警告: 连续 {ineffective_count} 次操作未生效")
                else:
                    ineffective_count = 0

            # Debug 模式: 发送截图
            if debug_mode:
                img_debug = img.copy()
                if img_debug.mode == 'RGBA':
                    img_debug = img_debug.convert('RGB')
                buffer = io.BytesIO()
                img_debug.save(buffer, format="JPEG", quality=85)
                screenshot_b64 = base64.b64encode(buffer.getvalue()).decode()
                await _send_sse(response, "screenshot", {
                    "step": step + 1,
                    "image": screenshot_b64
                })

            # 发送当前日志
            await _send_sse(response, "logs", {"logs": agent._task_log[-10:]})

            # 2. 检测循环
            if detect_loop(action_history, loop_count=3):
                agent._log(f"[警告] 检测到循环! 连续3次相同操作，任务失败")
                await _send_sse(response, "done", {
                    "success": False,
                    "error": "检测到操作循环，AI 陷入死循环",
                    "steps": step + 1
                })
                agent._task_status = "failed"
                return response

            # 3. 调用 LLM（传入历史记录）
            agent._log("[2] 调用 LLM 分析...")

            context = None
            if ineffective_count >= 2:
                context = f"注意：之前{ineffective_count}次操作都没有使屏幕发生变化，请尝试不同的位置或方法"

            action = agent.vision.analyze_screen(
                img,
                task_description,
                context=context,
                history=action_history if action_history else None
            )

            # 记录历史
            action_history.append(action)

            agent._log(f"[3] LLM 返回: {action.action_type.value}, reason={action.reason}")
            await _send_sse(response, "action", {
                "action": action.action_type.value,
                "x": action.x,
                "y": action.y,
                "reason": action.reason
            })

            # 发送更新后的日志
            await _send_sse(response, "logs", {"logs": agent._task_log[-10:]})

            if action.action_type == ActionType.SUCCESS:
                await _send_sse(response, "done", {"success": True, "message": action.reason, "steps": step + 1})
                agent._task_status = "completed"
                return response

            if action.action_type == ActionType.FAILED:
                await _send_sse(response, "done", {"success": False, "error": action.reason, "steps": step + 1})
                agent._task_status = "failed"
                return response

            # 4. 执行操作
            agent._log(f"[4] 执行操作...")
            if action.action_type == ActionType.TAP and action.x and action.y:
                x, y = int(action.x), int(action.y)
                agent._log(f"    >>> TAP ({x}, {y})")
                agent.adb.tap(x, y)
            elif action.action_type == ActionType.LONG_PRESS and action.x and action.y:
                x, y = int(action.x), int(action.y)
                duration = action.duration or 1000
                agent._log(f"    >>> LONG_PRESS ({x}, {y}) {duration}ms")
                agent.adb.long_press(x, y, duration)
            elif action.action_type == ActionType.SWIPE and action.x and action.y and action.x2 and action.y2:
                x, y, x2, y2 = int(action.x), int(action.y), int(action.x2), int(action.y2)
                agent._log(f"    >>> SWIPE ({x}, {y}) -> ({x2}, {y2})")
                agent.adb.swipe(x, y, x2, y2)
            elif action.action_type == ActionType.INPUT_TEXT and action.text:
                agent._log(f"    >>> INPUT_TEXT: {action.text}")
                agent.adb.input_text(action.text)
            elif action.action_type == ActionType.PRESS_KEY and action.keycode:
                agent._log(f"    >>> PRESS_KEY: {action.keycode}")
                agent.adb.input_keyevent(int(action.keycode))
            elif action.action_type == ActionType.WAIT:
                wait_time = (action.duration or 1000) / 1000
                agent._log(f"    >>> WAIT {wait_time}s")
                await asyncio.sleep(wait_time)
            elif action.action_type == ActionType.NONE:
                agent._log(f"    >>> NONE (仅输出坐标: x={action.x}, y={action.y})")
                await _send_sse(response, "done", {"success": True, "message": action.reason, "x": action.x, "y": action.y, "steps": step + 1})
                agent._task_status = "completed"
                return response

            # 保存当前截图用于下次对比
            prev_screenshot = img

            await _send_sse(response, "logs", {"logs": agent._task_log[-5:]})
            await asyncio.sleep(0.5)

        await _send_sse(response, "done", {"success": False, "error": "达到最大步数限制", "steps": max_steps})
        agent._task_status = "completed"

    except Exception as e:
        import traceback
        await _send_sse(response, "error", {"message": str(e), "traceback": traceback.format_exc()})
        agent._task_status = "failed"

    return response


async def _send_sse(response: web.StreamResponse, event: str, data: dict):
    """发送 SSE 事件"""
    msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    await response.write(msg.encode('utf-8'))


async def handle_status(request: web.Request) -> web.Response:
    """获取状态"""
    return web.json_response(agent.get_status())


async def handle_screen(request: web.Request) -> web.Response:
    """获取屏幕截图（base64）"""
    try:
        screen_b64 = agent.capture_screen_base64()
        return web.json_response({"screen": screen_b64})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_screen_grid(request: web.Request) -> web.Response:
    """获取带坐标网格的截图（用于调试）"""
    try:
        # 可选保存到手机本地
        save = request.query.get("save", "0") == "1"
        save_path = "/sdcard/screen_grid.jpg" if save else None

        screen_b64 = agent.capture_screen_with_grid(save_path=save_path)
        return web.json_response({
            "screen": screen_b64,
            "saved": save_path if save else None
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_ping(request: web.Request) -> web.Response:
    """健康检查"""
    return web.json_response({"status": "ok", "time": time.time()})


def create_app() -> web.Application:
    """创建 HTTP 应用"""
    app = web.Application()
    app.router.add_post("/task", handle_task)
    app.router.add_post("/task/stream", handle_task_stream)  # 流式接口
    app.router.add_get("/status", handle_status)
    app.router.add_get("/screen", handle_screen)
    app.router.add_get("/screen_grid", handle_screen_grid)
    app.router.add_get("/ping", handle_ping)
    return app


def main():
    global agent

    parser = argparse.ArgumentParser(description="手机端 Agent 服务")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--llm", default="custom", help="LLM 提供商")
    args = parser.parse_args()

    print(f"初始化 Agent (LLM: {args.llm})...")
    agent = PhoneAgent(llm_provider=args.llm)

    print(f"启动服务: http://{args.host}:{args.port}")
    print("API 端点:")
    print("  POST /task        - 执行任务 (等待完成)")
    print("  POST /task/stream - 执行任务 (流式，实时返回)")
    print("  GET  /status      - 获取状态")
    print("  GET  /screen      - 获取截图")
    print("  GET  /screen_grid - 获取带坐标网格的截图 (?save=1 保存到手机)")
    print("  GET  /ping        - 健康检查")

    app = create_app()
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
