"""
ai/vison_agent.py
LLM 视觉代理 - 使用多模态 LLM 分析屏幕并决策操作

支持的 LLM 提供商:
- Claude (Anthropic)
- OpenAI (GPT-4V)
- 自定义 OpenAI 兼容 API (DeepSeek, Moonshot, 智谱, 通义千问, 零一万物, Ollama 等)
"""
import base64
import json
import re
import time
from typing import Optional, Tuple, List, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum
from PIL import Image
import io

import config
from config import LLMConfig


class ActionType(Enum):
    """操作类型"""
    TAP = "tap"
    LONG_PRESS = "long_press"
    SWIPE = "swipe"
    INPUT_TEXT = "input_text"
    PRESS_KEY = "press_key"
    WAIT = "wait"
    NONE = "none"  # 仅输出坐标，不执行操作
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class Action:
    """LLM 返回的操作指令"""
    action_type: ActionType
    x: Optional[int] = None
    y: Optional[int] = None
    x2: Optional[int] = None  # 用于 swipe
    y2: Optional[int] = None
    text: Optional[str] = None
    keycode: Optional[int] = None
    duration: Optional[int] = None
    reason: str = ""


class VisionAgent:
    """
    视觉代理 - 使用多模态 LLM 理解屏幕并生成操作指令

    支持多种 LLM 提供商:
    - claude: Anthropic Claude (推荐)
    - openai: OpenAI GPT-4V
    - custom: 任意 OpenAI 兼容 API

    使用示例:

        # 方式1: 使用提供商名称 (从环境变量读取配置)
        agent = VisionAgent(provider="claude")
        agent = VisionAgent(provider="openai")
        agent = VisionAgent(provider="custom")

        # 方式2: 使用 LLMConfig 对象 (完全自定义)
        from config import LLMConfig

        llm_config = LLMConfig.custom(
            api_key="sk-xxx",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat"
        )
        agent = VisionAgent(llm_config=llm_config)

        # 方式3: 使用预设配置
        from config import get_preset_config

        llm_config = get_preset_config("deepseek", api_key="sk-xxx")
        agent = VisionAgent(llm_config=llm_config)

        # 方式4: 直接传入参数
        agent = VisionAgent(
            api_key="sk-xxx",
            base_url="https://api.example.com/v1",
            model="my-model"
        )
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        # 直接参数 (用于快速自定义)
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """
        初始化视觉代理

        Args:
            provider: LLM 提供商名称 ('claude', 'openai', 'custom')
            llm_config: LLMConfig 配置对象 (优先级最高)
            api_key: API 密钥 (用于快速自定义)
            base_url: API 基础 URL (用于快速自定义)
            model: 模型名称 (用于快速自定义)
        """
        # 日志回调函数
        self._logger = None

        # 优先使用 llm_config
        if llm_config is not None:
            self.config = llm_config
        # 其次使用直接参数
        elif api_key and base_url and model:
            self.config = LLMConfig.custom(
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
        # 最后使用 provider 从环境变量加载
        else:
            provider = provider or config.LLM_PROVIDER
            self.config = LLMConfig.from_env(provider)

        self._client = None

    def set_logger(self, logger_func):
        """设置日志回调函数"""
        self._logger = logger_func

    def _log(self, message: str):
        """记录日志"""
        if self._logger:
            self._logger(f"[Vision] {message}")
        else:
            print(f"[VisionAgent] {message}")

    @property
    def provider(self) -> str:
        """获取当前提供商"""
        return self.config.provider

    def _get_client(self):
        """懒加载 API 客户端"""
        if self._client is None:
            if self.config.provider == "claude":
                import anthropic
                self._client = anthropic.Anthropic(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url if self.config.base_url != "https://api.anthropic.com" else None,
                    timeout=self.config.timeout,
                )
            elif self.config.provider in ("openai", "custom"):
                import openai

                # OpenRouter 需要特定的请求头
                default_headers = {}
                if "openrouter" in self.config.base_url.lower():
                    default_headers = {
                        "HTTP-Referer": "https://github.com/anthropics/claude-code",
                        "X-Title": "Android Remote Controller",
                    }

                self._client = openai.OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    default_headers=default_headers if default_headers else None,
                )
            else:
                raise ValueError(f"不支持的 provider: {self.config.provider}")
        return self._client

    def _image_to_base64(self, image: Image.Image, max_size: int = 1024) -> str:
        """将图片转换为 base64"""
        original_size = image.size
        self._log(f"输入图片 {original_size[0]}x{original_size[1]}")

        # 缩放图片以减小体积
        width, height = image.size
        if width > max_size or height > max_size:
            ratio = min(max_size / width, max_size / height)
            new_size = (int(width * ratio), int(height * ratio))
            self._log(f"缩放图片: {width}x{height} -> {new_size[0]}x{new_size[1]} (ratio={ratio:.3f})")
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        # 使用 JPEG 格式压缩，质量 85%
        if image.mode == 'RGBA':
            image = image.convert('RGB')
        image.save(buffer, format="JPEG", quality=85)
        b64_len = len(buffer.getvalue())
        self._log(f"最终图片: {image.size[0]}x{image.size[1]}, 大小: {b64_len/1024:.1f}KB")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _bbox_to_center(self, bbox: Dict[str, int], width: int, height: int) -> Tuple[int, int]:
        """
        将 bbox {xmin, ymin, xmax, ymax} (0-1000) 转换为中心点像素坐标

        Args:
            bbox: {"xmin": int, "ymin": int, "xmax": int, "ymax": int} 范围 0-1000
            width: 图片宽度（像素）
            height: 图片高度（像素）

        Returns:
            (x, y) 中心点像素坐标
        """
        xmin = bbox.get("xmin", 0)
        ymin = bbox.get("ymin", 0)
        xmax = bbox.get("xmax", 0)
        ymax = bbox.get("ymax", 0)

        # 计算中心点百分比
        x_center = (xmin + xmax) / 2 / 1000
        y_center = (ymin + ymax) / 2 / 1000

        # 转换为像素坐标
        x = int(x_center * width)
        y = int(y_center * height)
        return x, y

    def _parse_action(self, response_text: str, image_size: Optional[Tuple[int, int]] = None) -> Action:
        """
        解析 LLM 返回的操作指令

        Args:
            response_text: LLM 返回的文本
            image_size: 图片尺寸 (width, height)，用于 bbox 坐标转换

        Returns:
            Action 对象
        """
        # 尝试提取 JSON
        json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())

                action_type = ActionType(data.get("action", "wait"))

                x = data.get("x")
                y = data.get("y")
                x2 = data.get("x2")
                y2 = data.get("y2")

                # 如果有 bbox 格式的坐标，转换为像素坐标
                if "xmin" in data and "ymin" in data and image_size:
                    width, height = image_size
                    xmin = data.get("xmin", 0)
                    ymin = data.get("ymin", 0)
                    xmax = data.get("xmax", 0)
                    ymax = data.get("ymax", 0)

                    if action_type == ActionType.SWIPE:
                        # swipe: xmin/ymin 是起点，xmax/ymax 是终点
                        x = int(xmin / 1000 * width)
                        y = int(ymin / 1000 * height)
                        x2 = int(xmax / 1000 * width)
                        y2 = int(ymax / 1000 * height)
                        self._log(f"swipe bbox -> ({x}, {y}) -> ({x2}, {y2})")
                    else:
                        # tap/long_press: 使用 bbox 中心点
                        x, y = self._bbox_to_center(data, width, height)
                        self._log(f"bbox -> 中心坐标 ({x}, {y})")

                return Action(
                    action_type=action_type,
                    x=x,
                    y=y,
                    x2=x2,
                    y2=y2,
                    text=data.get("text"),
                    keycode=data.get("keycode"),
                    duration=data.get("duration"),
                    reason=data.get("reason", "")
                )
            except (json.JSONDecodeError, ValueError) as e:
                self._log(f"JSON 解析错误: {e}")

        # 解析失败，返回等待
        return Action(
            action_type=ActionType.WAIT,
            reason=f"无法解析响应: {response_text[:200]}"
        )

    def analyze_screen(
        self,
        image: Image.Image,
        task: str,
        context: Optional[str] = None,
        history: Optional[List[Action]] = None
    ) -> Action:
        """
        分析屏幕并返回下一步操作

        Args:
            image: 屏幕截图
            task: 当前任务描述
            context: 额外上下文信息
            history: 历史操作记录（用于避免重复操作）

        Returns:
            下一步操作指令
        """
        self._log(f"====== analyze_screen ======")
        self._log(f"任务: {task}")

        # 获取原始分辨率
        width, height = image.size

        system_prompt = f"""You are an Android automation assistant that analyzes screens and plans operation steps.

【Coordinate System】
- Use a scale of 0-1000 for positioning (will be converted to actual pixels)
- Return bounding box format: {{"xmin": int, "ymin": int, "xmax": int, "ymax": int}}

【Decision Rules】
1. Analyze current screen: Identify the app/interface (home screen, in-app, popup, etc.)
2. Compare with task goal: How many steps to reach the target?
3. Choose optimal action:
   - If target is visible → tap on it
   - Need to go home → press_key(keycode=3) for HOME
   - Need to go back → press_key(keycode=4) for BACK
   - Target not visible → swipe to find (left/right for home screen, up/down for lists)
   - Task completed → return success
   - Cannot complete → return failed

【Swipe Directions】 (in 0-1000 scale)
- Swipe left (next page): swipe from xmin=700 to xmax=300, y=500
- Swipe right (prev page): swipe from xmin=300 to xmax=700, y=500
- Scroll down: swipe from ymin=700 to ymax=300, x=500
- Scroll up: swipe from ymin=300 to ymax=700, x=500

【Response Format】
Return strictly valid JSON with one of these actions:
{{"action":"tap","xmin":400,"ymin":550,"xmax":600,"ymax":650,"reason":"click button"}}
{{"action":"long_press","xmin":400,"ymin":550,"xmax":600,"ymax":650,"duration":1000,"reason":"long press"}}
{{"action":"swipe","xmin":700,"ymin":500,"xmax":300,"ymax":500,"reason":"swipe left"}}
{{"action":"input_text","text":"hello","reason":"enter text"}}
{{"action":"press_key","keycode":3,"reason":"press HOME"}}
{{"action":"wait","duration":1000,"reason":"wait for loading"}}
{{"action":"success","reason":"task completed"}}
{{"action":"failed","reason":"cannot complete task"}}

Common keys: 3=HOME, 4=BACK, 66=ENTER, 24=VOL+, 25=VOL-"""

        user_prompt = f"任务:{task}"
        if context:
            user_prompt += f"\n上下文:{context}"

        # 添加历史操作记录（帮助 LLM 避免重复操作）
        if history:
            history_str = "\n".join([
                f"  第{i+1}步: {h.action_type.value}" +
                (f" ({h.x},{h.y})" if h.x and h.y else "") +
                (f" -> ({h.x2},{h.y2})" if h.x2 and h.y2 else "") +
                (f" text={h.text}" if h.text else "") +
                (f" | {h.reason}" if h.reason else "")
                for i, h in enumerate(history[-5:])  # 只保留最近5步
            ])
            user_prompt += f"\n\n已执行的操作:\n{history_str}\n\n注意: 如果之前的操作没有效果，请尝试不同的方法或位置。"

        image_b64 = self._image_to_base64(image)

        self._log(f"调用 LLM: {self.config.provider}/{self.config.model}")
        start_time = time.time()

        if self.config.provider == "claude":
            response = self._call_claude(system_prompt, user_prompt, image_b64)
        else:
            # openai 和 custom 都使用 OpenAI 兼容 API
            response = self._call_openai_compatible(system_prompt + "\n只返回JSON，不要其他内容。", user_prompt, image_b64, json_mode=True)

        elapsed = time.time() - start_time
        self._log(f"LLM 响应耗时: {elapsed:.2f}s")
        self._log(f"LLM 响应: {response[:200]}...")

        action = self._parse_action(response, image_size=(width, height))
        self._log(f"解析结果: {action.action_type.value}, x={action.x}, y={action.y}")
        return action

    def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
        image_b64: str
    ) -> str:
        """调用 Claude API"""
        client = self._get_client()

        # 使用数组格式的 system，兼容官方 API 和第三方代理
        system_content = [{"type": "text", "text": system_prompt}]

        response = client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system_content,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": user_prompt
                        }
                    ]
                }
            ]
        )

        return response.content[0].text

    def _call_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        image_b64: Union[str, List[str]],
        json_mode: bool = False
    ) -> str:
        """
        调用 OpenAI 兼容 API

        支持: OpenAI, DeepSeek, Moonshot, 智谱, 通义千问, 零一万物, Ollama, LMStudio, OpenRouter 等

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            image_b64: 单张图片的 base64 字符串，或多张图片的 base64 列表
            json_mode: 是否强制 JSON 输出
        """
        client = self._get_client()

        # 构建消息内容
        user_content = [
            {
                "type": "text",
                "text": user_prompt
            }
        ]

        # 支持单张或多张图片
        images = [image_b64] if isinstance(image_b64, str) else image_b64
        for img_b64 in images:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high"
                }
            })

        # 构建请求参数
        request_params = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False,
            **self.config.extra_params
        }

        # 强制 JSON 输出
        if json_mode:
            request_params["response_format"] = {"type": "json_object"}

        try:
            response = client.chat.completions.create(**request_params)
            result = response.choices[0].message.content
            return result
        except Exception as e:
            # 打印详细错误信息
            self._log(f"API 请求失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    def check_screen_state(
        self,
        image: Image.Image,
        expected_states: List[str]
    ) -> Tuple[bool, str]:
        """
        检查屏幕是否处于预期状态

        Args:
            image: 屏幕截图
            expected_states: 预期状态描述列表

        Returns:
            (是否匹配, 实际状态描述)
        """
        self._log(f"check_screen_state: {expected_states}")
        states_str = "\n".join(f"- {s}" for s in expected_states)

        prompt = f"""分析这个屏幕截图，判断它是否处于以下任一状态:
{states_str}

严格按以下JSON格式返回，不要返回任何其他内容:
{{"matched": true, "matched_state": "主屏幕/桌面", "actual_state": "手机主屏幕"}}
或
{{"matched": false, "matched_state": "", "actual_state": "锁屏界面"}}
"""

        image_b64 = self._image_to_base64(image)

        if self.config.provider == "claude":
            response = self._call_claude("你是屏幕状态分析助手", prompt, image_b64)
        else:
            response = self._call_openai_compatible("你是屏幕状态分析助手，只返回JSON", prompt, image_b64, json_mode=True)

        try:
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                matched = data.get("matched", False)
                actual_state = data.get("actual_state", "未知")
                self._log(f"check_screen_state 结果: matched={matched}, state={actual_state}")
                return matched, actual_state
        except Exception as e:
            self._log(f"check_screen_state 解析失败: {e}")

        return False, "解析失败"

    def find_element(
        self,
        image: Image.Image,
        element_description: str
    ) -> Optional[Tuple[int, int]]:
        """
        在屏幕中查找指定元素（基于文字描述，动态定位模式）

        Args:
            image: 屏幕截图
            element_description: 元素描述（如 "拨号按钮"、"绿色通话图标"）

        Returns:
            元素中心坐标 (x, y) 或 None
        """
        self._log(f"===== 描述定位 =====")
        self._log(f"  目标描述: '{element_description}'")
        self._log(f"  截图: {image.size[0]}x{image.size[1]}")
        width, height = image.size

        prompt = f"""Task: Find the element matching this description in the Screenshot.

【Target Description】
{element_description}

【Instructions】
1. Locate the UI element that best matches the description
2. Consider:
   - Text content (if the description mentions text)
   - Visual appearance (color, shape, icon type)
   - Position context (e.g., "底部输入框" should be at bottom, "顶部搜索" should be at top)

3. Coordinate System:
   - Use a scale of 0-1000 for both X and Y axes
   - (0,0) is top-left, (1000,1000) is bottom-right

【Output】
Return strictly valid JSON:

If found:
{{"found": true, "xmin": int, "ymin": int, "xmax": int, "ymax": int, "confidence": float, "matched_text": "actual text if any"}}

If not found:
{{"found": false, "reason": "why not found"}}"""

        image_b64 = self._image_to_base64(image)
        img_size_kb = len(image_b64) * 3 / 4 / 1024
        self._log(f"  发送到 AI: 截图 {img_size_kb:.1f}KB")
        self._log(f"  API: {self.config.provider}/{self.config.model}")
        self._log(f"  -> 调用 LLM...")

        if self.config.provider == "claude":
            response = self._call_claude("You are a UI element detection assistant. Only return JSON.", prompt, image_b64)
        else:
            response = self._call_openai_compatible("You are a UI element detection assistant. Only return JSON.", prompt, image_b64, json_mode=True)

        try:
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                self._log(f"LLM 返回: {data}")

                # 检查是否找到
                if data.get("found") == False:
                    reason = data.get("reason", "未找到")
                    self._log(f"find_element 结果: 未找到 - {reason}")
                    return None

                # 检查是否有 bbox 数据
                if "xmin" in data and "ymin" in data:
                    x, y = self._bbox_to_center(data, width, height)
                    confidence = data.get("confidence", 0)
                    matched_text = data.get("matched_text", "")
                    self._log(f"find_element 结果: bbox -> ({x}, {y}), confidence={confidence}, text='{matched_text}'")
                    return (x, y)

                # 兼容旧格式
                x, y = data.get("x"), data.get("y")
                if x is not None and y is not None:
                    pos = (int(x), int(y))
                    self._log(f"find_element 结果: 找到 {pos}")
                    return pos

                self._log(f"find_element 结果: 未找到有效坐标")
        except Exception as e:
            self._log(f"find_element 解析失败: {e}")

        return None

    def find_element_by_image(
        self,
        reference_image: Image.Image,
        screenshot: Image.Image
    ) -> Optional[Tuple[int, int]]:
        """
        通过参考图片在屏幕截图中查找元素（双图匹配模式）

        Args:
            reference_image: 参考图标/元素图片
            screenshot: 屏幕截图

        Returns:
            元素中心坐标 (x, y) 或 None
        """
        self._log(f"===== 双图匹配定位 =====")
        self._log(f"  参考图: {reference_image.size[0]}x{reference_image.size[1]}")
        self._log(f"  截图: {screenshot.size[0]}x{screenshot.size[1]}")
        width, height = screenshot.size

        prompt = """Task: Detect the Reference Image (Image 1) inside the Screenshot (Image 2).

【Instructions】
1. Visual Matching: Find the element in Image 2 that matches Image 1 based on:
   - Shape and outline
   - Color scheme
   - Icon design / visual pattern

2. Coordinate System:
   - Use a scale of 0-1000 for both X and Y axes
   - (0,0) is top-left, (1000,1000) is bottom-right

3. Precision Requirements:
   - Match by visual features, NOT by guessing text/name
   - If the reference is a colored icon, the match must have the same color
   - If the reference has a specific shape, the match must have the same shape

4. Multiple Matches:
   - If multiple similar elements exist, return the most prominent/primary one
   - Report if there are multiple matches

【Output】
Return strictly valid JSON:

If found:
{"found": true, "xmin": int, "ymin": int, "xmax": int, "ymax": int, "confidence": float, "multiple_matches": boolean}

If not found:
{"found": false, "reason": "specific reason why not found", "suggestion": "what to do next"}"""

        # 参考图片不需要太大
        ref_b64 = self._image_to_base64(reference_image, max_size=256)
        screenshot_b64 = self._image_to_base64(screenshot)

        ref_size_kb = len(ref_b64) * 3 / 4 / 1024
        screenshot_size_kb = len(screenshot_b64) * 3 / 4 / 1024
        self._log(f"  发送到 AI: 参考图 {ref_size_kb:.1f}KB + 截图 {screenshot_size_kb:.1f}KB")
        self._log(f"  API: {self.config.provider}/{self.config.model}")

        # 发送两张图片：[参考图, 截图]
        if self.config.provider == "claude":
            # Claude 暂不支持多图片，使用单图片模式
            self._log("  错误: Claude 不支持多图片匹配，请使用 OpenAI 兼容 API")
            return None
        else:
            self._log(f"  -> 调用 LLM...")
            response = self._call_openai_compatible(
                "You are a visual object detection assistant. Only return JSON.",
                prompt,
                [ref_b64, screenshot_b64],
                json_mode=True
            )

        try:
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                self._log(f"LLM 返回: {data}")

                # 检查是否找到
                if data.get("found") == False:
                    reason = data.get("reason", "未找到")
                    suggestion = data.get("suggestion", "")
                    self._log(f"find_element_by_image 结果: 未找到 - {reason}")
                    if suggestion:
                        self._log(f"  建议: {suggestion}")
                    return None

                # 转换 bbox 为中心坐标
                if "xmin" in data and "ymin" in data:
                    x, y = self._bbox_to_center(data, width, height)
                    confidence = data.get("confidence", 0)
                    multiple = data.get("multiple_matches", False)
                    self._log(f"find_element_by_image 结果: bbox -> ({x}, {y}), confidence={confidence}, multiple={multiple}")
                    return (x, y)

                self._log(f"find_element_by_image 结果: 返回数据格式错误")
        except Exception as e:
            self._log(f"find_element_by_image 解析失败: {e}")

        return None

    def describe_screen(self, image: Image.Image) -> str:
        """
        描述屏幕内容

        Args:
            image: 屏幕截图

        Returns:
            屏幕内容描述
        """
        prompt = """请描述这个手机屏幕截图的内容，包括:
1. 当前是什么应用/界面
2. 主要的UI元素和按钮
3. 任何重要的文字内容

用简洁的中文回答。"""

        image_b64 = self._image_to_base64(image)

        if self.config.provider == "claude":
            return self._call_claude("你是屏幕内容描述助手", prompt, image_b64)
        else:
            return self._call_openai_compatible("你是屏幕内容描述助手", prompt, image_b64)

    def get_config_info(self) -> Dict[str, Any]:
        """获取当前 LLM 配置信息（用于调试）"""
        return self.config.to_dict()


def compare_screenshots(img1: Image.Image, img2: Image.Image, threshold: float = 0.02) -> Tuple[bool, float]:
    """
    比较两张截图是否有明显变化

    Args:
        img1: 第一张截图
        img2: 第二张截图
        threshold: 差异阈值（0-1），默认0.02表示2%的像素变化

    Returns:
        (是否有变化, 差异比例)
    """
    # 确保图片尺寸相同
    if img1.size != img2.size:
        img2 = img2.resize(img1.size)

    # 转换为相同模式
    img1 = img1.convert('RGB')
    img2 = img2.convert('RGB')

    # 缩小图片加快计算（采样到 100x200）
    sample_size = (100, 200)
    img1_small = img1.resize(sample_size, Image.Resampling.LANCZOS)
    img2_small = img2.resize(sample_size, Image.Resampling.LANCZOS)

    # 计算像素差异
    pixels1 = list(img1_small.getdata())
    pixels2 = list(img2_small.getdata())

    diff_count = 0
    for p1, p2 in zip(pixels1, pixels2):
        # 计算每个像素的差异（RGB 各通道）
        diff = sum(abs(a - b) for a, b in zip(p1, p2))
        if diff > 30:  # 如果差异超过阈值（30/255 ≈ 12%）
            diff_count += 1

    diff_ratio = diff_count / len(pixels1)
    has_changed = diff_ratio > threshold

    return has_changed, diff_ratio


def is_action_same(a1: Action, a2: Action, tolerance: int = 20) -> bool:
    """
    判断两个 Action 是否相同（用于循环检测）

    Args:
        a1: 第一个 Action
        a2: 第二个 Action
        tolerance: 坐标容差（像素）

    Returns:
        是否相同
    """
    if a1.action_type != a2.action_type:
        return False

    # TAP 和 LONG_PRESS 比较坐标
    if a1.action_type in (ActionType.TAP, ActionType.LONG_PRESS):
        if a1.x and a2.x and a1.y and a2.y:
            return abs(a1.x - a2.x) <= tolerance and abs(a1.y - a2.y) <= tolerance
        return False

    # SWIPE 比较起点和终点
    if a1.action_type == ActionType.SWIPE:
        if all([a1.x, a1.y, a1.x2, a1.y2, a2.x, a2.y, a2.x2, a2.y2]):
            return (abs(a1.x - a2.x) <= tolerance and
                    abs(a1.y - a2.y) <= tolerance and
                    abs(a1.x2 - a2.x2) <= tolerance and
                    abs(a1.y2 - a2.y2) <= tolerance)
        return False

    # INPUT_TEXT 比较文本
    if a1.action_type == ActionType.INPUT_TEXT:
        return a1.text == a2.text

    # PRESS_KEY 比较按键
    if a1.action_type == ActionType.PRESS_KEY:
        return a1.keycode == a2.keycode

    # WAIT 认为总是相同
    if a1.action_type == ActionType.WAIT:
        return True

    return False


def detect_loop(history: List[Action], loop_count: int = 3) -> bool:
    """
    检测是否陷入循环（连续相同操作）

    Args:
        history: 历史操作列表
        loop_count: 判定循环的次数

    Returns:
        是否陷入循环
    """
    if len(history) < loop_count:
        return False

    # 取最后 loop_count 个操作
    recent = history[-loop_count:]

    # 检查是否都相同
    first = recent[0]
    return all(is_action_same(first, action) for action in recent[1:])
