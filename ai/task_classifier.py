"""
ai/task_classifier.py
任务分类器 - 判断任务是简单任务还是复杂任务

支持两种模式：
1. regex: 基于正则表达式规则（快速，无API开销）
2. llm: 基于LLM判断（更准确，支持独立模型配置）
"""
import json
import re
from typing import Optional, Dict, Any, Tuple
from enum import Enum

import config
from config import LLMConfig


class TaskType(Enum):
    """任务类型"""
    SIMPLE = "simple"      # 简单任务：单一动作
    COMPLEX = "complex"    # 复杂任务：多步骤或包含连接词


class TaskClassifier:
    """
    任务分类器

    根据配置使用正则表达式或LLM判断任务是简单还是复杂
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        llm_config: Optional[LLMConfig] = None,
        complex_indicators: Optional[list] = None,
        action_words: Optional[list] = None
    ):
        """
        初始化任务分类器

        Args:
            mode: 分类模式 ('regex' 或 'llm')，默认从环境变量读取
            llm_config: LLM配置（仅在 llm 模式下使用）
            complex_indicators: 复杂任务指示词列表（用于regex模式）
            action_words: 动作词列表（用于regex模式）
        """
        self.mode = mode or config.TASK_CLASSIFIER_MODE
        self._logger = None
        self._last_parsed_data = None  # 保存最后一次LLM解析的数据

        # 正则模式的规则
        self.complex_indicators = complex_indicators or [
            "然后", "再", "接着", "之后", "完成后",
            "并且", "同时", "顺便",
            "截图", "保存",
        ]

        self.action_words = action_words or [
            "发消息", "发朋友圈", "搜索", "加好友",
            "打开", "点击", "截图"
        ]

        # LLM模式的配置
        if self.mode == "llm":
            if llm_config:
                self.llm_config = llm_config
            else:
                # 如果指定了分类器专用的LLM配置，使用专用配置
                if config.TASK_CLASSIFIER_LLM_PROVIDER:
                    self.llm_config = LLMConfig.from_env(config.TASK_CLASSIFIER_LLM_PROVIDER)
                elif config.TASK_CLASSIFIER_LLM_BASE_URL and config.TASK_CLASSIFIER_LLM_MODEL:
                    # 使用自定义配置
                    self.llm_config = LLMConfig.custom(
                        api_key=config.TASK_CLASSIFIER_LLM_API_KEY or config.CUSTOM_LLM_API_KEY,
                        base_url=config.TASK_CLASSIFIER_LLM_BASE_URL,
                        model=config.TASK_CLASSIFIER_LLM_MODEL,
                        max_tokens=512,  # 任务分类只需要少量token
                        temperature=0.0
                    )
                else:
                    # 使用主LLM配置
                    self.llm_config = LLMConfig.from_env()

            # 创建LLM客户端
            from ai.vision_agent import VisionAgent
            self.llm_agent = VisionAgent(llm_config=self.llm_config)
            self.llm_agent.set_logger(self._log)

    def set_logger(self, logger_func):
        """设置日志函数"""
        self._logger = logger_func
        if hasattr(self, 'llm_agent'):
            self.llm_agent.set_logger(logger_func)

    def _log(self, message: str):
        """记录日志"""
        if self._logger:
            self._logger(f"[TaskClassifier] {message}")

    def classify(self, task: str) -> TaskType:
        """
        分类任务

        Args:
            task: 用户任务描述

        Returns:
            TaskType.SIMPLE 或 TaskType.COMPLEX
        """
        if self.mode == "llm":
            return self._classify_with_llm(task)
        else:
            return self._classify_with_regex(task)

    def is_complex_task(self, task: str) -> bool:
        """
        判断是否为复杂任务（兼容旧接口）

        Args:
            task: 用户任务描述

        Returns:
            True 表示复杂任务，False 表示简单任务
        """
        return self.classify(task) == TaskType.COMPLEX

    def get_last_parsed_data(self) -> Optional[Dict[str, Any]]:
        """
        获取最后一次LLM解析的数据

        Returns:
            解析数据字典，包含 type, recipient, content
            如果使用正则模式或LLM解析失败，返回None
        """
        return self._last_parsed_data

    def classify_and_parse(self, task: str) -> Tuple[TaskType, Optional[Dict[str, Any]]]:
        """
        分类任务并返回解析的数据

        流程：
        1. 检查是否为 SS 快速模式（以 ss/SS/Ss/sS 开头）
        2. SS 模式：直接正则解析，返回简单任务 + 解析数据
        3. 非 SS 模式：使用 LLM 解析并分类

        Args:
            task: 用户任务描述

        Returns:
            (TaskType, parsed_data)
            parsed_data 包含 type, recipient, content
        """
        # 1. 检查是否为 SS 快速模式
        if self._is_ss_mode(task):
            self._log("检测到 SS 快速模式")
            parsed_data = self._parse_ss_mode(task)
            if parsed_data:
                self._last_parsed_data = parsed_data
                self._log(f"SS 模式解析成功: {parsed_data}")
                return TaskType.SIMPLE, parsed_data
            else:
                self._log("SS 模式解析失败，降级到 LLM 模式")

        # 2. 非 SS 模式：使用 LLM 分类和解析
        task_type = self._classify_with_llm(task)
        return task_type, self._last_parsed_data

    def _is_ss_mode(self, task: str) -> bool:
        """
        检查是否为 SS 快速模式

        快速模式格式（无需 ss 前缀）：
        1. 联系人:消息内容  (冒号分隔)
        2. 联系人 消息内容  (空格分隔，联系人需满足长度限制)

        Args:
            task: 用户任务描述

        Returns:
            True 表示是 SS 模式
        """
        task_stripped = task.strip()
        if not task_stripped:
            return False

        # 归一化冒号
        normalized = task_stripped.replace('：', ':')

        # 检查冒号分隔：联系人:消息
        if ':' in normalized:
            parts = normalized.split(':', 1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                return True

        # 检查空格分隔：联系人 消息
        space_parts = normalized.split(None, 1)
        if len(space_parts) == 2:
            first_word = space_parts[0].strip()
            rest = space_parts[1].strip()
            if first_word and rest:
                # 朋友圈相关关键词无长度限制
                if first_word.lower() in ['朋友圈', '朋友', 'pyq']:
                    return True
                # 其他情况检查长度限制
                if self._is_valid_recipient_length(first_word):
                    return True

        return False

    def _parse_ss_mode(self, task: str) -> Optional[Dict[str, Any]]:
        """
        解析 SS 快速模式的指令

        支持的格式（无需 ss 前缀）：
        1. 联系人:消息内容  (冒号分隔)
        2. 朋友圈:消息内容  (发朋友圈，冒号分隔)
        3. 联系人 消息内容  (空格分隔，联系人需满足长度限制)
        4. 朋友圈 消息内容  (空格分隔，朋友圈无长度限制)

        冒号不区分中英文（: 或 ：）
        空格分隔时，联系人如果不是"朋友圈"或"朋友"，则不能超过4个汉字或8个英文字母

        Args:
            task: 用户任务描述

        Returns:
            解析后的数据 {type, recipient, content}
            如果解析失败返回 None
        """
        # 归一化冒号（中英文统一为英文冒号）
        normalized_task = task.strip().replace('：', ':')

        # 优先尝试冒号分割：联系人:消息
        if ':' in normalized_task:
            parts = normalized_task.split(':', 1)
            if len(parts) == 2:
                target = parts[0].strip()
                content = parts[1].strip()
                if target and content:
                    return self._parse_ss_parts(target, content)

        # 冒号分隔失败，尝试空格分隔：联系人 消息
        self._log(f"冒号分隔失败，尝试空格分隔")
        space_parts = normalized_task.split(None, 1)  # 最多分割1次

        if len(space_parts) == 2:
            target = space_parts[0].strip()
            content = space_parts[1].strip()

            if target and content:
                # 朋友圈相关关键词无长度限制
                if target.lower() not in ['朋友圈', '朋友', 'pyq']:
                    if not self._is_valid_recipient_length(target):
                        self._log(f"空格分隔失败：'{target}'超过长度限制（4汉字/8英文）")
                        return None

                return self._parse_ss_parts(target, content)

        self._log(f"SS 模式格式错误：无法解析")
        return None

    def _is_valid_recipient_length(self, recipient: str) -> bool:
        """
        检查联系人名称是否符合长度限制

        规则：不能为空，不能超过4个汉字或8个英文字母
        混合情况：1汉字 = 2英文字母的权重

        Args:
            recipient: 联系人名称

        Returns:
            是否符合长度限制
        """
        if not recipient:
            return False

        # 计算长度：汉字算2，其他算1
        length = 0
        for char in recipient:
            if '\u4e00' <= char <= '\u9fff':
                length += 2  # 汉字
            else:
                length += 1  # 英文/数字/符号

        return length <= 8  # 4汉字 = 8，8英文 = 8

    def _parse_ss_parts(self, target: str, content: str) -> Optional[Dict[str, Any]]:
        """
        解析 SS 模式的目标和内容

        Args:
            target: 联系人名称或朋友圈关键词
            content: 消息内容

        Returns:
            解析后的数据 {type, recipient, content}
        """
        target_lower = target.lower()

        # 判断是否为朋友圈
        if target_lower in ['朋友圈', 'pyq', '朋友']:
            if not content:
                self._log("SS 模式格式错误：发朋友圈缺少内容")
                return None

            return {
                "type": "post_moment_only_text",
                "recipient": "",
                "content": content
            }
        else:
            # 默认为发消息
            if not target:
                self._log("SS 模式格式错误：发消息缺少联系人")
                return None
            if not content:
                self._log("SS 模式格式错误：发消息缺少内容")
                return None

            return {
                "type": "send_msg",
                "recipient": target,
                "content": content
            }

    def _classify_with_regex(self, task: str) -> TaskType:
        """
        使用正则表达式规则判断任务类型

        Args:
            task: 用户任务描述

        Returns:
            TaskType
        """
        # 包含复合任务指示词
        if any(indicator in task for indicator in self.complex_indicators):
            self._log(f"正则判断：检测到复杂任务指示词")
            return TaskType.COMPLEX

        # 包含多个动作词
        action_count = sum(1 for w in self.action_words if w in task)
        if action_count >= 2:
            self._log(f"正则判断：检测到多个动作词 (数量: {action_count})")
            return TaskType.COMPLEX

        self._log(f"正则判断：简单任务")
        return TaskType.SIMPLE

    def _ensure_llm_agent(self):
        """确保 LLM agent 已初始化"""
        if not hasattr(self, 'llm_agent') or self.llm_agent is None:
            from ai.vision_agent import VisionAgent
            # 使用主 LLM 配置
            self.llm_config = LLMConfig.from_env()
            self.llm_agent = VisionAgent(llm_config=self.llm_config)
            self.llm_agent.set_logger(self._log)

    def _classify_with_llm(self, task: str) -> TaskType:
        """
        使用LLM判断任务类型

        Args:
            task: 用户任务描述

        Returns:
            TaskType
        """
        # 确保 LLM agent 存在
        self._ensure_llm_agent()

        system_prompt = """你是一个解析器，只输出JSON。字段包含：type(send_msg/post_moment_only_text/others/invalid), recipient, content

type 说明：
- send_msg: 发送消息给联系人
- post_moment_only_text: 发布纯文字朋友圈
- others: 其他复杂任务（多步骤任务）
- invalid: 无效输入（空白、无意义、误触、错误输入等）

invalid 类型示例：
- 空白输入、只有空格/换行
- 无意义的字符（如：aaa、123、！！！）
- 明显的误触（如：s、ss、、、等）
- 不清楚的指令"""

        # 用户提示词就是任务本身
        user_prompt = task

        try:
            # 直接调用OpenAI客户端（不需要图片）
            client = self.llm_agent._get_client()

            # 构建请求参数
            request_params = {
                "model": self.llm_config.model,
                "max_tokens": self.llm_config.max_tokens,
                "temperature": self.llm_config.temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
            }

            # 强制 JSON 输出
            request_params["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**request_params)
            result_text = response.choices[0].message.content

            self._log(f"LLM响应: {result_text[:200]}...")

            # 解析JSON响应
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result = json.loads(json_match.group())
                task_type = result.get("type", "others")
                recipient = result.get("recipient", "")
                content = result.get("content", "")

                # 保存解析的数据，供后续使用
                self._last_parsed_data = {
                    "type": task_type,
                    "recipient": recipient,
                    "content": content
                }

                self._log(f"LLM解析: type={task_type}, recipient={recipient}, content={content}")

                # 根据type判断任务复杂度
                if task_type == "invalid":
                    # 无效输入，标记为复杂任务（在 handler 中会被特殊处理）
                    self._log("LLM判断：无效输入")
                    return TaskType.COMPLEX
                elif task_type in ["send_msg", "post_moment_only_text"]:
                    # send_msg 和 post_moment_only_text 是简单任务
                    return TaskType.SIMPLE
                else:
                    # others类型或无法识别的，判断为复杂任务
                    return TaskType.COMPLEX
            else:
                self._log("LLM响应格式错误，降级使用正则判断")
                return self._classify_with_regex(task)

        except Exception as e:
            self._log(f"LLM分类失败: {e}，降级使用正则判断")
            return self._classify_with_regex(task)


# 全局单例（用于向后兼容）
_global_classifier: Optional[TaskClassifier] = None


def get_task_classifier() -> TaskClassifier:
    """获取全局任务分类器实例"""
    global _global_classifier
    if _global_classifier is None:
        _global_classifier = TaskClassifier()
    return _global_classifier


def is_complex_task(task: str) -> bool:
    """
    判断是否为复杂任务（向后兼容的全局函数）

    Args:
        task: 用户任务描述

    Returns:
        True 表示复杂任务，False 表示简单任务
    """
    classifier = get_task_classifier()
    return classifier.is_complex_task(task)
