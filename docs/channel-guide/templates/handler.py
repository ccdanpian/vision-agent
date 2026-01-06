"""
apps/{channel}/handler.py
{Channel}频道处理器模板

使用说明：
1. 将 {Channel} 替换为频道名称（如 Douyin, Weibo）
2. 将 {channel} 替换为小写名称（如 douyin, weibo）
3. 导入实际的 workflows 模块
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any

from apps.base import DefaultHandler
from .workflows import (
    Workflow, {Channel}Screen, WORKFLOWS, LOCAL_TO_NORMAL_WORKFLOW,
    match_workflow, is_complex_task, get_workflow_descriptions,
    SCREEN_DETECT_REFS
)
from .workflow_executor import WorkflowExecutor, parse_task_params


class Handler(DefaultHandler):
    """
    {Channel}专用处理器

    扩展功能：
    - 工作流执行（简单任务规则匹配，复杂任务 LLM 选择）
    - 界面状态检测
    - 智能导航
    """

    def __init__(self, module_dir: Path):
        super().__init__(module_dir)
        self._workflow_executor: Optional[WorkflowExecutor] = None
        self._task_runner = None

    def set_task_runner(self, task_runner):
        """设置 TaskRunner 引用（用于工作流执行）"""
        self._task_runner = task_runner
        self._workflow_executor = WorkflowExecutor(task_runner, self)
        if self._logger:
            self._workflow_executor.set_logger(self._logger)

    @property
    def workflow_executor(self) -> Optional[WorkflowExecutor]:
        """获取工作流执行器"""
        return self._workflow_executor

    def set_logger(self, logger_func):
        """设置日志函数"""
        super().set_logger(logger_func)
        if self._workflow_executor:
            self._workflow_executor.set_logger(logger_func)

    def get_available_workflows(self) -> Dict[str, str]:
        """获取可用的工作流列表"""
        return {name: wf.description for name, wf in WORKFLOWS.items()}

    def match_workflow(self, task: str) -> Optional[Dict[str, Any]]:
        """
        根据任务描述匹配工作流（简单任务用规则）

        Args:
            task: 用户任务描述

        Returns:
            匹配结果或 None
        """
        return match_workflow(task)

    def select_workflow_with_llm(self, task: str) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 选择工作流和提取参数（复杂任务）

        Args:
            task: 用户任务描述

        Returns:
            {"workflow_name": str, "params": dict} 或 None
        """
        if not self._task_runner:
            self._log("TaskRunner 未设置，无法调用 LLM")
            return None

        # 构建 prompt
        workflow_desc = get_workflow_descriptions()

        prompt = f"""分析以下任务，选择合适的预定义工作流并提取参数。

【用户任务】
{task}

【可用工作流】
{workflow_desc}

【输出格式】
如果任务匹配某个工作流，返回 JSON：
{{"workflow": "工作流名称", "params": {{"参数名": "参数值", ...}}}}

如果没有匹配的工作流，返回：
{{"workflow": null, "reason": "原因说明"}}

注意：
1. 仔细分析任务意图，选择最匹配的工作流
2. 从任务描述中提取所有必需参数
3. 只返回 JSON，不要其他内容"""

        try:
            # 调用 LLM
            vision_agent = self._task_runner.planner.vision
            response = vision_agent._call_openai_compatible(
                "你是任务分析助手，负责匹配工作流和提取参数。只返回JSON。",
                prompt,
                image_base64=None,
                json_mode=True
            )

            self._log(f"LLM 工作流选择响应: {response[:200]}...")

            # 解析响应
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                workflow_name = result.get("workflow")

                if workflow_name and workflow_name in WORKFLOWS:
                    return {
                        "workflow_name": workflow_name,
                        "params": result.get("params", {}),
                        "match_type": "llm"
                    }
                else:
                    self._log(f"LLM 未选择工作流: {result.get('reason', '未知原因')}")

        except Exception as e:
            self._log(f"LLM 工作流选择失败: {e}")

        return None

    def execute_workflow(
        self,
        workflow_name: str,
        params: Dict[str, Any],
        local_only: bool = False
    ) -> Dict[str, Any]:
        """
        执行指定工作流

        Args:
            workflow_name: 工作流名称
            params: 工作流参数
            local_only: 是否仅使用本地匹配（禁用AI回退）

        Returns:
            执行结果
        """
        if not self._workflow_executor:
            return {
                "success": False,
                "message": "工作流执行器未初始化，请先调用 set_task_runner()"
            }

        if workflow_name not in WORKFLOWS:
            return {
                "success": False,
                "message": f"未知工作流: {workflow_name}，可用: {list(WORKFLOWS.keys())}"
            }

        workflow = WORKFLOWS[workflow_name]
        return self._workflow_executor.execute_workflow(workflow, params, local_only)

    def _map_type_to_workflow(self, task_type: str, local_only: bool = False) -> Optional[str]:
        """
        将任务类型映射到工作流名称

        Args:
            task_type: 任务类型（如 send_msg, post_moment_only_text）
            local_only: 是否使用 local_only 版本的工作流

        Returns:
            工作流名称，如果无法映射则返回 None

        注意：每个频道需要根据自己的工作流定义维护此映射表
        """
        if local_only:
            # Local 版本映射（纯本地匹配，无AI回退）
            # TODO: 根据频道实际的工作流定义修改此映射表
            type_to_workflow_map = {
                # "send_msg": "send_message_local",
                # "post_moment_only_text": "post_moments_only_text_local",
            }
        else:
            # 正常版本映射
            # TODO: 根据频道实际的工作流定义修改此映射表
            type_to_workflow_map = {
                # "send_msg": "send_message",
                # "post_moment_only_text": "post_moments",
            }
        return type_to_workflow_map.get(task_type)

    def _map_parsed_data_to_workflow_params(
        self,
        parsed_data: Dict[str, Any],
        workflow_name: str
    ) -> Dict[str, Any]:
        """
        将 TaskClassifier 解析的数据映射到工作流参数

        Args:
            parsed_data: TaskClassifier 返回的解析数据
            workflow_name: 目标工作流名称

        Returns:
            工作流参数字典
        """
        # TODO: 根据频道实际的工作流参数定义修改此映射
        params = {}
        if "contact" in parsed_data:
            params["contact"] = parsed_data["contact"]
        if "content" in parsed_data:
            params["content"] = parsed_data["content"]
        return params

    def execute_task_with_workflow(
        self,
        task: str,
        task_type = None,
        parsed_data: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        尝试使用工作流执行任务

        流程：
        1. 如果有 parsed_data.type -> 直接根据 type 选择工作流
        2. 简单任务（有 local 版本）-> 先尝试 local_only，失败回退到正常模式
        3. 复杂任务 -> LLM 选择
        4. 简单任务 -> 规则匹配（兼容旧逻辑）

        Args:
            task: 用户任务描述
            task_type: 任务类型（可选）
            parsed_data: 已解析的任务数据（可选，包含 type, contact, content 等）

        Returns:
            执行结果，如果没有匹配的工作流则返回 None
        """
        workflow_name = None
        params = {}
        task_parsed_type = None

        # 1. 如果已经解析出 type，直接根据 type 选择工作流
        if parsed_data and parsed_data.get("type"):
            task_parsed_type = parsed_data["type"]
            workflow_name = self._map_type_to_workflow(task_parsed_type)

            if workflow_name:
                params = self._map_parsed_data_to_workflow_params(parsed_data, workflow_name)
                self._log(f"根据 type 选择工作流: {workflow_name} (type={task_parsed_type})")

        # 2. 简单任务优先尝试 local_only 模式
        # TODO: 根据频道实际配置调整支持 local_only 的任务类型
        local_workflow_types = set()  # 例如: {"send_msg", "post_moment_only_text"}
        can_try_local = task_parsed_type in local_workflow_types

        if can_try_local and workflow_name:
            self._log(f"")
            self._log(f"+" + "=" * 40 + "+")
            self._log(f"|    【优化模式】尝试纯本地匹配执行       |")
            self._log(f"+" + "=" * 40 + "+")
            self._log(f"")

            # 获取 local 版本工作流
            local_workflow_name = self._map_type_to_workflow(task_parsed_type, local_only=True)
            if local_workflow_name:
                local_params = self._map_parsed_data_to_workflow_params(parsed_data, local_workflow_name)
                self._log(f"执行 local 工作流: {local_workflow_name}, 参数: {local_params}")

                # 执行 local_only 版本（使用 OPENCV_ONLY 策略）
                result = self.execute_workflow(local_workflow_name, local_params, local_only=True)

                if result["success"]:
                    self._log(f"V local_only 模式执行成功")
                    return result

                # local_only 失败，回退到正常模式
                self._log(f"")
                self._log(f"+" + "=" * 40 + "+")
                self._log(f"|    【回退模式】local失败，使用正常流程   |")
                self._log(f"+" + "=" * 40 + "+")
                self._log(f"")
                self._log(f"local 失败原因: {result.get('message', '未知')}")

        # 3. 复杂任务使用 LLM 选择
        if not workflow_name and task_type and hasattr(task_type, 'name') and task_type.name == 'COMPLEX':
            self._log(f"检测到复杂任务，使用 LLM 选择工作流")
            llm_result = self.select_workflow_with_llm(task)
            if llm_result:
                workflow_name = llm_result["workflow_name"]
                params = llm_result["params"]
                self._log(f"LLM 选择工作流: {workflow_name}, 参数: {params}")

        # 4. 简单任务但没有 type -> 规则匹配工作流（兼容旧逻辑）
        if not workflow_name:
            if is_complex_task(task):
                self._log(f"检测到复杂任务，使用 LLM 选择工作流")
                llm_result = self.select_workflow_with_llm(task)
                if llm_result:
                    workflow_name = llm_result["workflow_name"]
                    params = llm_result["params"]
            else:
                match_result = self.match_workflow(task)
                if match_result:
                    workflow = match_result["workflow"]
                    workflow_name = workflow.name
                    param_hints = match_result["param_hints"]
                    params = parse_task_params(task, param_hints)
                    self._log(f"规则匹配工作流: {workflow_name}, 参数: {params}")

        # 5. 如果没有匹配到工作流
        if not workflow_name:
            self._log(f"未匹配到工作流: {task}")
            return None

        # 6. 检查必需参数
        workflow = WORKFLOWS[workflow_name]
        missing = [p for p in workflow.required_params if p not in params or not params[p]]
        if missing:
            self._log(f"缺少必需参数: {missing}")
            return {
                "success": False,
                "message": f"无法从任务中解析出必需参数: {missing}",
                "workflow": workflow_name,
                "parsed_params": params,
                "missing_params": missing
            }

        # 7. 执行工作流（正常模式）
        return self.execute_workflow(workflow_name, params, local_only=False)

    def detect_current_screen(self) -> {Channel}Screen:
        """检测当前界面"""
        if not self._workflow_executor:
            return {Channel}Screen.UNKNOWN
        return self._workflow_executor.detect_screen()

    def navigate_to_home(self) -> bool:
        """导航到首页"""
        if not self._workflow_executor:
            return False
        return self._workflow_executor.navigate_to_home()

    def get_screen_ref(self, screen: {Channel}Screen) -> Optional[str]:
        """获取界面对应的参考图名称"""
        return SCREEN_DETECT_REFS.get(screen)

    def get_planner_prompt(self) -> str:
        """
        获取规划器提示词

        扩展父类方法，添加工作流相关信息
        """
        base_prompt = super().get_planner_prompt()

        # 添加工作流信息（包含具体步骤）
        workflow_info = "\n\n【预定义工作流 - 必须优先参考！】\n"
        workflow_info += "以下任务有预定义的执行路径，**必须优先使用这些步骤**，不要自主设计：\n\n"

        for name, wf in WORKFLOWS.items():
            workflow_info += f"**{name}**: {wf.description}\n"
            workflow_info += f"  必需参数: {wf.required_params}\n"
            workflow_info += f"  标准步骤:\n"
            for i, step in enumerate(wf.steps, 1):
                target = step.target if step.target else "(无)"
                workflow_info += f"    {i}. {step.action}: {step.description} -> {target}\n"
            workflow_info += "\n"

        workflow_info += """**使用规则**:
1. 如果任务匹配上述工作流，**直接使用其标准步骤**
2. 根据当前屏幕调整起点 - 如果已在中间步骤，跳过前面的步骤
3. 只有无匹配时才自主规划

【重要：界面导航规则】
1. 执行任何操作前，先检查当前界面状态
2. 如果不在正确的界面，先导航到正确位置
3. 不要在错误的界面尝试执行操作

【重要：参考图用途区分】
参考图分为两类，用途不同：

1. 界面判断参考图（用于验证当前在哪个页面，不用于点击）：
   - system/{channel}_home_page: 首页
   - system/{channel}_*_page: 其他页面

2. 点击操作参考图（用于定位可点击元素）：
   - {channel}_*_button: 各种按钮
   - {channel}_*_input: 输入框

注意：
- 点击操作时必须使用"点击操作参考图"，不要使用"界面判断参考图"！
- 部分参考图有 _v1 变体版本用于多设备适配，系统会自动尝试匹配
"""

        return base_prompt + workflow_info
