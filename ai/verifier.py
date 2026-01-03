"""
ai/verifier.py
结果验证器 - 验证操作是否成功，确定下一步行动

职责:
- 比较当前屏幕与期望状态
- 检测屏幕变化
- 识别弹窗等阻挡物
- 提供恢复建议
"""
import json
import re
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from PIL import Image

from config import LLMConfig
from ai.vision_agent import VisionAgent, compare_screenshots


class BlockerType(Enum):
    """阻挡物类型"""
    NONE = "none"
    POPUP = "popup"           # 普通弹窗
    DIALOG = "dialog"         # 对话框
    PERMISSION = "permission" # 权限请求
    AD = "ad"                 # 广告
    ERROR = "error"           # 错误提示
    LOADING = "loading"       # 加载中
    KEYBOARD = "keyboard"     # 键盘弹出
    UNKNOWN = "unknown"       # 未知弹窗


class SuggestionAction(Enum):
    """建议动作"""
    CONTINUE = "continue"    # 继续执行下一步
    RETRY = "retry"          # 重试当前步骤
    SKIP = "skip"            # 跳过当前步骤
    WAIT = "wait"            # 等待一段时间
    DISMISS = "dismiss"      # 关闭弹窗
    ABORT = "abort"          # 中止任务
    REPLAN = "replan"        # 重新规划


@dataclass
class DismissSuggestion:
    """关闭弹窗的建议"""
    action: str                    # tap / press_key / swipe
    target_ref: Optional[str]      # 参考图名称或 dynamic:描述
    description: str               # 说明
    keycode: Optional[int] = None  # 按键码（用于 press_key）


@dataclass
class Blocker:
    """阻挡物信息"""
    type: BlockerType
    description: str
    dismiss_suggestion: Optional[DismissSuggestion] = None


@dataclass
class VerifyResult:
    """验证结果"""
    verified: bool              # 是否验证通过
    confidence: float           # 置信度 (0-1)
    current_state: str          # 当前状态描述
    matches_expected: bool      # 是否匹配期望状态
    screen_changed: bool        # 屏幕是否有变化
    change_description: str     # 变化描述
    blocker: Optional[Blocker]  # 检测到的阻挡物
    suggestion: SuggestionAction  # 建议的下一步动作
    suggestion_detail: str      # 建议详情


class Verifier:
    """
    结果验证器

    验证操作是否成功，检测阻挡物，提供恢复建议。
    """

    def __init__(self, llm_config: Optional[LLMConfig] = None):
        """
        初始化验证器

        Args:
            llm_config: LLM 配置，如果为 None 则从环境变量加载
        """
        self.vision = VisionAgent(llm_config=llm_config)
        self._logger = None

    def set_logger(self, logger_func):
        """设置日志回调函数"""
        self._logger = logger_func
        self.vision.set_logger(logger_func)

    def _log(self, message: str):
        """记录日志"""
        if self._logger:
            self._logger(f"[Verifier] {message}")
        else:
            print(f"[Verifier] {message}")

    def verify_with_reference(
        self,
        expected_ref: Image.Image,
        current_screenshot: Image.Image,
        success_condition: Optional[str] = None
    ) -> VerifyResult:
        """
        使用参考图验证当前状态

        Args:
            expected_ref: 期望状态的参考图
            current_screenshot: 当前屏幕截图
            success_condition: 成功条件描述（可选）

        Returns:
            VerifyResult 验证结果
        """
        self._log("使用参考图验证...")

        prompt = self._build_reference_verify_prompt(success_condition)

        # 发送两张图片进行对比
        ref_b64 = self.vision._image_to_base64(expected_ref, max_size=512)
        screenshot_b64 = self.vision._image_to_base64(current_screenshot)

        if self.vision.config.provider == "claude":
            self._log("Claude 不支持多图片验证，使用描述模式")
            return self._verify_with_description(current_screenshot, success_condition or "操作成功")
        else:
            response = self.vision._call_openai_compatible(
                self._get_system_prompt(),
                prompt,
                [ref_b64, screenshot_b64],
                json_mode=True
            )

        self._log(f"LLM 响应: {response[:300]}...")
        return self._parse_verify_response(response)

    def verify_with_description(
        self,
        current_screenshot: Image.Image,
        expected_description: str,
        previous_screenshot: Optional[Image.Image] = None
    ) -> VerifyResult:
        """
        使用文字描述验证当前状态

        Args:
            current_screenshot: 当前屏幕截图
            expected_description: 期望状态描述
            previous_screenshot: 操作前的截图（用于对比变化）

        Returns:
            VerifyResult 验证结果
        """
        return self._verify_with_description(
            current_screenshot,
            expected_description,
            previous_screenshot
        )

    def _verify_with_description(
        self,
        current_screenshot: Image.Image,
        expected_description: str,
        previous_screenshot: Optional[Image.Image] = None
    ) -> VerifyResult:
        """使用描述验证（内部方法）"""
        self._log(f"验证状态: {expected_description}")

        # 检测屏幕变化
        screen_changed = True
        change_ratio = 1.0
        if previous_screenshot:
            screen_changed, change_ratio = compare_screenshots(
                previous_screenshot, current_screenshot
            )
            self._log(f"屏幕变化: {screen_changed}, 变化比例: {change_ratio:.2%}")

        prompt = self._build_description_verify_prompt(
            expected_description,
            screen_changed,
            change_ratio
        )

        screenshot_b64 = self.vision._image_to_base64(current_screenshot)

        if self.vision.config.provider == "claude":
            response = self.vision._call_claude(
                self._get_system_prompt(),
                prompt,
                screenshot_b64
            )
        else:
            response = self.vision._call_openai_compatible(
                self._get_system_prompt() + "\n只返回JSON。",
                prompt,
                screenshot_b64,
                json_mode=True
            )

        self._log(f"LLM 响应: {response[:300]}...")
        result = self._parse_verify_response(response)

        # 补充屏幕变化信息
        if not result.screen_changed and previous_screenshot:
            result.screen_changed = screen_changed

        return result

    def detect_blocker(self, screenshot: Image.Image) -> Optional[Blocker]:
        """
        检测屏幕上是否有阻挡物（弹窗、对话框等）

        Args:
            screenshot: 当前屏幕截图

        Returns:
            Blocker 对象，如果没有阻挡物则返回 None
        """
        self._log("检测阻挡物...")

        prompt = """分析当前屏幕，检测是否有阻挡主界面的元素。

检测目标:
- 权限请求弹窗（如"允许访问相机/存储"）
- 更新提示对话框
- 广告弹窗
- 活动/促销弹窗
- 引导/教程弹窗
- 错误提示
- 加载中遮罩

输出 JSON:
{
  "has_blocker": true/false,
  "blocker_type": "permission/popup/dialog/ad/error/loading/none",
  "description": "弹窗内容描述",
  "dismiss_method": {
    "action": "tap/press_key/swipe/wait",
    "target": "关闭按钮/确定按钮 或 dynamic:描述",
    "keycode": 4
  }
}

如果没有阻挡物，返回:
{"has_blocker": false, "blocker_type": "none"}"""

        screenshot_b64 = self.vision._image_to_base64(screenshot)

        if self.vision.config.provider == "claude":
            response = self.vision._call_claude(
                "你是 UI 阻挡物检测专家。只返回 JSON。",
                prompt,
                screenshot_b64
            )
        else:
            response = self.vision._call_openai_compatible(
                "你是 UI 阻挡物检测专家。只返回 JSON。",
                prompt,
                screenshot_b64,
                json_mode=True
            )

        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())

                if not data.get("has_blocker", False):
                    return None

                # 解析阻挡物类型
                blocker_type_str = data.get("blocker_type", "unknown")
                try:
                    blocker_type = BlockerType(blocker_type_str)
                except ValueError:
                    blocker_type = BlockerType.UNKNOWN

                # 解析关闭建议
                dismiss_suggestion = None
                dismiss_data = data.get("dismiss_method")
                if dismiss_data:
                    dismiss_suggestion = DismissSuggestion(
                        action=dismiss_data.get("action", "tap"),
                        target_ref=dismiss_data.get("target"),
                        description=f"关闭{data.get('description', '弹窗')}",
                        keycode=dismiss_data.get("keycode")
                    )

                return Blocker(
                    type=blocker_type,
                    description=data.get("description", ""),
                    dismiss_suggestion=dismiss_suggestion
                )
        except Exception as e:
            self._log(f"解析阻挡物检测结果失败: {e}")

        return None

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是 Android 自动化验证专家。分析屏幕截图，验证操作是否成功。

【验证规则】
1. 仔细比较当前屏幕与期望状态
2. 识别任何可能阻挡操作的弹窗或对话框
3. 给出明确的验证结论和建议

【阻挡物类型】
- permission: 权限请求弹窗
- popup: 普通弹窗（活动、促销等）
- dialog: 对话框（确认、提示等）
- ad: 广告
- error: 错误提示
- loading: 加载中
- keyboard: 键盘弹出
- none: 无阻挡物

【建议动作】
- continue: 验证通过，继续下一步
- retry: 验证失败，重试当前步骤
- skip: 跳过当前步骤
- wait: 等待一段时间
- dismiss: 需要先关闭弹窗
- abort: 无法完成，中止任务
- replan: 需要重新规划"""

    def _build_reference_verify_prompt(self, success_condition: Optional[str]) -> str:
        """构建参考图验证提示词"""
        prompt = """验证当前屏幕状态。

【参考图】
Image 1: 期望的屏幕状态

【当前截图】
Image 2: 当前屏幕截图

【验证任务】
判断 Image 2 是否与 Image 1 表示的状态匹配。"""

        if success_condition:
            prompt += f"\n\n【额外成功条件】\n{success_condition}"

        prompt += """

【输出格式】
返回 JSON:
{
  "verified": true/false,
  "confidence": 0.0-1.0,
  "current_state": "当前屏幕状态描述",
  "matches_expected": true/false,
  "screen_changed": true/false,
  "change_description": "变化描述",
  "detected_blocker": null 或 {
    "type": "popup/dialog/permission/ad/error/loading",
    "description": "阻挡物描述",
    "dismiss_action": "tap/press_key",
    "dismiss_target": "关闭按钮 或 dynamic:描述"
  },
  "suggestion": "continue/retry/skip/wait/dismiss/abort/replan",
  "suggestion_detail": "建议详情"
}"""
        return prompt

    def _build_description_verify_prompt(
        self,
        expected_description: str,
        screen_changed: bool,
        change_ratio: float
    ) -> str:
        """构建描述验证提示词"""
        return f"""验证当前屏幕状态。

【期望状态】
{expected_description}

【屏幕变化检测】
- 屏幕已变化: {"是" if screen_changed else "否"}
- 变化比例: {change_ratio:.1%}

【验证任务】
1. 分析当前屏幕是否达到期望状态
2. 检测是否有弹窗等阻挡物
3. 给出验证结论和下一步建议

【输出格式】
返回 JSON:
{{
  "verified": true/false,
  "confidence": 0.0-1.0,
  "current_state": "当前屏幕状态描述",
  "matches_expected": true/false,
  "screen_changed": {str(screen_changed).lower()},
  "change_description": "变化描述",
  "detected_blocker": null 或 {{
    "type": "popup/dialog/permission/ad/error/loading",
    "description": "阻挡物描述",
    "dismiss_action": "tap/press_key",
    "dismiss_target": "关闭按钮 或 dynamic:描述"
  }},
  "suggestion": "continue/retry/skip/wait/dismiss/abort/replan",
  "suggestion_detail": "建议详情"
}}"""

    def _parse_verify_response(self, response: str) -> VerifyResult:
        """解析验证响应"""
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())

                # 解析阻挡物
                blocker = None
                blocker_data = data.get("detected_blocker")
                if blocker_data:
                    blocker_type_str = blocker_data.get("type", "unknown")
                    try:
                        blocker_type = BlockerType(blocker_type_str)
                    except ValueError:
                        blocker_type = BlockerType.UNKNOWN

                    dismiss_suggestion = None
                    if blocker_data.get("dismiss_action"):
                        dismiss_suggestion = DismissSuggestion(
                            action=blocker_data.get("dismiss_action", "tap"),
                            target_ref=blocker_data.get("dismiss_target"),
                            description="关闭弹窗"
                        )

                    blocker = Blocker(
                        type=blocker_type,
                        description=blocker_data.get("description", ""),
                        dismiss_suggestion=dismiss_suggestion
                    )

                # 解析建议动作
                suggestion_str = data.get("suggestion", "continue")
                try:
                    suggestion = SuggestionAction(suggestion_str)
                except ValueError:
                    suggestion = SuggestionAction.CONTINUE

                return VerifyResult(
                    verified=data.get("verified", False),
                    confidence=data.get("confidence", 0.0),
                    current_state=data.get("current_state", "未知"),
                    matches_expected=data.get("matches_expected", False),
                    screen_changed=data.get("screen_changed", False),
                    change_description=data.get("change_description", ""),
                    blocker=blocker,
                    suggestion=suggestion,
                    suggestion_detail=data.get("suggestion_detail", "")
                )
        except Exception as e:
            self._log(f"解析验证响应失败: {e}")

        # 返回默认失败结果
        return VerifyResult(
            verified=False,
            confidence=0.0,
            current_state="解析失败",
            matches_expected=False,
            screen_changed=False,
            change_description="",
            blocker=None,
            suggestion=SuggestionAction.RETRY,
            suggestion_detail="验证响应解析失败，建议重试"
        )

    def quick_check(
        self,
        before_screenshot: Image.Image,
        after_screenshot: Image.Image,
        expected_change: str
    ) -> Tuple[bool, str]:
        """
        快速检查操作是否有效果

        Args:
            before_screenshot: 操作前截图
            after_screenshot: 操作后截图
            expected_change: 期望的变化描述

        Returns:
            (是否有效, 变化描述)
        """
        # 首先用简单的像素比较
        changed, ratio = compare_screenshots(before_screenshot, after_screenshot)

        if not changed:
            return False, "屏幕无变化"

        # 如果有变化，用 LLM 确认变化是否符合预期
        self._log(f"检测到屏幕变化 ({ratio:.1%})，验证是否符合预期...")

        result = self._verify_with_description(
            after_screenshot,
            expected_change,
            before_screenshot
        )

        return result.verified, result.change_description
